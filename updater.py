"""
updater.py — Eseguito da GitHub Actions ogni 6 ore.
Usa FinBERT (data/database.py) per sentiment più preciso.
"""
import os
import sys
import random

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


def get_all_tickers() -> list:
    """Recupera tutti i ticker già presenti nel DB."""
    from backend.database import get_pool as backend_pool
    pool = backend_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT ticker FROM news")
        tickers = [row[0] for row in cur.fetchall()]
        cur.close()
    finally:
        pool.putconn(conn)
    return tickers


if __name__ == "__main__":
    print("=" * 50)
    print("Cheruvo Updater — FinBERT mode")
    print("=" * 50)

    # Init DB
    init_database()

    # Raccogli ticker
    try:
        tickers_db = get_all_tickers()
    except Exception as e:
        print(f"Errore lettura ticker dal DB: {e}")
        tickers_db = []

    tickers = list(set(DEFAULT_TICKERS + tickers_db))

    # 3 ticker per run — FinBERT è più lento di VADER
    selected = random.sample(tickers, min(3, len(tickers)))
    print(f"Ticker selezionati: {selected}")
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