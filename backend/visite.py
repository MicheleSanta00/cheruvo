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

`richieste` NON dice quanto interesse c'è, e per un po' questo file ha scritto
il contrario. Diceva che molte richieste per poche sessioni vogliono dire che
la gente ci clicca dentro, e citava i rapporti 46, 6, 37 e 30 delle prime
giornate come prova.

È sbagliato, e il motivo sta nel frontend. `App.jsx` si ricarica da solo: la
classifica ogni 15 minuti, i dati del titolo aperto ogni 10, e i prezzi del
grafico giornaliero ogni 60 secondi finché la borsa è aperta. Una scheda
lasciata aperta un'ora, con nessuno davanti, produce da sola una sessantina di
richieste. Il 17 agosto 2026 il rapporto era 78 a 1, il più alto mai visto, ed
è esattamente ciò che si vede quando qualcuno apre il sito e se ne va.

Quello che un ciclo automatico non può gonfiare sono i PERCORSI DISTINTI, cioè
la colonna `percorsi`. Un timer chiede sempre le stesse cose e non ne aggiunge
una; una persona che cambia titolo ne aggiunge tre ogni volta. Aprire il sito
e guardare il titolo predefinito costa cinque o sei percorsi: sotto quella
soglia nessuno ha fatto niente, sopra qualcuno si è mosso.

    python backend/visite.py --dettaglio 2026-08-17

stampa, per ogni sessione di quel giorno, che cosa ha chiesto davvero.

CHI SVILUPPA NON DEVE CONTARSI

Per i primi giorni il conteggio comprendeva anche Michele, che apre il sito
venti volte al giorno per controllare una cosa. Non si poteva separare: qui non
si sa chi sia nessuno, ed è voluto.

La soluzione sta nel frontend (`apiFetch.js`): aprendo una volta
`app.cheruvo.com/?noncontarmi=1` quel browser smette di mandare il gettone e
sparisce dal conteggio, in modo permanente e senza spedire niente in più.
Non passa da una variabile d'ambiente perché il repo è pubblico e finirebbe in
chiaro nel bundle. Si annulla con `?noncontarmi=0`.

    python backend/visite.py            # stampa gli ultimi 14 giorni
"""
import logging
import re
import sys
import threading
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Qui sopra c'e' scritto che il conteggio non e' legato a un account. Il 18
# agosto 2026 non era piu' vero: `/api/subscription/{user_id}` porta
# l'identificativo dell'utente dentro il percorso, e finiva nella tabella
# accanto al gettone di sessione. Bastava una join per sapere chi era.
#
# Nessuno l'aveva messo li' apposta: l'indirizzo esiste da mesi ed e' il
# conteggio dei percorsi ad averlo fatto vedere. Una promessa sulla privacy
# scritta nel docstring non si mantiene da sola, va imposta dal codice.
_IDENTIFICATIVO = re.compile(
    r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def senza_identificativi(percorso: str) -> str:
    """Toglie dal percorso gli UUID, che dicono CHI invece di COSA."""
    return _IDENTIFICATIVO.sub("/:id", percorso or "")

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


# ══════════════════════════════════════════════════════════════════════════
#  SCRIVERE SENZA AMMAZZARE IL SERVER
# ══════════════════════════════════════════════════════════════════════════
#
# La prima versione di questo file, dell'8 agosto 2026, faceva a OGNI singola
# richiesta: prendi una connessione dal pool, esegui un CREATE TABLE IF NOT
# EXISTS, scrivi, fai commit, restituisci la connessione.
#
# Il pool ne ha da 2 a 10. Quindi bastavano poche richieste ravvicinate perché
# le connessioni finissero e le richieste successive restassero in attesa: il
# backend sembrava morto, si riprendeva, e tornava a morire. Michele l'ha
# visto succedere per due giorni.
#
# Ci sono tre errori sovrapposti, e vale la pena nominarli tutti perché sono
# tre errori diversi.
#
#   1. DDL nel percorso di una richiesta. `CREATE TABLE IF NOT EXISTS` sembra
#      gratis perché di solito non fa niente, ma e' pur sempre una richiesta
#      di lock sullo schema, mille volte al giorno, per creare una tabella che
#      esiste gia' dal primo minuto.
#   2. Una scrittura sincrona per ogni lettura. Perfino le risposte servite
#      dalla cache, che non toccavano il database, sono diventate scritture.
#   3. I/O bloccante dentro un middleware asincrono: mentre quella connessione
#      aspetta il database, il ciclo di eventi non serve nessun altro.
#
# Adesso `registra` non tocca il database: somma in memoria e basta, dura
# microsecondi. Ogni tanto un thread separato svuota il conto accumulato con
# UNA connessione e UNA scrittura sola.
#
# Il prezzo, detto chiaro: se il servizio si spegne fra due scaricamenti, i
# conteggi di quei secondi si perdono. Per un contatore di visite e' un prezzo
# accettabile; per i dati veri non lo sarebbe mai.

_conteggio: dict = {}
_serratura = threading.Lock()
_ultimo_scarico = time.monotonic()
_tabella_creata = False

INTERVALLO_SCARICO = 60      # secondi fra uno svuotamento e l'altro
MASSIMO_IN_MEMORIA = 500     # oltre questo si svuota subito, per non gonfiare


def registra(sessione: str, percorso: str) -> None:
    """
    Segna una richiesta. Non tocca il database e non puo' far aspettare
    nessuno: incrementa un numero in memoria.
    """
    if not sessione or any(percorso.startswith(p) for p in IGNORA):
        return

    global _ultimo_scarico
    chiave = (sessione[:64], senza_identificativi(percorso)[:120])
    scarica = False

    with _serratura:
        _conteggio[chiave] = _conteggio.get(chiave, 0) + 1
        scaduto = time.monotonic() - _ultimo_scarico > INTERVALLO_SCARICO
        if scaduto or len(_conteggio) >= MASSIMO_IN_MEMORIA:
            _ultimo_scarico = time.monotonic()
            scarica = True

    if scarica:
        # In un thread suo: se il database e' lento, a rallentare e' lui e non
        # la persona che sta guardando il sito.
        threading.Thread(target=scarica_su_database, daemon=True).start()


def scarica_su_database() -> int:
    """Svuota il conto accumulato. Una connessione, una scrittura sola."""
    global _tabella_creata

    with _serratura:
        if not _conteggio:
            return 0
        da_scrivere = list(_conteggio.items())
        _conteggio.clear()

    try:
        from database import get_pool
        pool = get_pool()
        conn = pool.getconn()
        try:
            cur = conn.cursor()
            if not _tabella_creata:
                _tabella(cur)
                _tabella_creata = True
            cur.executemany("""
                INSERT INTO visite (giorno, sessione, percorso, quante)
                VALUES (CURRENT_DATE, %s, %s, %s)
                ON CONFLICT (giorno, sessione, percorso)
                DO UPDATE SET quante = visite.quante + EXCLUDED.quante
            """, [(s, p, n) for (s, p), n in da_scrivere])
            conn.commit()
            cur.close()
        finally:
            pool.putconn(conn)
        return len(da_scrivere)
    except Exception as e:
        # Rimettere dentro quello che non è stato scritto: al prossimo giro si
        # riprova, invece di perdere il conteggio per un singhiozzo del
        # database.
        with _serratura:
            for chiave, n in da_scrivere:
                _conteggio[chiave] = _conteggio.get(chiave, 0) + n
        logger.debug("scarico visite non riuscito: %s", e)
        return 0


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
        # COUNT(*) sono i percorsi distinti: la chiave primaria è
        # (giorno, sessione, percorso), quindi ogni riga è una cosa diversa
        # chiesta almeno una volta. È il numero che un timer non gonfia.
        cur.execute("""
            SELECT giorno,
                   COUNT(DISTINCT sessione) AS sessioni,
                   SUM(quante)              AS richieste,
                   COUNT(*)                 AS percorsi
            FROM visite
            WHERE giorno >= CURRENT_DATE - %s::integer
            GROUP BY giorno
            ORDER BY giorno DESC
        """, (giorni,))
        righe = cur.fetchall()
        cur.close()
    finally:
        pool.putconn(conn)
    return [{"giorno": g.isoformat(), "sessioni": int(s),
             "richieste": int(r), "percorsi": int(p)}
            for g, s, r, p in righe]


def titoli_scelti(percorsi) -> set:
    """
    I titoli che la persona ha scelto, distinti da quelli che carica l'app.

    `useFinData` chiama `/validate/{ticker}` come PRIMA cosa quando si apre un
    titolo, e non lo chiama in nessun altro caso. Quindi un `validate` e' una
    scelta, mentre `/news/{tk}` da solo non lo e': la sidebar lo chiede da
    sola per ogni titolo della watchlist predefinita, ed e' il motivo per cui
    DIA e GOOG comparivano in quasi tutte le sessioni del 16 agosto 2026
    senza che nessuno li avesse cercati.

    Contare i percorsi invece delle scelte faceva sbagliare in tutte e due le
    direzioni: la schermata iniziale ne costa cinque senza che nessuno tocchi
    niente, e una sessione da sei percorsi veniva marcata "ha aperto e basta"
    quando aveva aperto Solana.
    """
    return {p.rsplit("/", 1)[-1] for p in percorsi if "/validate/" in p}


def dettaglio(giorno: str) -> list[dict]:
    """
    Cosa ha chiesto davvero ogni sessione di un certo giorno.

    Serve a distinguere le due cose che la colonna `richieste` confonde: una
    persona che si muove nel sito e una scheda dimenticata aperta che si
    ricarica da sola.
    """
    from database import get_pool
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        _tabella(cur)
        cur.execute("""
            SELECT sessione, percorso, quante
            FROM visite
            WHERE giorno = %s::date
            ORDER BY sessione, quante DESC, percorso
        """, (giorno,))
        righe = cur.fetchall()
        cur.close()
    finally:
        pool.putconn(conn)

    sessioni: dict[str, list] = {}
    for s, p, n in righe:
        sessioni.setdefault(s, []).append((p, int(n)))
    return [{"sessione": s,
             "percorsi": len(v),
             "richieste": sum(n for _, n in v),
             "scelti": titoli_scelti(p for p, _ in v),
             "cosa": v}
            for s, v in sessioni.items()]


def main(giorni: int = 14) -> int:
    righe = riepilogo(giorni)
    print("=" * 52)
    print(f"  VISITE — {datetime.now(timezone.utc):%d/%m/%Y}")
    print("=" * 52)
    if not righe:
        print("\n  Nessuna visita registrata.")
        print("  Se il frontend aggiornato non e' ancora online, e' normale.")
        return 0

    print(f"\n  {'giorno':<12}{'sessioni':>10}{'richieste':>12}{'percorsi':>11}")
    print("  " + "-" * 45)
    for r in righe:
        print(f"  {r['giorno']:<12}{r['sessioni']:>10}"
              f"{r['richieste']:>12}{r['percorsi']:>11}")

    tot = sum(r["sessioni"] for r in righe)
    print(f"\n  totale sessioni nel periodo: {tot}")
    print("\n  Una sessione non e' una persona: chi apre il sito due volte in")
    print("  un giorno conta due volte, chi lascia la scheda aperta conta una")
    print("  volta sola. E' la stima piu' onesta che si possa fare senza")
    print("  seguire nessuno.")
    print("\n  Guarda `percorsi`, non `richieste`. Il frontend si ricarica da")
    print("  solo ogni minuto sul grafico giornaliero, quindi le richieste le")
    print("  fa anche una scheda dimenticata aperta. I percorsi distinti no.")
    print("  Aprire il sito e fermarsi li' costa cinque o sei percorsi.")
    return 0


def mostra_dettaglio(giorno: str) -> int:
    sessioni = dettaglio(giorno)
    print("=" * 52)
    print(f"  DETTAGLIO — {giorno}")
    print("=" * 52)
    if not sessioni:
        print("\n  Nessuna visita quel giorno.")
        return 0

    for s in sorted(sessioni, key=lambda x: -len(x["scelti"])):
        print(f"\n  sessione {s['sessione'][:12]}...  "
              f"{len(s['scelti'])} titoli scelti, "
              f"{s['percorsi']} percorsi, {s['richieste']} richieste")
        if s["scelti"]:
            print(f"      -> {', '.join(sorted(s['scelti']))}")
        else:
            print("      -> nessuno: ha visto la schermata iniziale e basta")
        for p, n in s["cosa"]:
            print(f"      {n:>5}x  {p}")
    return 0


if __name__ == "__main__":
    import argparse
    import os

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    except ImportError:
        pass

    ap = argparse.ArgumentParser(description="Quante sessioni distinte al giorno")
    ap.add_argument("--giorni", type=int, default=14,
                    help="quanti giorni indietro guardare (default 14)")
    ap.add_argument("--dettaglio", metavar="GIORNO",
                    help="cosa ha chiesto ogni sessione di quel giorno "
                         "(formato 2026-08-17)")
    args = ap.parse_args()
    if args.dettaglio:
        sys.exit(mostra_dettaglio(args.dettaglio))
    sys.exit(main(args.giorni))
