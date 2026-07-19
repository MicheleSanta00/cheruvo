"""
quick_fetch.py — Fetch veloce senza FinBERT per Render.
- Alpha Vantage: usa i sentiment score pre-calcolati dall'API (modello finanziario)
- Google RSS / NewsAPI: usa VADER come fallback (nessun score fornito)
"""
import os
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


# ── GDELT ─────────────────────────────────────────────────────────────────────
# Licenza: i dataset GDELT sono rilasciati per "unlimited and unrestricted use
# for any academic, commercial, or governmental use of any kind without fee",
# con diritto di ridistribuzione. È l'unica fonte davvero libera che abbiamo.
# Restiamo comunque su titolo + link + attribuzione, senza testo integrale.
#
# Disattivata finché GDELT_ENABLED non è impostata: la qualità va validata
# prima di lasciarle influenzare le medie di sentiment (le query per nome
# societario producono molto rumore, vedi _e_pertinente).
GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_ENABLED = os.environ.get("GDELT_ENABLED", "").strip().lower() in ("1", "true", "yes")

# Lingua locale attesa per borsa, oltre all'inglese
_LINGUA_BORSA = {"MI": "Italian", "PA": "French", "DE": "German",
                 "AS": "Dutch", "MC": "Spanish", "L": "English"}

# Suffissi societari: inutili come parole chiave e fonte di falsi positivi
_SUFFISSI = {"inc", "inc.", "corp", "corp.", "corporation", "spa", "s.p.a.",
             "plc", "nv", "n.v.", "sa", "s.a.", "ag", "ltd", "limited",
             "group", "holding", "holdings", "company", "co", "the"}

_nomi_cache: dict[str, str] = {}


def _nome_societa(ticker: str) -> str:
    """Nome esteso della società (per interrogare GDELT), con cache in memoria."""
    if ticker in _nomi_cache:
        return _nomi_cache[ticker]
    nome = ticker.split(".")[0]
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info or {}
        esteso = (info.get("longName") or info.get("shortName") or "").strip()
        if esteso:
            nome = esteso
    except Exception as e:
        logger.info("GDELT: nome societario non risolto per %s (%s)", ticker, e)
    _nomi_cache[ticker] = nome
    return nome


def _parole_chiave(ticker: str, nome: str) -> list[str]:
    """
    Parole che un titolo pertinente dovrebbe contenere.
    I punti vengono tolti prima del confronto, così "S.p.A." diventa "spa" e
    finisce tra i suffissi da scartare: se restasse, qualunque notizia su una
    qualsiasi società italiana risulterebbe pertinente.
    """
    parole = []
    for p in nome.split():
        p = p.strip(",.'\"").lower().replace(".", "")
        if p and p not in _SUFFISSI and len(p) > 2 and p not in parole:
            parole.append(p)
    base = ticker.split(".")[0].lower()
    if len(base) > 2 and base not in parole:
        parole.append(base)
    return parole or [base]


def _e_pertinente(titolo: str, chiavi: list[str]) -> bool:
    """
    Guardia anti rumore. Una query per nome societario su GDELT restituisce
    anche articoli che citano l'azienda di sfuggita o per niente (provato:
    cercando "nvidia" tornano pezzi su altre società e sulla giacca del CEO).
    Senza questo filtro quel rumore finirebbe nella media di sentiment.

    Il confronto è su parola intera: cercare "eni" come sottostringa
    combacerebbe dentro "beni", "veniva" e mezzo vocabolario italiano.
    """
    import re
    t = titolo.lower()
    return any(re.search(rf"\b{re.escape(k)}\b", t) for k in chiavi)


def fetch_gdelt(ticker: str, max_items: int = 25) -> list:
    if not GDELT_ENABLED:
        return []
    news_list = []
    try:
        nome = _nome_societa(ticker)
        chiavi = _parole_chiave(ticker, nome)
        borsa = ticker.split(".")[-1] if "." in ticker else ""
        lingue = {"English", _LINGUA_BORSA.get(borsa, "English")}

        resp = requests.get(GDELT_URL, params={
            "query": f'"{nome}"',
            "mode": "artlist",
            "format": "json",
            "maxrecords": max_items,
            "timespan": "3d",
            "sort": "datedesc",
        }, timeout=15, headers={"User-Agent": "Cheruvo/1.0 (+https://cheruvo.com)"})
        resp.raise_for_status()
        articoli = (resp.json() or {}).get("articles", []) or []

        scartati = 0
        for a in articoli:
            titolo = (a.get("title") or "").strip()
            if not titolo:
                continue
            if a.get("language") not in lingue:
                scartati += 1
                continue
            if not _e_pertinente(titolo, chiavi):
                scartati += 1
                continue
            news_list.append({
                "source": f"GDELT · {a.get('domain', 'n/d')}",
                "title": titolo,
                # GDELT non fornisce il sommario: lo score si basa sul titolo
                "summary": "",
                "published_date": format_date(a.get("seendate", "")),
                "url": a.get("url", ""),
                "sentiment": vader_sentiment(titolo),
            })
        logger.info("QuickFetch GDELT %s: %d news tenute, %d scartate",
                    ticker, len(news_list), scartati)
    except Exception as e:
        logger.error("QuickFetch GDELT error: %s", e)
    return news_list


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
                    n["score_source"] = "llm"
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
    # LICENZE — NON riattivare fetch_newsapi senza un piano a pagamento:
    # il piano gratuito "Developer" di NewsAPI è valido solo in ambiente di
    # sviluppo, vieta l'uso commerciale e ritarda gli articoli di 24 ore
    # (quindi come segnale di sentiment era comunque vecchio di un giorno).
    all_news.extend(fetch_alpha_vantage(ticker))
    all_news.extend(fetch_google_rss(ticker))
    all_news.extend(fetch_gdelt(ticker))   # no-op finché GDELT_ENABLED non è attiva
    
    # Aggiungi fonti europee se ticker europeo
    if '.' in ticker:
        all_news.extend(fetch_european_rss(ticker))

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