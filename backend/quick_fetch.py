"""
quick_fetch.py — Fetch veloce senza FinBERT per Render.
Usa VADER per il sentiment — leggero e istantaneo.
"""
import logging
import requests
import psycopg2.extras
from datetime import datetime, timedelta
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from dateutil import parser as dateparser
from database import get_pool

logger = logging.getLogger(__name__)

analyzer = SentimentIntensityAnalyzer()


def vader_sentiment(text: str) -> float:
    if not text:
        return 0.0
    score = analyzer.polarity_scores(text)["compound"]
    return round(max(-1.0, min(1.0, score)), 4)


def format_date(date_str):
    if not date_str:
        return None
    try:
        return dateparser.parse(str(date_str)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        s = str(date_str)
        # fallback: se abbiamo almeno la data, restituiamola come mezzanotte
        return f"{s[:10]} 00:00:00" if len(s) >= 10 else None


def fetch_alpha_vantage(ticker: str) -> list:
    news_list = []
    try:
        api_key = os.environ.get("ALPHA_VANTAGE", "").strip()
        if not api_key:
            return []
        r = requests.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "NEWS_SENTIMENT",
                "tickers": ticker,
                "limit": 50,
                "apikey": api_key,
                "sort": "LATEST",
            },
            timeout=15,
        )
        for item in r.json().get("feed", [])[:30]:
            title = item.get("title", "").strip()
            if not title:
                continue
            summary = item.get("summary", "").strip()
            news_list.append({
                "source": item.get("source", "Alpha Vantage"),
                "title": title,
                "summary": summary[:250],
                "published_date": format_date(item.get("time_published")),
                "url": item.get("url", ""),
                "sentiment": vader_sentiment(f"{title} {summary}"),
            })
        logger.info("QuickFetch Alpha Vantage: %d news", len(news_list))
    except Exception as e:
        logger.error("QuickFetch AV error: %s", e)
    return news_list


def fetch_newsapi(ticker: str) -> list:
    news_list = []
    try:
        api_key = os.environ.get("NEWSAPI", "").strip()
        if not api_key:
            return []
        from newsapi import NewsApiClient
        api = NewsApiClient(api_key=api_key)
        articles = api.get_everything(
            q=f"{ticker} stock", language="en",
            sort_by="publishedAt", page_size=20
        ).get("articles", [])
        for a in articles[:15]:
            title = (a.get("title") or "").strip()
            desc = (a.get("description") or "").strip()
            if not title or len(title) < 10:
                continue
            news_list.append({
                "source": (a.get("source") or {}).get("name", "NewsAPI"),
                "title": title,
                "summary": desc[:250],
                "published_date": format_date(a.get("publishedAt")),
                "url": a.get("url", ""),
                "sentiment": vader_sentiment(f"{title} {desc}"),
            })
        logger.info("QuickFetch NewsAPI: %d news", len(news_list))
    except Exception as e:
        logger.error("QuickFetch NewsAPI error: %s", e)
    return news_list


def fetch_google_rss(ticker: str) -> list:
    news_list = []
    try:
        import feedparser
        feed = feedparser.parse(
            f"https://news.google.com/rss/search?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en"
        )
        for entry in feed.entries[:20]:
            title = entry.get("title", "").strip()
            if not title:
                continue
            summary = entry.get("summary", "")
            news_list.append({
                "source": "Google News",
                "title": title,
                "summary": summary[:250],
                "published_date": format_date(entry.get("published", "")),
                "url": entry.get("link", ""),
                "sentiment": vader_sentiment(f"{title} {summary}"),
            })
        logger.info("QuickFetch Google News: %d news", len(news_list))
    except Exception as e:
        logger.error("QuickFetch Google RSS error: %s", e)
    return news_list

def fetch_european_rss(ticker: str) -> list:
    news_list = []
    try:
        import feedparser, re
        base = ticker.split('.')[0]
        exchange = ticker.split('.')[-1] if '.' in ticker else ''
        
        urls = [
            f"https://news.google.com/rss/search?q={base}+stock&hl=en&gl=US&ceid=US:en",
            f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US",
        ]
        
        if exchange == 'MI':
            urls.append(f"https://news.google.com/rss/search?q={base}+borsa&hl=it&gl=IT&ceid=IT:it")
            urls.append("https://www.ilsole24ore.com/rss/finanza-e-mercati.xml")
        
        for url in urls:
            feed = feedparser.parse(url)
            for entry in feed.entries[:15]:
                title = entry.get("title", "").strip()
                if not title:
                    continue
                summary = re.sub(r'<[^>]+>', '', entry.get("summary", ""))[:250]
                news_list.append({
                    "source": "European News",
                    "title": title,
                    "summary": summary,
                    "published_date": format_date(entry.get("published", "")),
                    "url": entry.get("link", ""),
                    "sentiment": vader_sentiment(f"{title} {summary}"),
                })
        logger.info("QuickFetch European RSS: %d news", len(news_list))
    except Exception as e:
        logger.error("QuickFetch European RSS error: %s", e)
    return news_list


def save_news(ticker: str, news_list: list) -> int:
    if not news_list:
        return 0
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT lower(trim(title)), lower(trim(source)) FROM news WHERE ticker = %s",
            (ticker,),
        )
        existing = set(cur.fetchall())
        new_entries = []
        for n in news_list:
            tk = n["title"].lower().strip()
            sk = n["source"].lower().strip()
            if (tk, sk) not in existing:
                new_entries.append((
                    ticker, n["source"], n["title"],
                    n.get("summary", ""), n["published_date"],
                    n["url"], float(n["sentiment"]),
                ))
                existing.add((tk, sk))
        if new_entries:
            psycopg2.extras.execute_values(cur, """
                INSERT INTO news (ticker, source, title, summary, published_date, url, sentiment)
                VALUES %s
                ON CONFLICT (ticker, title, source) DO NOTHING
            """, new_entries)
            conn.commit()
        cur.close()
    finally:
        pool.putconn(conn)
    return len(new_entries)


def quick_fetch(ticker: str) -> int:
    logger.info("QuickFetch avviato per %s", ticker)
    all_news = []
    all_news.extend(fetch_alpha_vantage(ticker))
    all_news.extend(fetch_newsapi(ticker))
    all_news.extend(fetch_google_rss(ticker))
    
    # Aggiungi fonti europee se ticker europeo
    if '.' in ticker:
        all_news.extend(fetch_european_rss(ticker))

    seen, unique = set(), []
    for n in all_news:
        if n.get("url") and n["url"] not in seen:
            seen.add(n["url"])
            unique.append(n)

    count = save_news(ticker, unique)
    logger.info("QuickFetch %s completato: %d nuove news salvate", ticker, count)
    return count