"""
updater.py — Eseguito da GitHub Actions ogni 6 ore.
Aggiorna le news e manda gli alert agli utenti PRO.
"""
import os
import sys
import random

# Assicura che Python trovi i moduli in backend/
BASE_DIR = os.path.dirname(__file__)
BACKEND_DIR = os.path.join(BASE_DIR, 'backend')
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, BASE_DIR)

# Usa il quick_fetch del backend (VADER, leggero)
from quick_fetch import quick_fetch
from alerts import check_and_send_alerts
from database import get_pool, init_database

DEFAULT_TICKERS = [
    # USA
    'NVDA', 'AAPL', 'TSLA', 'MSFT', 'GOOGL', 'META', 'AMD', 'AMZN',
    # Italia
    'ENI.MI', 'ENEL.MI', 'ISP.MI', 'UCG.MI', 'STM.MI', 'RACE.MI', 'TIT.MI', 'BAMI.MI',
    # Europa
    'LVMH.PA', 'SAP.DE', 'ASML.AS', 'NESN.SW', 'SHEL.L', 'NOVN.SW',
]


def get_all_tickers() -> list[str]:
    pool = get_pool()
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
    init_database()

    tickers_db = get_all_tickers()
    tickers = list(set(DEFAULT_TICKERS + tickers_db))

    # 3 ticker per run per evitare timeout GitHub Actions
    selected = random.sample(tickers, min(3, len(tickers)))
    print(f"Ticker selezionati: {selected}")

    for ticker in selected:
        print(f"Aggiornando {ticker}...")
        try:
            count = quick_fetch(ticker)
            print(f"  ✓ {ticker}: {count} nuove news")
        except Exception as e:
            print(f"  ✗ Errore su {ticker}: {e}")

    print("\nControllo alert PRO...")
    check_and_send_alerts()
    print("Done.")