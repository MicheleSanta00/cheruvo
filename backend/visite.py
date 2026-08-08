"""
visite.py — Contare chi arriva, senza tracciare nessuno.

PERCHÉ ESISTE

L'8 agosto 2026 una persona ha scritto su Reddit di aver provato il sito. Su
PostHog non c'era, e su Supabase nemmeno. Non era un guasto: erano tre filtri
in fila, e ne basta uno.

  1. PostHog non parte affatto senza il consenso ai cookie, e quasi nessuno
     clicca "accetta" su un banner.
  2. `respect_dnt: true`: chi ha Do Not Track attivo è invisibile per scelta
     nostra.
  3. `eu.i.posthog.com` è bloccato da qualunque ad blocker, e fra il pubblico
     che ci interessa gli ad blocker li ha la maggioranza.

E su Supabase non doveva comparire: da quando il muro a pagamento è spento,
guardare il sito non richiede un account.

Il risultato era il peggiore possibile per chi sta cercando i primi utenti:
non "pochi visitatori", ma **nessuna idea di quanti siano**. E si stava per
giudicare se la promozione funzionava guardando un numero che non li vedeva.

COSA CONTA, E COSA NON RACCOGLIE

Il frontend genera un numero casuale per SESSIONE del browser, tenuto in
`sessionStorage`, e lo manda come intestazione. Qui si conta quanti numeri
distinti si presentano in un giorno.

Quel numero muore quando si chiude la scheda, non segue nessuno da un giorno
all'altro, non è legato a un account e non è ricavato da caratteristiche del
dispositivo. Non è un'impronta digitale: è un gettone per il turno, come il
numerino del banco dei salumi.

Non vengono salvati: indirizzi IP, user agent, referrer, pagine viste,
posizione geografica. Nemmeno in forma cifrata o abbreviata. Un conteggio non
ha bisogno di sapere chi eri, ha bisogno di sapere quanti eravate, ed è per
questo che non serve chiedere un consenso per farlo.

COME SI LEGGE IL NUMERO, ONESTAMENTE

`sessioni` è il numero più vicino a "quante persone". Ma una stessa persona che
apre il sito la mattina e il pomeriggio conta due volte, e una che tiene la
scheda aperta tutto il giorno conta una volta sola. È una stima, non un censimento.

`richieste` è sempre più grande e serve solo a capire se qualcuno sta usando
davvero il sito o l'ha solo aperto: molte richieste per poche sessioni vuol
dire che la gente ci clicca dentro.

    python backend/visite.py            # stampa gli ultimi 14 giorni
"""
import logging
import sys
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Solo il traffico che indica una persona davanti a uno schermo.
# `/ping` e `/health` sono la sveglia esterna che chiama ogni pochi minuti:
# contarli vorrebbe dire vedere centinaia di "visite" al giorno fatte da un
# cron, ed è esattamente il tipo di numero gonfio che fa prendere decisioni
# sbagliate.
IGNORA = ("/ping", "/health", "/docs", "/openapi.json", "/favicon.ico")

INTESTAZIONE = "x-sessione"

# Segni che dietro non c'è una persona. L'elenco è corto di proposito: serve a
# togliere i crawler dichiarati, non a fare la guerra a chi si traveste.
BOT = ("bot", "crawler", "spider", "curl", "wget", "python-requests",
       "headless", "monitor", "uptime", "pingdom", "lighthouse")


def _tabella(cur) -> None:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS visite (
            giorno   DATE NOT NULL,
            sessione TEXT NOT NULL,
            percorso TEXT NOT NULL,
            quante   INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (giorno, sessione, percorso)
        )
    """)


def registra(sessione: str, percorso: str) -> None:
    """
    Segna una richiesta. Non deve mai far fallire la richiesta vera: se il
    conteggio si rompe, l'utente non se ne deve accorgere.
    """
    if not sessione or any(percorso.startswith(p) for p in IGNORA):
        return
    try:
        from database import get_pool
        pool = get_pool()
        conn = pool.getconn()
        try:
            cur = conn.cursor()
            _tabella(cur)
            cur.execute("""
                INSERT INTO visite (giorno, sessione, percorso)
                VALUES (CURRENT_DATE, %s, %s)
                ON CONFLICT (giorno, sessione, percorso)
                DO UPDATE SET quante = visite.quante + 1
            """, (sessione[:64], percorso[:120]))
            conn.commit()
            cur.close()
        finally:
            pool.putconn(conn)
    except Exception as e:
        logger.debug("conteggio visite non riuscito: %s", e)


def e_bot(user_agent: str) -> bool:
    ua = (user_agent or "").lower()
    return not ua or any(b in ua for b in BOT)


def riepilogo(giorni: int = 14) -> list[dict]:
    from database import get_pool
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        _tabella(cur)
        cur.execute("""
            SELECT giorno,
                   COUNT(DISTINCT sessione) AS sessioni,
                   SUM(quante)              AS richieste
            FROM visite
            WHERE giorno >= CURRENT_DATE - %s::integer
            GROUP BY giorno
            ORDER BY giorno DESC
        """, (giorni,))
        righe = cur.fetchall()
        cur.close()
    finally:
        pool.putconn(conn)
    return [{"giorno": g.isoformat(), "sessioni": int(s), "richieste": int(r)}
            for g, s, r in righe]


def main() -> int:
    righe = riepilogo()
    print("=" * 52)
    print(f"  VISITE — {datetime.now(timezone.utc):%d/%m/%Y}")
    print("=" * 52)
    if not righe:
        print("\n  Nessuna visita registrata.")
        print("  Se il frontend aggiornato non e' ancora online, e' normale.")
        return 0

    print(f"\n  {'giorno':<12}{'sessioni':>10}{'richieste':>12}")
    print("  " + "-" * 34)
    for r in righe:
        print(f"  {r['giorno']:<12}{r['sessioni']:>10}{r['richieste']:>12}")

    tot = sum(r["sessioni"] for r in righe)
    print(f"\n  totale sessioni nel periodo: {tot}")
    print("\n  Una sessione non e' una persona: chi apre il sito due volte in")
    print("  un giorno conta due volte, chi lascia la scheda aperta conta una")
    print("  volta sola. E' la stima piu' onesta che si possa fare senza")
    print("  seguire nessuno.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    except ImportError:
        pass
    sys.exit(main())
