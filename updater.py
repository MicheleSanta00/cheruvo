"""
updater.py — Eseguito da GitHub Actions ogni 8 ore.
Usa FinBERT (data/database.py) per sentiment più preciso.
"""
import os
import sys
from datetime import datetime, timezone

# Aggiunge i path necessari
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, 'backend')
DATA_DIR    = os.path.join(BASE_DIR, 'data')

sys.path.insert(0, DATA_DIR)     # data/database.py  (FinBERT)
sys.path.insert(0, BACKEND_DIR)  # backend/alerts.py, backend/database.py
sys.path.insert(0, BASE_DIR)

from database import SuperNewsAnalyzer, init_database, get_pool   # data/database.py
from alerts import check_and_send_alerts                           # backend/alerts.py

API_KEY = {
    "ALPHA_VANTAGE": os.environ.get("ALPHA_VANTAGE", ""),
    "NEWSAPI":       os.environ.get("NEWSAPI", ""),
    "FMP":           os.environ.get("FMP", ""),
    "REDDIT": {
        "client_id":     os.environ.get("REDDIT_CLIENT_ID", ""),
        "client_secret": os.environ.get("REDDIT_CLIENT_SECRET", ""),
    },
}

DEFAULT_TICKERS = [
    # USA
    'NVDA', 'AAPL', 'TSLA', 'MSFT', 'GOOGL', 'META', 'AMD', 'AMZN',
    # Italia
    'ENI.MI', 'ENEL.MI', 'ISP.MI', 'UCG.MI', 'STM.MI', 'RACE.MI',
    # Europa
    'LVMH.PA', 'SAP.DE', 'ASML.AS', 'SHEL.L',
]


def get_tickers_by_priority() -> list[str]:
    """
    Restituisce tutti i ticker ordinati per priorità di aggiornamento:
    quelli aggiornati meno di recente vengono prima.
    I ticker DEFAULT che non hanno mai news vengono aggiunti in fondo.
    """
    conn = _get_raw_conn()
    try:
        cur = conn.cursor()
        # Ticker nel DB con data dell'ultima news (proxy di "ultimo aggiornamento")
        cur.execute("""
            SELECT ticker, MAX(published_date) as last_news
            FROM news
            GROUP BY ticker
            ORDER BY last_news ASC NULLS FIRST
        """)
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    db_tickers = [r[0] for r in rows]
    # Aggiunge i DEFAULT che non sono ancora nel DB (mai fetchati)
    missing = [t for t in DEFAULT_TICKERS if t not in db_tickers]
    return missing + db_tickers  # i mai-fetchati hanno la priorità massima


def _get_raw_conn():
    """Connessione diretta (senza pool) — usata solo nell'updater batch."""
    import psycopg2
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL non trovata")
    return psycopg2.connect(database_url)


if __name__ == "__main__":
    print("=" * 50)
    print("Cheruvo Updater — FinBERT mode (priority queue)")
    print("=" * 50)

    # Init DB
    init_database()

    # Raccogli ticker ordinati per priorità
    try:
        tickers = get_tickers_by_priority()
    except Exception as e:
        print(f"Errore lettura ticker dal DB: {e} — uso DEFAULT")
        tickers = DEFAULT_TICKERS[:]

    # 5 ticker per run con sistema a priorità
    # (quelli meno aggiornati vengono sempre prima)
    selected = tickers[:5]
    print(f"Ticker selezionati (priorità): {selected}")
    print(f"(FinBERT verrà caricato al primo ticker — ~30s)\n")

    for ticker in selected:
        print(f"\n{'─'*40}")
        print(f"Aggiornando {ticker} con FinBERT...")
        try:
            analyzer = SuperNewsAnalyzer(ticker, API_KEY)
            count = analyzer.mega_fetch_silent()
            print(f"✓ {ticker}: {count} nuove news salvate")
        except Exception as e:
            print(f"✗ Errore su {ticker}: {e}")

    print(f"\n{'─'*40}")
    print("Controllo alert PRO...")
    try:
        check_and_send_alerts()
    except Exception as e:
        print(f"Errore alert: {e}")

    print("\nDone.")