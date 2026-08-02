"""
quick_fetch.py — Fetch veloce senza FinBERT per Render.

FONTI ATTIVE (scelta "zero rischi legali", luglio 2026):
- GDELT: licenza commerciale libera → fonte principale (vedi gdelt_source.py)
- Alpha Vantage: dietro interruttore AV_ENABLED, SPENTO di default. Il supporto
  ha confermato via email che il piano gratuito non copre l'uso commerciale;
  si riaccende solo dopo aver ottenuto un piano/autorizzazione.

NON riattivare NewsAPI, Google News RSS, Yahoo/Sole24Ore RSS senza una licenza
commerciale: le funzioni restano nel file per riferimento ma non vengono
chiamate (vedi quick_fetch()).
"""
import os
import logging
import requests
import psycopg2.extras
from datetime import datetime, timedelta
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from dateutil import parser as dateparser
from database import get_pool
from gdelt_source import fetch_gdelt
from sec_source import fetch_sec

logger = logging.getLogger(__name__)

analyzer = SentimentIntensityAnalyzer()

# Interruttori fonti. Alpha Vantage spento finché non c'è autorizzazione scritta;
# GDELT acceso di default. Si cambiano via variabili d'ambiente su Render.
AV_ENABLED    = os.environ.get("AV_ENABLED", "").strip().lower() in ("1", "true", "yes")
GDELT_ENABLED = os.environ.get("GDELT_ENABLED", "1").strip().lower() in ("1", "true", "yes")


def vader_sentiment(text: str) -> float:
    if not text:
        return 0.0
    score = analyzer.polarity_scores(text)["compound"]
    return round(max(-1.0, min(1.0, score)), 4)


def _av_sentiment(item: dict, ticker: str) -> float:
    """
    Estrae il sentiment da una news Alpha Vantage con questo ordine di priorità:
    1. ticker_sentiment_score specifico per il ticker richiesto
    2. overall_sentiment_score dell'articolo
    3. VADER sul titolo+summary come fallback finale
    """
    # 1. Score specifico per il ticker (es. AAPL ha score diverso da MSFT
    #    nello stesso articolo che li cita entrambi)
    ticker_upper = ticker.upper()
    for ts in item.get("ticker_sentiment", []):
        if ts.get("ticker", "").upper() == ticker_upper:
            try:
                score = float(ts["ticker_sentiment_score"])
                return round(max(-1.0, min(1.0, score)), 4)
            except (KeyError, ValueError, TypeError):
                break

    # 2. Overall score dell'articolo
    try:
        score = float(item["overall_sentiment_score"])
        return round(max(-1.0, min(1.0, score)), 4)
    except (KeyError, ValueError, TypeError):
        pass

    # 3. Fallback VADER
    title = item.get("title", "")
    summary = item.get("summary", "")
    return vader_sentiment(f"{title} {summary}")


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

            # Preferisci il sentiment specifico per il ticker se disponibile,
            # altrimenti usa l'overall score dell'articolo,
            # altrimenti fallback a VADER sul testo.
            sentiment = _av_sentiment(item, ticker)

            news_list.append({
                "source": item.get("source", "Alpha Vantage"),
                "title": title,
                "summary": summary[:250],
                "published_date": format_date(item.get("time_published")),
                "url": item.get("url", ""),
                "sentiment": sentiment,
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


# NOTA: la logica GDELT vive in gdelt_source.py (condivisa col cron). Qui la
# importiamo soltanto. Le due funzioni RSS qui sotto restano definite per
# riferimento ma NON sono più chiamate (vedi quick_fetch()).


def fetch_european_rss(ticker: str) -> list:
    news_list = []
    try:
        import feedparser, re
        base = ticker.split('.')[0]
        exchange = ticker.split('.')[-1] if '.' in ticker else ''
        
        # LICENZE — il feed RSS di Yahoo Finance è dichiarato per solo uso NON
        # commerciale: rimosso perché Cheruvo vende un piano a pagamento.
        urls = [
            f"https://news.google.com/rss/search?q={base}+stock&hl=en&gl=US&ceid=US:en",
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


def _llm_refine(news_list: list, max_items: int = 40) -> int:
    """
    Prova a sostituire gli score VADER con score LLM (Groq) per le news non-AV,
    direttamente al momento del fetch. Muta news_list in place.
    Qualsiasi errore → si tengono gli score VADER (mai peggiorare).
    Ritorna il numero di score migliorati.
    """
    if not os.environ.get("GROQ_API_KEY"):
        return 0
    targets = [n for n in news_list
               if n.get("source") != "Alpha Vantage"
               and n.get("score_source", "vader") == "vader"][:max_items]
    if not targets:
        return 0
    refined = 0
    try:
        from sentiment_groq import score_batch
        for i in range(0, len(targets), 20):
            chunk = targets[i:i + 20]
            scores = score_batch([{"title": n["title"], "summary": n.get("summary", "")}
                                  for n in chunk])
            if scores is None:
                break   # Groq indisponibile: VADER resta, riproverà il cron
            for n, s in zip(chunk, scores):
                if s is not None:
                    n["sentiment"] = s
                    # 'llm2' = scoring con mappatura per indice (vedi
                    # sentiment_groq). Le righe marcate 'llm' vengono dalla
                    # versione con il disallineamento e vanno ripassate.
                    n["score_source"] = "llm2"
                    refined += 1
    except Exception as e:
        logger.warning("LLM refine saltato (%s) — score VADER conservati", e)
    if refined:
        logger.info("QuickFetch: %d score raffinati con LLM", refined)
    return refined


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
                source_kind = "av" if n["source"] == "Alpha Vantage" else n.get("score_source", "vader")
                new_entries.append((
                    ticker, n["source"], n["title"],
                    n.get("summary", ""), n["published_date"],
                    n["url"], float(n["sentiment"]), source_kind,
                ))
                existing.add((tk, sk))
        if new_entries:
            psycopg2.extras.execute_values(cur, """
                INSERT INTO news (ticker, source, title, summary, published_date, url, sentiment, score_source)
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

    # Catena fonti "zero rischi legali" (luglio 2026):
    #   GDELT     -> principale, licenza commerciale libera
    #   Alpha V.  -> solo se AV_ENABLED (autorizzazione scritta dal supporto)
    # Escluse senza licenza: NewsAPI (vieta la produzione), Google News RSS,
    # Yahoo/Sole24Ore RSS. Le funzioni restano sopra come riferimento.
    if GDELT_ENABLED:
        all_news.extend(fetch_gdelt(ticker))
    # SEC: atti pubblici del governo USA, pubblico dominio. Nessuna licenza da
    # chiedere e nessuna chiave da farsi revocare. Vale solo per i titoli USA
    # e ritorna lista vuota per gli altri, quindi si può chiamare sempre.
    all_news.extend(fetch_sec(ticker))
    if AV_ENABLED:
        all_news.extend(fetch_alpha_vantage(ticker))

    seen, unique = set(), []
    for n in all_news:
        if n.get("url") and n["url"] not in seen:
            seen.add(n["url"])
            unique.append(n)

    # Score di qualità finanziaria via LLM (fallback: VADER già calcolato)
    _llm_refine(unique)

    count = save_news(ticker, unique)
    logger.info("QuickFetch %s completato: %d nuove news salvate", ticker, count)
    return count