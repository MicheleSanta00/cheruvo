"""
updater.py — Eseguito da GitHub Actions ogni 6 ore.
Usa quick_fetch (VADER + Alpha Vantage scores) — leggero, niente PyTorch.
"""
import os
import sys
import logging
from datetime import datetime, timezone

# Path setup
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, 'backend')
sys.path.insert(0, BACKEND_DIR)

from database import init_database, get_pool
from quick_fetch import quick_fetch
from alerts import check_and_send_alerts
from sentiment_groq import rescore_all_tickers
from onboarding import init_onboarding_table, check_and_send_onboarding_emails
# digest ed earnings vengono importati "pigramente" dentro i loro try/except più sotto:
# definiscono router FastAPI a livello di modulo, e non vogliamo che un loro import
# error blocchi il fetch news (la parte critica del cron).

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Ticker di default — aggiornati ad ogni run anche senza utenti registrati
DEFAULT_TICKERS = [
    # USA
    'NVDA', 'AAPL', 'TSLA', 'MSFT', 'GOOGL', 'META', 'AMD', 'AMZN',
    # Italia
    'ENI.MI', 'ENEL.MI', 'ISP.MI', 'UCG.MI', 'STM.MI', 'RACE.MI',
    # Europa
    'LVMH.PA', 'SAP.DE', 'ASML.AS', 'SHEL.L',
    # Criptovalute. Aggiunte il 4 agosto 2026 dopo aver misurato che su GDELT
    # rendono circa otto volte più dei titoli italiani, sulla stessa licenza.
    # Vantaggio in più: scambiano 24 ore su 24, quindi il grafico della seduta
    # non resta immobile la sera e nel fine settimana come per le borse.
    'BTC-USD', 'ETH-USD', 'SOL-USD', 'XRP-USD', 'ADA-USD', 'DOGE-USD',
    'AVAX-USD', 'LINK-USD', 'DOT-USD', 'LTC-USD', 'UNI-USD', 'ATOM-USD',
    'XLM-USD', 'NEAR-USD', 'BCH-USD', 'SHIB-USD',
]

# Quanti ticker processare per run.
#
# Era 12 su 18 di default: sei titoli restavano fuori a ogni giro, e quelli
# aggiunti dagli utenti in watchlist competevano per gli slot avanzati. Il
# risultato era una watchlist con metà delle righe senza dati.
# Con 24 ci stanno tutti i default più le watchlist di un piccolo numero di
# utenti. Il costo è tempo, non denaro: GDELT impone 5 secondi tra le
# chiamate, quindi ~2 minuti, ben dentro il timeout di 12 minuti del workflow.
# Alzato a 40 con l'arrivo delle criptovalute. Il costo in chiamate NON
# cresce in proporzione: le 16 crypto viaggiano su UNA interrogazione
# raggruppata, non su sedici. Restiamo dentro il timeout del workflow.
MAX_TICKERS = 40

# Il ciclo di raccolta si ferma da solo dopo questi secondi, lasciando il
# resto del tempo alle cose che vengono DOPO: controllo di salute, alert,
# digest, earnings. Il workflow ha 12 minuti totali: qui ne usiamo 8 e ne
# restano 4, che sono abbondanti perché il resto non fa chiamate lente.
LIMITE_FETCH_SECONDI = 8 * 60


def get_watchlist_tickers() -> list[str]:
    """
    Recupera tutti i ticker presenti nelle watchlist degli utenti.
    Così i ticker personalizzati vengono aggiornati automaticamente.
    """
    try:
        pool = get_pool()
        conn = pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT ticker FROM watchlist ORDER BY ticker")
            tickers = [r[0] for r in cur.fetchall()]
            cur.close()
        finally:
            pool.putconn(conn)
        logger.info("Watchlist tickers: %s", tickers)
        return tickers
    except Exception as e:
        logger.warning("Impossibile leggere watchlist: %s", e)
        return []


def get_tickers_by_priority() -> list[str]:
    """
    Ordina tutti i ticker (watchlist + default) per priorità:
    quelli con news più vecchie vengono prima.
    I ticker mai fetchati hanno la priorità massima.
    """
    watchlist = get_watchlist_tickers()
    # Unione: watchlist + default senza duplicati, mantenendo l'ordine
    all_tickers = list(dict.fromkeys(watchlist + DEFAULT_TICKERS))

    try:
        pool = get_pool()
        conn = pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT ticker, MAX(published_date) as last_news
                FROM news
                GROUP BY ticker
                ORDER BY last_news ASC NULLS FIRST
            """)
            rows = cur.fetchall()
            cur.close()
        finally:
            pool.putconn(conn)

        db_tickers_ordered = [r[0] for r in rows]
        db_set = set(db_tickers_ordered)

        # Prima i mai-fetchati, poi quelli più vecchi per data
        never_fetched = [t for t in all_tickers if t not in db_set]
        in_db_ordered = [t for t in db_tickers_ordered if t in set(all_tickers)]

        return never_fetched + in_db_ordered

    except Exception as e:
        logger.warning("Errore priorità ticker: %s — uso lista piatta", e)
        return all_tickers


if __name__ == "__main__":
    start = datetime.now(timezone.utc)
    logger.info("=" * 55)
    logger.info("Cheruvo Updater — avviato alle %s", start.strftime("%Y-%m-%d %H:%M UTC"))
    logger.info("=" * 55)

    # Init DB (crea tabelle se non esistono)
    init_database()
    init_onboarding_table()

    # Raccogli ticker ordinati per priorità
    try:
        tickers = get_tickers_by_priority()
    except Exception as e:
        logger.error("Errore lettura ticker: %s — uso DEFAULT", e)
        tickers = DEFAULT_TICKERS[:]

    selected = tickers[:MAX_TICKERS]
    logger.info("Ticker da aggiornare (%d): %s", len(selected), selected)

    total_new = 0
    errors = 0
    saltati = 0
    for ticker in selected:
        # Freno di sicurezza. Il workflow viene ucciso a 12 minuti esatti, e
        # quando succede NON viene salvato niente: né le notizie, né il
        # controllo di salute, né gli alert, perché sta tutto dopo questo
        # ciclo. È successo davvero il 5 agosto 2026, con un giro terminato a
        # 12m16s e zero risultati.
        #
        # Meglio aggiornare venticinque ticker e finire, che tentarne quaranta
        # e perdere tutto. Quelli saltati hanno la precedenza al giro dopo,
        # perché la lista è ordinata per notizia più vecchia.
        trascorso = (datetime.now(timezone.utc) - start).total_seconds()
        if trascorso > LIMITE_FETCH_SECONDI:
            saltati = len(selected) - selected.index(ticker)
            logger.warning("Tempo quasi esaurito (%.0fs): salto gli ultimi %d ticker "
                           "per arrivare in fondo al resto", trascorso, saltati)
            break

        logger.info("─── %s ───", ticker)
        try:
            count = quick_fetch(ticker)
            total_new += count
            logger.info("✓ %s: %d nuove news", ticker, count)
        except Exception as e:
            logger.error("✗ Errore su %s: %s", ticker, e)
            errors += 1

    logger.info("─" * 55)
    logger.info("Fetch completato: %d nuove news, %d errori, %d ticker saltati "
                "per tempo, su %d in lista",
                total_new, errors, saltati, len(selected))

    # Controllo salute: registra la copertura del giorno e avvisa se peggiora.
    # Sta QUI, subito dopo il fetch, perché è il fetch che vogliamo sorvegliare.
    try:
        from salute import controlla_e_registra
        controlla_e_registra()
    except Exception as e:
        logger.error("Errore controllo salute: %s", e)

    # Ri-classifica le news non-AV con Groq per score di qualità finanziaria
    if os.environ.get("GROQ_API_KEY"):
        logger.info("Ri-classificazione sentiment con Groq (news non-AV)...")
        try:
            rescored = rescore_all_tickers(selected)
            logger.info("Groq: %d articoli aggiornati", rescored)
        except Exception as e:
            logger.error("Errore Groq rescore: %s", e)
    else:
        logger.warning("GROQ_API_KEY non trovata — skip rescore")

    # Alert PRO (invia email se ci sono movimenti significativi)
    logger.info("Controllo alert sentiment PRO...")
    try:
        check_and_send_alerts()
    except Exception as e:
        logger.error("Errore alert: %s", e)

    # Email onboarding giorno 3 e 7
    logger.info("Controllo email onboarding (giorno 3 e 7)...")
    try:
        check_and_send_onboarding_emails()
    except Exception as e:
        logger.error("Errore onboarding emails: %s", e)

    # Digest settimanale (parte solo di lunedì, una volta per utente)
    logger.info("Controllo digest settimanale...")
    try:
        from digest import init_digest_tables, send_weekly_digests
        init_digest_tables()
        send_weekly_digests()
    except Exception as e:
        logger.error("Errore digest: %s", e)

    # Date earnings (aggiorna solo quelle più vecchie di 24h)
    logger.info("Aggiornamento calendario earnings...")
    try:
        from earnings import init_earnings_tables, refresh_earnings
        init_earnings_tables()
        refresh_earnings(selected)
    except Exception as e:
        logger.error("Errore earnings: %s", e)

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    logger.info("Done in %.1fs", elapsed)

    # Exit code non-zero se troppi errori (GitHub Actions lo segnala come failed)
    if errors > len(selected) // 2:
        logger.error("Troppi errori (%d/%d) — exit 1", errors, len(selected))
        sys.exit(1)
