"""
data/database.py — versione CON FinBERT per GitHub Actions.
Usato da updater.py per scaricare news e calcolare il sentiment.
"""
import os
import pandas as pd
from datetime import datetime, timedelta
import requests
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import feedparser
import torch
import praw
import time
import logging
import psycopg2
import psycopg2.extras
from dateutil import parser as dateparser

logger = logging.getLogger(__name__)


# ── FinBERT Singleton ─────────────────────────────────────────────────────

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

    def predict(self, text: str) -> float:
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


# ── Connessione PostgreSQL ─────────────────────────────────────────────────

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


# ── SuperNewsAnalyzer ──────────────────────────────────────────────────────

class SuperNewsAnalyzer:

    def __init__(self, ticker: str, api_key):
        self.ticker = ticker.upper()
        # Supporta sia dict che stringa (compatibilità con updater.py)
        if isinstance(api_key, dict):
            self.api_key = api_key
        else:
            self.api_key = {"ALPHA_VANTAGE": api_key}
        init_database()

    def _format_date(self, date_str):
        if not date_str:
            return ""
        try:
            return dateparser.parse(str(date_str)).strftime("%Y-%m-%d")
        except Exception:
            s = str(date_str)
            return s[:10] if len(s) >= 10 else ""

    def fetch_alpha_vantage(self):
        news_list = []
        try:
            params = {
                "function": "NEWS_SENTIMENT",
                "tickers": self.ticker,
                "limit": 100,
                "apikey": self.api_key.get("ALPHA_VANTAGE", "demo").strip(),
                "sort": "LATEST",
            }
            r = requests.get("https://www.alphavantage.co/query", params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            if "feed" not in data or not data["feed"]:
                return []
            finbert = get_finbert()
            for item in data["feed"][:50]:
                title = item.get("title", "").strip()
                if not title:
                    continue
                summary = item.get("summary", "").strip()
                av_sent = float(item.get("overall_sentiment_score", 0))
                try:
                    sent = finbert.predict(f"{title} {summary}")
                except Exception:
                    sent = av_sent
                news_list.append({
                    "source": item.get("source", "Alpha Vantage"),
                    "title": title,
                    "summary": (summary[:250] + "...") if len(summary) > 250 else summary,
                    "published_date": self._format_date(item.get("time_published")),
                    "url": item.get("url", ""),
                    "sentiment": sent,
                })
            print(f"Alpha Vantage: {len(news_list)} news")
        except Exception as e:
            print(f"Alpha Vantage error: {str(e)[:80]}")
        return news_list

    def fetch_newsapi(self):
        news_list = []
        try:
            from newsapi import NewsApiClient
            api_key = self.api_key.get("NEWSAPI", os.environ.get("NEWSAPI", "")).strip()
            if not api_key:
                return []
            api = NewsApiClient(api_key=api_key)
            finbert = get_finbert()
            for query in [f"{self.ticker} stock", f"{self.ticker} earnings"]:
                try:
                    articles = api.get_everything(
                        q=query, language="en", sort_by="publishedAt", page_size=20
                    ).get("articles", [])
                    for a in articles[:10]:
                        title = (a.get("title") or "").strip()
                        desc = (a.get("description") or "").strip()
                        url = a.get("url", "")
                        if not title or len(title) < 10 or not url:
                            continue
                        news_list.append({
                            "source": (a.get("source") or {}).get("name", "Unknown"),
                            "title": title,
                            "summary": (desc or title)[:250],
                            "published_date": self._format_date(a.get("publishedAt")),
                            "url": url,
                            "sentiment": finbert.predict(f"{title} {desc}"),
                        })
                except Exception:
                    continue
            seen, unique = set(), []
            for n in news_list:
                k = n["url"] or n["title"].lower()
                if k not in seen:
                    seen.add(k); unique.append(n)
            print(f"NewsAPI: {len(unique)} news")
            return unique[:50]
        except Exception as e:
            print(f"NewsAPI error: {str(e)[:80]}")
        return news_list

    def fetch_fmp_news(self):
        news_list = []
        try:
            api_key = self.api_key.get("FMP", os.environ.get("FMP", "")).strip()
            if not api_key:
                return []
            r = requests.get(
                "https://financialmodelingprep.com/api/v3/stock_news",
                params={"ticker": self.ticker, "limit": 50, "apikey": api_key},
                timeout=15,
            )
            if r.status_code == 403:
                return []
            finbert = get_finbert()
            for item in r.json():
                title = item.get("title", "").strip()
                if not title:
                    continue
                text = item.get("text", "")
                news_list.append({
                    "source": "FinancialModelingPrep",
                    "title": title,
                    "summary": (text or title)[:250],
                    "published_date": self._format_date(item.get("publishedDate")),
                    "url": item.get("url", ""),
                    "sentiment": finbert.predict(f"{title} {text}"),
                })
            print(f"FMP: {len(news_list)} news")
        except Exception as e:
            print(f"FMP error: {str(e)[:80]}")
        return news_list

    def fetch_rss(self):
        ticker_lower = self.ticker.lower()
        sources = {
            f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={self.ticker}&region=US&lang=en-US": "Yahoo Finance",
            f"https://finviz.com/rss.ashx?t={self.ticker}": "Finviz",
            f"https://news.google.com/rss/search?q={self.ticker}+stock&hl=en-US&gl=US&ceid=US:en": "Google News",
            f"https://news.google.com/rss/search?q={self.ticker}+earnings&hl=en-US&gl=US&ceid=US:en": "Google News Earnings",
            f"https://seekingalpha.com/api/sa/combined/{self.ticker}.xml": "Seeking Alpha",
            f"https://www.investing.com/rss/news_{self.ticker}.rss": "Investing.com",
            "https://feeds.marketwatch.com/marketwatch/marketpulse/": "MarketWatch",
            "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best": "Reuters",
        }
        news_list = []
        finbert = get_finbert()
        
        for url, name in sources.items():
            try:
                feed = feedparser.parse(url)
                if not feed.entries:
                    print(f"RSS {name}: 0 news")
                    continue
                count = 0
                for entry in feed.entries[:25]:
                    title = entry.get("title", "").strip()
                    if not title or len(title) < 10:
                        continue
                    # Fonti generiche: filtra per ticker nel titolo
                    if name in ["MarketWatch", "Reuters"] and self.ticker.lower() not in title.lower():
                        continue
                    summary = entry.get("summary", "") or entry.get("description", "")
                    # Rimuovi HTML dal summary
                    import re
                    summary = re.sub(r'<[^>]+>', '', summary)[:250]
                    news_list.append({
                        "source": name,
                        "title": title,
                        "summary": summary,
                        "published_date": self._format_date(entry.get("published", "")),
                        "url": entry.get("link", ""),
                        "sentiment": finbert.predict(f"{title} {summary}"),
                    })
                    count += 1
                print(f"RSS {name}: {count} news")
            except Exception as e:
                print(f"RSS {name}: {str(e)[:60]}")
        
        print(f"RSS totale: {len(news_list)} news")
        return news_list
    
    def fetch_european_news(self):
        """Fonti specifiche per azioni europee."""
        news_list = []
        finbert = get_finbert()
        
        # Estrai il nome base del ticker (es. ENI da ENI.MI)
        base = self.ticker.split('.')[0]
        exchange = self.ticker.split('.')[-1] if '.' in self.ticker else ''
        
        # Mappa exchange → lingua/paese per Google News
        lang_map = {
            'MI': ('it', 'IT', 'it'),
            'PA': ('fr', 'FR', 'fr'),
            'DE': ('de', 'DE', 'de'),
            'L':  ('en', 'GB', 'en'),
            'AS': ('nl', 'NL', 'nl'),
            'MC': ('es', 'ES', 'es'),
        }
        lang, country, hl = lang_map.get(exchange, ('en', 'US', 'en'))
        
        sources = {
            # Google News in lingua locale
            f"https://news.google.com/rss/search?q={base}+azione&hl={hl}&gl={country}&ceid={country}:{hl}": f"Google News {country}",
            # Google News in inglese (sempre utile)
            f"https://news.google.com/rss/search?q={base}+stock&hl=en&gl=US&ceid=US:en": "Google News EN",
            # Yahoo Finance ticker-specifico
            f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={self.ticker}&region=US&lang=en-US": "Yahoo Finance",
        }
        
        # Fonti italiane se .MI
        if exchange == 'MI':
            sources.update({
                "https://www.ilsole24ore.com/rss/finanza-e-mercati.xml": "Il Sole 24 Ore",
                "https://www.milanofinanza.it/rss": "Milano Finanza",
                f"https://news.google.com/rss/search?q={base}+borsa+italiana&hl=it&gl=IT&ceid=IT:it": "Google News Borsa IT",
            })
        
        # Fonti pan-europee
        sources.update({
            "https://feeds.reuters.com/reuters/businessNews": "Reuters Business",
            f"https://news.google.com/rss/search?q={base}+Europa+finanza&hl=it&gl=IT&ceid=IT:it": "Google News Europa",
        })
        
        for url, name in sources.items():
            try:
                import feedparser, re
                feed = feedparser.parse(url)
                count = 0
                for entry in feed.entries[:20]:
                    title = entry.get("title", "").strip()
                    if not title or len(title) < 10:
                        continue
                    # Per fonti generiche filtra per nome ticker
                    if name in ["Reuters Business"] and base.lower() not in title.lower():
                        continue
                    summary = entry.get("summary", "") or entry.get("description", "")
                    summary = re.sub(r'<[^>]+>', '', summary)[:250]
                    news_list.append({
                        "source": name,
                        "title": title,
                        "summary": summary,
                        "published_date": self._format_date(entry.get("published", "")),
                        "url": entry.get("link", ""),
                        "sentiment": finbert.predict(f"{title} {summary}"),
                    })
                    count += 1
                if count:
                    print(f"  EU RSS {name}: {count} news")
            except Exception as e:
                print(f"  EU RSS {name}: {str(e)[:60]}")
        
        return news_list

    def fetch_sec(self):
        """SEC EDGAR — comunicati ufficiali (earnings, acquisizioni, ecc.)"""
        news_list = []
        try:
            headers = {"User-Agent": "FinSentinel contact@finsentinel.com"}
            # Cerca il CIK del ticker
            r = requests.get(
                f"https://efts.sec.gov/LATEST/search-index?q=%22{self.ticker}%22&dateRange=custom&startdt={(datetime.now()-timedelta(days=30)).strftime('%Y-%m-%d')}&enddt={datetime.now().strftime('%Y-%m-%d')}&forms=8-K",
                headers=headers, timeout=15
            )
            data = r.json()
            hits = data.get("hits", {}).get("hits", [])
            finbert = get_finbert()
            for hit in hits[:15]:
                source_data = hit.get("_source", {})
                title = source_data.get("display_names", [self.ticker])[0]
                form = source_data.get("form_type", "8-K")
                filed = source_data.get("file_date", "")
                description = source_data.get("period_of_report", "")
                full_title = f"{self.ticker} {form} — {title}"
                news_list.append({
                    "source": "SEC EDGAR",
                    "title": full_title,
                    "summary": f"Filing {form} presentato il {filed}",
                    "published_date": self._format_date(filed),
                    "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={self.ticker}&type=8-K&dateb=&owner=include&count=10",
                    "sentiment": finbert.predict(full_title),
                })
            print(f"SEC EDGAR: {len(news_list)} filing")
        except Exception as e:
            print(f"SEC EDGAR error: {str(e)[:80]}")
        return news_list

    def fetch_reddit(self):
        news_list = []
        try:
            rc = self.api_key.get("REDDIT", {})
            client_id = rc.get("client_id") or os.environ.get("REDDIT_CLIENT_ID", "")
            client_secret = rc.get("client_secret") or os.environ.get("REDDIT_CLIENT_SECRET", "")
            if not client_id:
                return []
            reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=f"NewsAnalyzer-{self.ticker}",
            )
            finbert = get_finbert()
            for sub in ["stocks", "investing", "wallstreetbets"]:
                for post in reddit.subreddit(sub).new(limit=15):
                    if self.ticker.lower() in post.title.lower():
                        text = f"{post.title} {post.selftext[:300]}"
                        news_list.append({
                            "source": f"Reddit/r/{sub}",
                            "title": post.title,
                            "summary": (post.selftext[:250] + "...") if post.selftext else post.title,
                            "published_date": self._format_date(
                                datetime.utcfromtimestamp(post.created_utc).strftime("%Y-%m-%d")
                            ),
                            "url": f"https://reddit.com{post.permalink}",
                            "sentiment": finbert.predict(text),
                        })
            print(f"Reddit: {len(news_list)} post")
            return news_list[:15]
        except Exception as e:
            print(f"Reddit error: {str(e)[:60]}")
        return news_list

    def save_news_to_db(self, news_list):
        if not news_list:
            return 0
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT lower(trim(title)), lower(trim(source)) FROM news WHERE ticker = %s",
            (self.ticker,),
        )
        existing = set(cur.fetchall())
        new_entries = []
        for n in news_list:
            tk = n["title"].lower().strip()
            sk = n["source"].lower().strip()
            if (tk, sk) not in existing:
                new_entries.append((
                    self.ticker, n["source"], n["title"].strip(),
                    (n.get("summary") or "").strip(),
                    n["published_date"], n["url"], float(n["sentiment"]),
                ))
                existing.add((tk, sk))
        if new_entries:
            try:
                psycopg2.extras.execute_values(cur, """
                    INSERT INTO news (ticker, source, title, summary, published_date, url, sentiment)
                    VALUES %s
                    ON CONFLICT (ticker, title, source) DO NOTHING
                """, new_entries)
                conn.commit()
                print(f"{len(new_entries)} news salvate")
            except Exception as e:
                print(f"Salvataggio error: {e}")
                conn.rollback()
        cur.close(); conn.close()
        return len(new_entries)

    def mega_fetch_silent(self):
        print(f"[{datetime.now():%H:%M:%S}] Aggiornamento {self.ticker}...")
        all_news = []
        
        # Determina se è un ticker europeo
        is_european = '.' in self.ticker and self.ticker.split('.')[-1] in ['MI', 'PA', 'DE', 'L', 'AS', 'MC']
        
        sources = [
            ("Alpha Vantage", self.fetch_alpha_vantage),
            ("NewsAPI",       self.fetch_newsapi),
            ("FMP",           self.fetch_fmp_news),
            ("RSS",           self.fetch_rss),
            ("SEC EDGAR",     self.fetch_sec),
        ]
        
        if is_european:
            sources.append(("European News", self.fetch_european_news))
        
        for nome, fn in sources:
            print(f"  → {nome}")
            try:
                all_news.extend(fn())
            except Exception as e:
                print(f"  ✗ {nome}: {e}")
            time.sleep(0.5)
        
        seen, uniche = set(), []
        for n in all_news:
            if n.get("url") and n["url"] not in seen:
                seen.add(n["url"]); uniche.append(n)
        count = self.save_news_to_db(uniche)
        print(f"  ✓ {self.ticker}: {count} nuove news")
        return count

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