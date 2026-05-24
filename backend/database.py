"""
database.py — versione leggera per FastAPI su Render.
Solo lettura dal database. FinBERT gira su GitHub Actions via updater.py.
"""
import os
import pandas as pd
from datetime import datetime, timedelta
import logging
import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)


def _get_connection():
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL non trovata nelle variabili d'ambiente")
    return psycopg2.connect(database_url)


def init_database():
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id               SERIAL PRIMARY KEY,
            ticker           TEXT    NOT NULL,
            source           TEXT,
            title            TEXT,
            summary          TEXT,
            published_date   TEXT,
            url              TEXT,
            sentiment        REAL,
            relevance_score  REAL DEFAULT 1.0,
            UNIQUE(ticker, title, source)
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


class SuperNewsAnalyzer:

    def __init__(self, ticker: str, api_key: dict = None):
        self.ticker = ticker.upper()
        self.api_key = api_key or {}

    def get_data(self, days=30):
        conn = _get_connection()
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        df = pd.read_sql(
            "SELECT * FROM news WHERE ticker = %s AND published_date >= %s ORDER BY published_date DESC",
            conn, params=(self.ticker, cutoff),
        )
        conn.close()
        return df

    def get_all_data(self):
        conn = _get_connection()
        df = pd.read_sql(
            "SELECT * FROM news WHERE ticker = %s ORDER BY published_date DESC",
            conn, params=(self.ticker,),
        )
        conn.close()
        if df.empty:
            return df
        df["published_date"] = pd.to_datetime(df["published_date"], errors="coerce")
        return df.dropna(subset=["published_date"]).sort_values("published_date", ascending=False)

    def mega_fetch_silent(self):
        """
        Su Render non carichiamo FinBERT — troppa memoria.
        Il fetch reale avviene tramite updater.py su GitHub Actions ogni 6 ore.
        """
        print(f"[INFO] Fetch richiesto per {self.ticker} — verrà eseguito dal cron GitHub Actions.")
        return 0