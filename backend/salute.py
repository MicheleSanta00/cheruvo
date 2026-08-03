"""
salute.py — Cheruvo si misura da solo.

Perché esiste. Fra il 19 luglio e il 3 agosto 2026 la raccolta notizie è passata
da 468 articoli ogni 48 ore a 55, e i titoli italiani coperti da 3 a zero.
Nessuno se n'è accorto per due settimane. Non per distrazione: perché il
prodotto non conservava traccia di come stava ieri, quindi non c'era modo di
vedere che stava peggiorando. Il calo è emerso solo grazie a una copia vecchia
rimasta per caso in una cache.

Un sistema che dipende da fonti esterne e non si misura è un sistema che
scoprirà i propri guasti dagli utenti. Questo file registra ogni giorno quattro
numeri e grida quando peggiorano.

Nessun dato personale: solo conteggi aggregati.
"""
import logging
import os
from datetime import datetime, timezone

from database import get_pool

logger = logging.getLogger(__name__)

# Sotto questa frazione della media dei giorni precedenti si considera un calo
# anomalo. 0.5 = "oggi vale meno della metà del normale".
SOGLIA_ALLARME = 0.5
GIORNI_CONFRONTO = 7
# Sotto questo numero di articoli non allarmiamo: nel fine settimana i mercati
# sono chiusi e le redazioni scrivono poco, quindi un calo è fisiologico.
MINIMO_SIGNIFICATIVO = 20


def init_tabella_salute() -> None:
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS storico_copertura (
                giorno              DATE PRIMARY KEY,
                titoli_totali       INTEGER NOT NULL,
                titoli_con_notizie  INTEGER NOT NULL,
                articoli_48h        INTEGER NOT NULL,
                titoli_italiani     INTEGER NOT NULL,
                rilevato_il         TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.commit()
        cur.close()
    finally:
        pool.putconn(conn)


def misura() -> dict:
    """Fotografia della copertura in questo momento."""
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(DISTINCT ticker) FROM news")
        titoli_totali = cur.fetchone()[0] or 0

        cur.execute("""
            SELECT COUNT(DISTINCT ticker), COUNT(*)
            FROM news
            WHERE published_date >= now() - interval '48 hours'
        """)
        titoli_con_notizie, articoli = cur.fetchone()

        # I titoli italiani sono il motivo per cui Cheruvo esiste in italiano:
        # vanno contati a parte, altrimenti il crollo si nasconde dentro la
        # media tenuta su dai titoli americani. È esattamente ciò che è
        # successo: il totale sembrava calare "un po'", l'Italia era a zero.
        # Il pattern passa come parametro: scritto dentro la stringa, il segno
        # di percentuale verrebbe interpretato da psycopg2 come segnaposto e il
        # comportamento cambierebbe a seconda che la query abbia parametri o no.
        cur.execute("""
            SELECT COUNT(DISTINCT ticker)
            FROM news
            WHERE published_date >= now() - interval '48 hours'
              AND ticker LIKE %s
        """, ("%.MI",))
        titoli_italiani = cur.fetchone()[0] or 0
        cur.close()
    finally:
        pool.putconn(conn)

    return {
        "titoli_totali": titoli_totali,
        "titoli_con_notizie": titoli_con_notizie or 0,
        "articoli_48h": articoli or 0,
        "titoli_italiani": titoli_italiani,
    }


def salva(m: dict) -> None:
    """Una riga al giorno. Se il cron gira più volte, l'ultima sovrascrive."""
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO storico_copertura
                (giorno, titoli_totali, titoli_con_notizie, articoli_48h, titoli_italiani)
            VALUES (CURRENT_DATE, %s, %s, %s, %s)
            ON CONFLICT (giorno) DO UPDATE SET
                titoli_totali      = EXCLUDED.titoli_totali,
                titoli_con_notizie = EXCLUDED.titoli_con_notizie,
                articoli_48h       = EXCLUDED.articoli_48h,
                titoli_italiani    = EXCLUDED.titoli_italiani,
                rilevato_il        = now()
        """, (m["titoli_totali"], m["titoli_con_notizie"],
              m["articoli_48h"], m["titoli_italiani"]))
        conn.commit()
        cur.close()
    finally:
        pool.putconn(conn)


def _media_precedente() -> dict | None:
    """Media dei giorni precedenti (oggi escluso). None se non c'è storia."""
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT AVG(articoli_48h), AVG(titoli_con_notizie), AVG(titoli_italiani),
                   COUNT(*)
            FROM (
                SELECT * FROM storico_copertura
                WHERE giorno < CURRENT_DATE
                ORDER BY giorno DESC LIMIT %s
            ) AS recenti
        """, (GIORNI_CONFRONTO,))
        art, tit, ita, quanti = cur.fetchone()
        cur.close()
    finally:
        pool.putconn(conn)
    if not quanti:
        return None
    return {"articoli_48h": float(art or 0),
            "titoli_con_notizie": float(tit or 0),
            "titoli_italiani": float(ita or 0),
            "giorni": quanti}


def _avvisa(righe: list[str]) -> None:
    """
    Manda l'allarme per email. Un log non basta: la volta scorsa il problema è
    rimasto invisibile due settimane proprio perché nessuno andava a leggere i
    log. Un avviso deve arrivare da solo, non aspettare di essere cercato.
    """
    destinatario = os.environ.get("ADMIN_EMAIL", "").strip()
    if not destinatario or not os.environ.get("RESEND_API_KEY", "").strip():
        logger.warning("Salute: nessun ADMIN_EMAIL configurato, avviso solo nei log")
        return
    try:
        import resend
        resend.api_key = os.environ["RESEND_API_KEY"]
        corpo = "".join(f"<li>{r}</li>" for r in righe)
        resend.Emails.send({
            "from": os.environ.get("FROM_EMAIL", "Cheruvo <noreply@cheruvo.com>"),
            "to": destinatario,
            "subject": "Cheruvo: la copertura notizie è calata",
            "html": ("<p>Il controllo automatico ha rilevato un peggioramento "
                     "della raccolta notizie.</p>"
                     f"<ul>{corpo}</ul>"
                     "<p>Le cause abituali sono due: GDELT che risponde 429, "
                     "oppure una fonte che ha smesso di rispondere. "
                     "Cerca <code>429</code> e <code>GDELT</code> nei log del cron.</p>"),
        })
        logger.info("Salute: avviso inviato a %s", destinatario)
    except Exception as e:
        logger.error("Salute: invio avviso fallito (%s)", e)


def controlla_e_registra() -> dict:
    """
    Misura, salva, confronta con i giorni precedenti e avvisa se peggiora.
    Chiamata dal cron. Non solleva: un problema qui non deve fermare il fetch.
    """
    try:
        init_tabella_salute()
        m = misura()
        precedente = _media_precedente()   # PRIMA di salvare, così oggi non entra nella media
        salva(m)

        logger.info("Salute: %d titoli con notizie (%d italiani), %d articoli in 48h, "
                    "%d titoli in archivio",
                    m["titoli_con_notizie"], m["titoli_italiani"],
                    m["articoli_48h"], m["titoli_totali"])

        if not precedente:
            logger.info("Salute: primo rilevamento, nessun confronto possibile")
            return m

        allarmi = []
        if (precedente["articoli_48h"] >= MINIMO_SIGNIFICATIVO
                and m["articoli_48h"] < precedente["articoli_48h"] * SOGLIA_ALLARME):
            allarmi.append(
                f"Articoli in 48 ore: {m['articoli_48h']} contro una media di "
                f"{precedente['articoli_48h']:.0f} negli ultimi {precedente['giorni']} giorni")
        if (precedente["titoli_con_notizie"] >= 4
                and m["titoli_con_notizie"] < precedente["titoli_con_notizie"] * SOGLIA_ALLARME):
            allarmi.append(
                f"Titoli coperti: {m['titoli_con_notizie']} contro una media di "
                f"{precedente['titoli_con_notizie']:.0f}")
        # L'Italia a zero è un allarme sempre, anche senza confronto: è la
        # promessa specifica del prodotto e non ha una soglia sotto cui è normale.
        if precedente["titoli_italiani"] >= 1 and m["titoli_italiani"] == 0:
            allarmi.append("Nessun titolo italiano ha notizie nelle ultime 48 ore")

        if allarmi:
            for a in allarmi:
                logger.warning("SALUTE — %s", a)
            _avvisa(allarmi)
        else:
            logger.info("Salute: copertura in linea con i giorni precedenti")
        return m
    except Exception as e:
        logger.error("Salute: controllo fallito (%s)", e)
        return {}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(controlla_e_registra())
