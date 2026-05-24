import os
import sys
import psycopg2

sys.path.insert(0, os.path.dirname(__file__))

from data.database import SuperNewsAnalyzer

DEFAULT_TICKERS = ['NVDA', 'AAPL', 'TSLA', 'MSFT', 'GOOGL', 'META', 'AMD', 'AMZN']

def get_all_tickers():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT ticker FROM news")
    tickers = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return tickers

if __name__ == "__main__":
    tickers_db = get_all_tickers()
    tickers = list(set(DEFAULT_TICKERS + tickers_db))
    
    if not tickers:
        print("Nessun ticker trovato.")
    
    for ticker in tickers:
        print(f"Aggiornando {ticker}...")
        try:
            analyzer = SuperNewsAnalyzer(ticker, os.environ["ALPHA_VANTAGE"])
            analyzer.mega_fetch_silent()
            print(f"  ✓ {ticker} aggiornato")
        except Exception as e:
            print(f"  ✗ Errore su {ticker}: {e}")