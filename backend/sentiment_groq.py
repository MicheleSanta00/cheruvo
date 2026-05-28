"""
sentiment_groq.py — Scoring sentiment di qualità finanziaria via Groq/Llama 3.

Usato dal workflow GitHub Actions (non in real-time) per ri-classificare
le news salvate da Google RSS e NewsAPI con un modello LLM invece di VADER.
Alpha Vantage mantiene i propri score pre-calcolati (già accurati).

Limiti free tier Groq (llama-3.1-8b-instant):
  - 30 req/min, 14.400 req/giorno
  - Con batch di 10 articoli → ~1.440 articoli/min, 144.000/giorno
  - Ampiamente sufficiente per il volume di Cheruvo
"""
import os
import json
import time
import logging
import psycopg2.extras
from groq import Groq
from database import get_pool

logger = logging.getLogger(__name__)

_groq_client: Groq | None = None


def _get_groq() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    return _groq_client


BATCH_PROMPT = """You are a financial sentiment analysis expert.
Score each news headline+summary with a sentiment value between -1.0 (very negative) and +1.0 (very positive) from a financial/investor perspective.

Rules:
- Focus on what the news means for investors and the stock price
- "beat earnings", "raised guidance", "record profit" → positive (0.3 to 0.8)
- "missed estimates", "layoffs", "investigation", "downgrade" → negative (-0.3 to -0.8)
- "bankruptcy", "fraud", "crash" → very negative (-0.7 to -1.0)
- "partnership", "new product launch", "upgrade" → positive (0.2 to 0.6)
- Neutral announcements, routine filings → near zero (-0.1 to 0.1)
- Use the full range, not just extremes

Respond ONLY with a valid JSON array of numbers (no text, no markdown):
[score1, score2, score3, ...]

News to score (index matches output position):
{items}
"""


def score_batch(articles: list[dict]) -> list[float]:
    """
    Invia un batch di articoli a Groq e restituisce i float scores.
    articles: lista di dict con 'title' e 'summary'.
    Ritorna lista di float della stessa lunghezza; fallback a 0.0 per errori.
    """
    if not articles:
        return []

    items_text = "\n".join(
        f"{i+1}. {a['title']} — {a.get('summary', '')[:120]}"
        for i, a in enumerate(articles)
    )

    prompt = BATCH_PROMPT.format(items=items_text)

    try:
        response = _get_groq().chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.1,   # quasi deterministico per consistency
        )
        raw = response.choices[0].message.content.strip()

        # Pulisci eventuali backtick o testo attorno al JSON
        raw = raw.strip("`").strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()

        scores = json.loads(raw)

        if not isinstance(scores, list):
            raise ValueError(f"Risposta non è una lista: {scores}")

        # Clamp e arrotonda
        result = []
        for i, s in enumerate(scores[:len(articles)]):
            try:
                result.append(round(max(-1.0, min(1.0, float(s))), 4))
            except (TypeError, ValueError):
                logger.warning("Score non valido per articolo %d: %r", i, s)
                result.append(0.0)

        # Padding se Groq restituisce meno scores del previsto
        while len(result) < len(articles):
            result.append(0.0)

        return result

    except json.JSONDecodeError as e:
        logger.warning("JSON non valido da Groq: %s | Raw: %r", e, raw[:200])
        return [0.0] * len(articles)
    except Exception as e:
        logger.error("Errore Groq batch: %s", e)
        return [0.0] * len(articles)


def rescore_non_av_news(ticker: str, batch_size: int = 10,
                         max_articles: int = 100) -> int:
    """
    Ri-classifica le news NON Alpha Vantage di un ticker usando Groq.
    Aggiorna solo gli articoli con score VADER (fonte != 'Alpha Vantage').
    Ritorna il numero di articoli aggiornati.
    """
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        # Seleziona news recenti non AV — quelle con score VADER da migliorare
        cur.execute("""
            SELECT id, title, summary
            FROM news
            WHERE ticker = %s
              AND source != 'Alpha Vantage'
              AND published_date >= NOW() - INTERVAL '7 days'
            ORDER BY published_date DESC
            LIMIT %s
        """, (ticker, max_articles))
        rows = cur.fetchall()
        cur.close()
    finally:
        pool.putconn(conn)

    if not rows:
        logger.info("[Groq Sentiment] Nessun articolo da ri-classificare per %s", ticker)
        return 0

    logger.info("[Groq Sentiment] %d articoli da ri-classificare per %s", len(rows), ticker)

    updated = 0
    for i in range(0, len(rows), batch_size):
        batch_rows = rows[i:i + batch_size]
        articles = [{"title": r[1], "summary": r[2] or ""} for r in batch_rows]
        ids = [r[0] for r in batch_rows]

        scores = score_batch(articles)

        # Aggiorna nel DB
        conn = pool.getconn()
        try:
            cur = conn.cursor()
            psycopg2.extras.execute_values(
                cur,
                "UPDATE news SET sentiment = data.score FROM (VALUES %s) AS data(id, score) WHERE news.id = data.id",
                [(id_, score) for id_, score in zip(ids, scores)],
                template="(%s, %s::real)",
            )
            conn.commit()
            cur.close()
            updated += len(ids)
        finally:
            pool.putconn(conn)

        # Rispetta il rate limit Groq (30 req/min → pausa 2s tra batch)
        if i + batch_size < len(rows):
            time.sleep(2)

    logger.info("[Groq Sentiment] %s: %d articoli aggiornati con score Groq", ticker, updated)
    return updated


def rescore_all_tickers(tickers: list[str]) -> int:
    """
    Entry point per updater.py — ri-classifica tutti i ticker della lista.
    """
    total = 0
    for ticker in tickers:
        try:
            n = rescore_non_av_news(ticker)
            total += n
        except Exception as e:
            logger.error("[Groq Sentiment] Errore su %s: %s", ticker, e)
    logger.info("[Groq Sentiment] Totale articoli ri-classificati: %d", total)
    return total
