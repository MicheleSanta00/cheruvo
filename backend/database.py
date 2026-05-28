"""
database.py — con connection pooling.
"""
import os
import pandas as pd
from datetime import datetime, timedelta
import logging
import psycopg2
import psycopg2.pool
import psycopg2.extras

logger = logging.getLogger(__name__)

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        database_url = os.environ.get("DATABASE_URL", "")
        if not database_url:
            raise RuntimeError("DATABASE_URL non trovata nelle variabili d'ambiente")
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            dsn=database_url,
        )
        logger.info("Connection pool inizializzato (2–10 connessioni)")
    return _pool


def _get_connection():
    return get_pool().getconn()


def _release_connection(conn):
    get_pool().putconn(conn)


def init_database():
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS news (
                id               SERIAL PRIMARY KEY,
                ticker           TEXT    NOT NULL,
                source           TEXT,
                title            TEXT,
                summary          TEXT,
                published_date   TIMESTAMPTZ,
                url              TEXT,
                sentiment        REAL,
                relevance_score  REAL DEFAULT 1.0,
                UNIQUE(ticker, title, source)
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_news_ticker_date
            ON news (ticker, published_date DESC)
        """)
        conn.commit()
        cur.close()
    finally:
        _release_connection(conn)


class SuperNewsAnalyzer:

    def __init__(self, ticker: str, api_key: dict = None):
        self.ticker = ticker.upper()
        self.api_key = api_key or {}

    def get_data(self, days=30):
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        conn = _get_connection()
        try:
            df = pd.read_sql(
                "SELECT * FROM news WHERE ticker = %s AND published_date >= %s ORDER BY published_date DESC",
                conn, params=(self.ticker, cutoff),
            )
        finally:
            _release_connection(conn)
        return df

    def get_all_data(self):
        conn = _get_connection()
        try:
            df = pd.read_sql(
                "SELECT * FROM news WHERE ticker = %s ORDER BY published_date DESC",
                conn, params=(self.ticker,),
            )
        finally:
            _release_connection(conn)
        if df.empty:
            return df
        df["published_date"] = pd.to_datetime(df["published_date"], errors="coerce")
        return df.dropna(subset=["published_date"]).sort_values("published_date", ascending=False)