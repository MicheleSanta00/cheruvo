import os
import pandas as pd
from datetime import datetime, timedelta
import requests
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import feedparser
from bs4 import BeautifulSoup
import torch
import praw
import time
import logging
import psycopg2
import psycopg2.extras
from psycopg2 import sql

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FinBERT
# ---------------------------------------------------------------------------

class FinBERTSentiment:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
            cls._instance.model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
            cls._instance.model.eval()
            print("FinBERT loaded!")
        return cls._instance

    def predict(self, text):
        if not text or len(text.strip()) < 10:
            return 0.0
        inputs = self.tokenizer(
            text, return_tensors="pt", truncation=True, padding=True, max_length=512
        )
        with torch.no_grad():
            outputs = self.model(**inputs)
            probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
            scores = probs.detach().numpy()[0]
        return float(max(-1.0, min(1.0, scores[0] - scores[1])))


_finbert_instance = None

def get_finbert():
    global _finbert_instance
    if _finbert_instance is None:
        _finbert_instance = FinBERTSentiment()
    return _finbert_instance


# ---------------------------------------------------------------------------
# Connessione Supabase (PostgreSQL)
# ---------------------------------------------------------------------------

def _get_connection():
    """Restituisce una connessione a Supabase via DATABASE_URL."""
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL non trovata nelle variabili d'ambiente / secrets")
    return psycopg2.connect(database_url)


def init_database():
    """Crea la tabella se non esiste (idempotente)."""
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


# ---------------------------------------------------------------------------
# SuperNewsAnalyzer
# ---------------------------------------------------------------------------

class SuperNewsAnalyzer:

    def __init__(self, ticker, api_key, ui=None):
        self.ticker = ticker.upper()
        self.api_key = api_key
        self.ui = ui or _SilentUI()
        init_database()

    def _info(self, msg):    self.ui.info(msg)
    def _success(self, msg): self.ui.success(msg)
    def _warning(self, msg): self.ui.warning(msg)
    def _error(self, msg):   self.ui.error(msg)

    def _format_date(self, date_str):
        if not date_str:
            return ''
        try:
            from dateutil import parser
            return parser.parse(str(date_str)).strftime('%Y-%m-%d')
        except Exception:
            s = str(date_str)
            return s[:10] if len(s) >= 10 else ''

    # ------------------------------------------------------------------
    # Fetch da ogni fonte
    # ------------------------------------------------------------------

    def fetch_alpha_vantage(self):
        news_list = []
        try:
            params = {
                'function': 'NEWS_SENTIMENT',
                'tickers': self.ticker,
                'limit': 100,
                'apikey': self.api_key.get('ALPHA_VANTAGE', 'demo').strip(),
                'sort': 'LATEST'
            }
            response = requests.get("https://www.alphavantage.co/query", params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            if 'feed' not in data or not data['feed']:
                self._info("Alpha Vantage: nessuna news")
                return []
            finbert = get_finbert()
            for item in data['feed'][:50]:
                title = item.get('title', '').strip()
                summary = item.get('summary', '').strip()
                if not title:
                    continue
                av_sentiment = float(item.get('overall_sentiment_score', 0))
                try:
                    finbert_sentiment = finbert.predict(f"{title} {summary}")
                except Exception:
                    finbert_sentiment = av_sentiment
                news_list.append({
                    'source': item.get('source', 'Alpha Vantage'),
                    'title': title,
                    'summary': (summary[:250] + '...') if len(summary) > 250 else summary,
                    'published_date': self._format_date(item.get('time_published')),
                    'url': item.get('url', ''),
                    'sentiment': finbert_sentiment,
                })
            self._success(f"Alpha Vantage: {len(news_list)} news")
        except Exception as e:
            self._warning(f"Alpha Vantage: {str(e)[:80]}")
        return news_list

    def fetch_newsapi(self):
        news_list = []
        try:
            from newsapi import NewsApiClient
            api_key = self.api_key.get('NEWSAPI', '').strip()
            if not api_key:
                self._warning("NewsAPI: API key vuota")
                return []
            api = NewsApiClient(api_key=api_key)
            finbert = get_finbert()
            for query in [f'{self.ticker} stock', f'{self.ticker} earnings']:
                try:
                    articles = api.get_everything(
                        q=query, language='en', sort_by='publishedAt', page_size=20
                    ).get('articles', [])
                    for article in articles[:10]:
                        title = (article.get('title') or '').strip()
                        source = (article.get('source') or {}).get('name', 'Unknown')
                        description = (article.get('description') or '').strip()
                        url = article.get('url', '')
                        if not title or len(title) < 10 or not url:
                            continue
                        news_list.append({
                            'source': source,
                            'title': title,
                            'summary': (description or title)[:250],
                            'published_date': self._format_date(article.get('publishedAt')),
                            'url': url,
                            'sentiment': finbert.predict(f"{title} {description}"),
                        })
                except Exception:
                    continue
            seen, unique = set(), []
            for n in news_list:
                key = n['url'] or n['title'].lower()
                if key not in seen:
                    seen.add(key)
                    unique.append(n)
            self._success(f"NewsAPI: {len(unique)} news")
            return unique[:50]
        except Exception as e:
            self._error(f"NewsAPI: {str(e)[:80]}")
        return news_list

    def fetch_fmp_news(self):
        news_list = []
        try:
            api_key = self.api_key.get('FMP', '').strip()
            if not api_key:
                self._error("FMP: API key mancante")
                return []
            response = requests.get(
                "https://financialmodelingprep.com/api/v3/stock_news",
                params={'ticker': self.ticker, 'limit': 50, 'apikey': api_key},
                timeout=15
            )
            if response.status_code == 403:
                self._error("FMP 403: API key non valida")
                return []
            finbert = get_finbert()
            for item in response.json():
                title = item.get('title', '').strip()
                if not title:
                    continue
                text = item.get('text', '')
                news_list.append({
                    'source': 'FinancialModelingPrep',
                    'title': title,
                    'summary': (text or title)[:250],
                    'published_date': self._format_date(item.get('publishedDate')),
                    'url': item.get('url', ''),
                    'sentiment': finbert.predict(f"{title} {text}"),
                })
            self._success(f"FMP: {len(news_list)} notizie")
        except Exception as e:
            self._error(f"FMP: {str(e)[:80]}")
        return news_list

    def fetch_rss(self):
        SOURCE_NAMES = {
            f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={self.ticker}&region=US&lang=en-US": "Yahoo Finance RSS",
            "https://www.cnbc.com/id/100003114/device/rss/rss.html": "CNBC",
            "https://feeds.marketwatch.com/marketwatch/topstories/": "MarketWatch",
        }
        news_list = []
        finbert = get_finbert()
        for feed_url, source_name in SOURCE_NAMES.items():
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:20]:
                    title = entry.get('title', '').strip()
                    if not title:
                        continue
                    summary = entry.get('summary', '')
                    news_list.append({
                        'source': source_name,
                        'title': title,
                        'summary': summary[:250],
                        'published_date': self._format_date(entry.get('published', '')),
                        'url': entry.get('link', ''),
                        'sentiment': finbert.predict(f"{title} {summary}"),
                    })
            except Exception as e:
                self._warning(f"RSS {source_name}: {str(e)[:60]}")
        return news_list

    def fetch_yahoo(self):
        try:
            url = f"https://finance.yahoo.com/quote/{self.ticker}/news"
            response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            if response.status_code != 200:
                self._warning(f"Yahoo Finance: status {response.status_code}")
                return []
            soup = BeautifulSoup(response.text, "html.parser")
            articles = soup.select("h3 a")
            if not articles:
                return []
            finbert = get_finbert()
            news_list = []
            for a in articles[:20]:
                title = a.text.strip()
                href = a.get('href', '')
                if not title or not href:
                    continue
                link = ("https://finance.yahoo.com" + href) if href.startswith('/') else href
                news_list.append({
                    'source': 'Yahoo Finance',
                    'title': title,
                    'summary': title,
                    'published_date': '',
                    'url': link,
                    'sentiment': finbert.predict(title),
                })
            return news_list
        except Exception as e:
            self._warning(f"Yahoo Finance: {str(e)[:80]}")
            return []

    def fetch_reddit(self):
        news_list = []
        try:
            reddit_config = self.api_key.get('REDDIT', {})
            if not reddit_config.get('client_id'):
                self._warning("Reddit: configurazione API mancante")
                return []
            reddit = praw.Reddit(
                client_id=reddit_config['client_id'],
                client_secret=reddit_config['client_secret'],
                user_agent=f"NewsAnalyzer-{self.ticker}"
            )
            finbert = get_finbert()
            for sub in ['stocks', 'investing', 'wallstreetbets']:
                for post in reddit.subreddit(sub).new(limit=15):
                    if self.ticker.lower() in post.title.lower():
                        text = f"{post.title} {post.selftext[:300]}"
                        news_list.append({
                            'source': f'Reddit/r/{sub}',
                            'title': post.title,
                            'summary': (post.selftext[:250] + '...') if post.selftext else post.title,
                            'published_date': self._format_date(
                                datetime.utcfromtimestamp(post.created_utc).strftime('%Y-%m-%d')
                            ),
                            'url': f"https://reddit.com{post.permalink}",
                            'sentiment': finbert.predict(text),
                        })
            self._success(f"Reddit: {len(news_list)} post")
            return news_list[:15]
        except Exception as e:
            self._warning(f"Reddit: {str(e)[:60]}")
            return []

    # ------------------------------------------------------------------
    # Salvataggio su Supabase
    # ------------------------------------------------------------------

    def save_news_to_db(self, news_list):
        if not news_list:
            return 0
        conn = _get_connection()
        cur = conn.cursor()

        cur.execute(
            "SELECT lower(trim(title)), lower(trim(source)) FROM news WHERE ticker = %s",
            (self.ticker,)
        )
        existing = set(cur.fetchall())

        new_entries = []
        for news in news_list:
            title_norm = news['title'].lower().strip()
            source_norm = news['source'].lower().strip()
            if (title_norm, source_norm) not in existing:
                new_entries.append((
                    self.ticker,
                    news['source'],
                    news['title'].strip(),
                    (news.get('summary') or '').strip(),
                    news['published_date'],
                    news['url'],
                    float(news['sentiment']),
                ))
                existing.add((title_norm, source_norm))

        if new_entries:
            try:
                psycopg2.extras.execute_values(cur, """
                    INSERT INTO news (ticker, source, title, summary, published_date, url, sentiment)
                    VALUES %s
                    ON CONFLICT (ticker, title, source) DO NOTHING
                """, new_entries)
                conn.commit()
                self._success(f"{len(new_entries)} news salvate nel DB")
            except Exception as e:
                self._warning(f"Errore salvataggio: {e}")
                conn.rollback()

        cur.close()
        conn.close()
        return len(new_entries)

    # ------------------------------------------------------------------
    # Mega fetch
    # ------------------------------------------------------------------

    def mega_fetch(self):
        import streamlit as st
        self._info(f"Aggiornamento notizie {self.ticker}...")
        progress_bar = st.progress(0)
        self.clean_duplicates()
        all_news = []
        fonti = [
            ("Alpha Vantage", self.fetch_alpha_vantage),
            ("NewsAPI",       self.fetch_newsapi),
            ("FMP",           self.fetch_fmp_news),
            ("RSS",           self.fetch_rss),
            ("Yahoo",         self.fetch_yahoo),
        ]
        for i, (nome, fn) in enumerate(fonti):
            self._info(f"Recupero da {nome}...")
            all_news.extend(fn())
            progress_bar.progress((i + 1) / len(fonti))
            time.sleep(0.5)

        seen, uniche = set(), []
        for n in all_news:
            if n.get('url') and n['url'] not in seen:
                seen.add(n['url'])
                uniche.append(n)

        count = self.save_news_to_db(uniche)
        st.balloons()
        self._success(f"{count} NUOVE notizie salvate!")
        return count

    def mega_fetch_silent(self):
        print(f"[{datetime.now():%H:%M:%S}] Aggiornamento {self.ticker}...")
        self.clean_duplicates()
        all_news = []
        fonti = [
            ("Alpha Vantage", self.fetch_alpha_vantage),
            ("NewsAPI",       self.fetch_newsapi),
            ("FMP",           self.fetch_fmp_news),
            ("RSS",           self.fetch_rss),
            ("Yahoo",         self.fetch_yahoo),
        ]
        for nome, fn in fonti:
            print(f"  → {nome}")
            try:
                all_news.extend(fn())
            except Exception as e:
                print(f"  ✗ {nome}: {e}")
            time.sleep(0.5)

        seen, uniche = set(), []
        for n in all_news:
            if n.get('url') and n['url'] not in seen:
                seen.add(n['url'])
                uniche.append(n)

        count = self.save_news_to_db(uniche)
        print(f"  ✓ {self.ticker}: {count} nuove news")
        return count

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_data(self, days=30):
        conn = _get_connection()
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        df = pd.read_sql(
            "SELECT * FROM news WHERE ticker = %s AND published_date >= %s ORDER BY published_date DESC",
            conn, params=(self.ticker, cutoff)
        )
        conn.close()
        return df

    def get_all_data(self):
        conn = _get_connection()
        df = pd.read_sql(
            "SELECT * FROM news WHERE ticker = %s ORDER BY published_date DESC",
            conn, params=(self.ticker,)
        )
        conn.close()
        if df.empty:
            return df
        df['published_date'] = pd.to_datetime(df['published_date'], errors='coerce')
        df = df.dropna(subset=['published_date'])
        return df.sort_values('published_date', ascending=False)

    def clean_duplicates(self):
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("""
            DELETE FROM news
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM news
                GROUP BY ticker, lower(trim(title)), lower(trim(source))
            )
        """)
        deleted = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        if deleted > 0:
            self._info(f"Puliti {deleted} duplicati")
        return deleted


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

class _SilentUI:
    def info(self, msg):    logger.info(msg);    print(f"[INFO] {msg}")
    def success(self, msg): logger.info(msg);    print(f"[OK]   {msg}")
    def warning(self, msg): logger.warning(msg); print(f"[WARN] {msg}")
    def error(self, msg):   logger.error(msg);   print(f"[ERR]  {msg}")


class StreamlitUI:
    def info(self, msg):
        import streamlit as st; st.info(msg)
    def success(self, msg):
        import streamlit as st; st.success(msg)
    def warning(self, msg):
        import streamlit as st; st.warning(msg)
    def error(self, msg):
        import streamlit as st; st.error(msg)