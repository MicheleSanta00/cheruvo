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
        # Da dove viene lo score: 'vader' (fallback), 'av' (Alpha Vantage), 'llm' (Groq).
        # Serve a ri-classificare ogni articolo UNA volta sola e a non degradare
        # score di qualità con fallback successivi.
        cur.execute("ALTER TABLE news ADD COLUMN IF NOT EXISTS score_source TEXT DEFAULT 'vader'")

        # La lingua originale dell'articolo, quando la fonte la dichiara.
        #
        # `ingest_grezzo` la leggeva da GDELT (srclc:tur, srclc:rus) e la
        # metteva nel dizionario da salvare fin dall'inizio, ma `save_news` non
        # la scriveva e la colonna non esisteva: il dato si raccoglieva e si
        # buttava a ogni riga, da agosto.
        #
        # Serve perche' meta' dell'archivio viene dal feed tradotto, che
        # restituisce il titolo nella lingua del giornale. Chi apre Bitcoin si
        # trova "Bitcoin'de haftalik kayip yuzde 3'u asti" e non sa nemmeno
        # perche' non lo capisce. Dirgli che e' turco non risolve la lettura,
        # ma toglie il sospetto che il sito sia rotto.
        #
        # Resta NULL sulle righe vecchie e su quelle che arrivano da fonti che
        # non la dichiarano: in quel caso non si mostra niente, invece di
        # tirare a indovinare.
        cur.execute("ALTER TABLE news ADD COLUMN IF NOT EXISTS lingua TEXT")
        conn.commit()
        cur.close()
    finally:
        _release_connection(conn)


def _leggi(sql: str, params: tuple) -> "pd.DataFrame":
    """
    Una query che torna un DataFrame, senza passare da `pd.read_sql`.

    PERCHE' NON pd.read_sql

    pandas dichiara di supportare solo SQLAlchemy, un URI o sqlite3, e su una
    connessione psycopg2 avvisa a ogni chiamata che "other DBAPI2 objects are
    not tested". Funzionava lo stesso, perche' internamente pandas fa
    esattamente quello che c'e' scritto qui sotto: cursore, fetchall, colonne
    da `cur.description`.

    Due motivi per farlo a mano.

    Il primo e' che quell'avviso compariva a ogni giro di test, e un avviso
    che si impara a saltare rende invisibili quelli veri: e' rumore che
    consuma attenzione.

    Il secondo e' che il supporto ai DBAPI2 e' dichiarato non testato, quindi
    puo' sparire in una versione maggiore di pandas. Se sparisce, `read_sql`
    smette di avvisare e comincia a sollevare, e i due endpoint che ci passano
    sono /api/news e /api/sentiment, cioe' quelli che apre chiunque.

    Il comportamento e' identico, colonne comprese: `cur.description` c'e'
    anche quando non torna nessuna riga, quindi un risultato vuoto resta un
    DataFrame con le sue colonne e non un DataFrame senza niente.
    """
    conn = _get_connection()
    try:
        cur = conn.cursor()
        try:
            cur.execute(sql, params)
            righe = cur.fetchall()
            colonne = [d[0] for d in cur.description]
        finally:
            cur.close()
    finally:
        _release_connection(conn)
    return pd.DataFrame(righe, columns=colonne)


class SuperNewsAnalyzer:

    def __init__(self, ticker: str, api_key: dict = None):
        self.ticker = ticker.upper()
        self.api_key = api_key or {}

    def get_data(self, days=30):
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        return _leggi(
            "SELECT * FROM news WHERE ticker = %s AND published_date >= %s "
            "ORDER BY published_date DESC",
            (self.ticker, cutoff),
        )

    def get_all_data(self):
        df = _leggi(
            "SELECT * FROM news WHERE ticker = %s ORDER BY published_date DESC",
            (self.ticker,),
        )
        if df.empty:
            return df
        df["published_date"] = pd.to_datetime(df["published_date"], errors="coerce")
        return df.dropna(subset=["published_date"]).sort_values("published_date", ascending=False)