"""
sentiment_groq.py — Scoring sentiment di qualità finanziaria via Groq/Llama.

Usato in due punti:
  1. updater.py (GitHub Actions, ogni 6 ore): ri-classifica le news non-AV
     ancora con score VADER (score_source='vader').
  2. quick_fetch.py (on-demand): prova a dare subito lo score LLM alle news
     appena scaricate, con VADER come fallback.

Principio di robustezza: se Groq fallisce (rate limit, modello dismesso,
JSON rotto) NON si tocca nulla — gli score esistenti restano.
Mai sovrascrivere uno score buono con uno zero.

Modello: env GROQ_SCORE_MODEL (default llama-3.3-70b-versatile, lo stesso
già usato per AI Summary e Academy — garantito attivo sull'account).
"""
import os
import json
import time
import logging
import psycopg2.extras
from groq import Groq
from database import get_pool

logger = logging.getLogger(__name__)

GROQ_SCORE_MODEL = os.environ.get("GROQ_SCORE_MODEL", "llama-3.3-70b-versatile")

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
- "beat earnings", "raised guidance", "record profit" -> positive (0.3 to 0.8)
- "missed estimates", "layoffs", "investigation", "downgrade" -> negative (-0.3 to -0.8)
- "bankruptcy", "fraud", "crash" -> very negative (-0.7 to -1.0)
- "partnership", "new product launch", "upgrade" -> positive (0.2 to 0.6)
- Neutral announcements, routine filings -> near zero (-0.1 to 0.1)
- Headlines may be in English, Italian or other languages: score them all
- Use the full range, not just extremes

Respond ONLY with a JSON object of this exact shape (no text, no markdown):
{{"scores": [score1, score2, score3, ...]}}

News to score (index matches output position):
{items}
"""


def score_batch(articles: list[dict]) -> list | None:
    """
    Invia un batch di articoli a Groq e restituisce gli score.

    Ritorna:
      - list della stessa lunghezza di articles; ogni elemento è un float
        in [-1, 1] oppure None se quel singolo score non è utilizzabile;
      - None se l'intera chiamata fallisce (rate limit, modello, JSON rotto).

    Il chiamante NON deve scrivere nulla per gli elementi None.
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
            model=GROQ_SCORE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.1,   # quasi deterministico per consistency
            response_format={"type": "json_object"},
        )
        raw = (response.choices[0].message.content or "").strip()

        # Pulisci eventuali backtick o prefissi attorno al JSON
        raw = raw.strip("`").strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()

        data = json.loads(raw)
        # Accetta sia {"scores": [...]} sia una lista nuda
        scores = data.get("scores") if isinstance(data, dict) else data
        if not isinstance(scores, list):
            raise ValueError(f"Risposta senza lista scores: {type(scores)}")

        result = []
        for i, s in enumerate(scores[:len(articles)]):
            try:
                result.append(round(max(-1.0, min(1.0, float(s))), 4))
            except (TypeError, ValueError):
                logger.warning("Score non valido per articolo %d: %r", i, s)
                result.append(None)

        # Padding con None se Groq restituisce meno score del previsto
        while len(result) < len(articles):
            result.append(None)
        return result

    except json.JSONDecodeError as e:
        logger.warning("JSON non valido da Groq: %s | Raw: %r", e, raw[:200])
        return None
    except Exception as e:
        logger.error("Errore Groq batch (%s): %s", GROQ_SCORE_MODEL, e)
        return None


def rescore_non_av_news(ticker: str, batch_size: int = 10,
                         max_articles: int = 100) -> int:
    """
    Ri-classifica con Groq le news di un ticker che hanno ancora lo score
    VADER (score_source='vader'). Ogni articolo viene processato UNA volta:
    dopo l'update score_source diventa 'llm'.
    Se Groq fallisce, gli score VADER restano intatti.
    """
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, title, summary
            FROM news
            WHERE ticker = %s
              AND source != 'Alpha Vantage'
              AND COALESCE(score_source, 'vader') = 'vader'
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
        if scores is None:
            logger.warning("[Groq Sentiment] Batch fallito per %s — score VADER conservati", ticker)
            break   # inutile insistere in questo run; riproverà il prossimo

        pairs = [(id_, s) for id_, s in zip(ids, scores) if s is not None]
        if pairs:
            conn = pool.getconn()
            try:
                cur = conn.cursor()
                psycopg2.extras.execute_values(
                    cur,
                    "UPDATE news SET sentiment = data.score, score_source = 'llm' "
                    "FROM (VALUES %s) AS data(id, score) WHERE news.id = data.id",
                    pairs,
                    template="(%s, %s::real)",
                )
                conn.commit()
                cur.close()
                updated += len(pairs)
            finally:
                pool.putconn(conn)

        # Rispetta il rate limit Groq (pausa tra batch)
        if i + batch_size < len(rows):
            time.sleep(2)

    logger.info("[Groq Sentiment] %s: %d articoli aggiornati con score Groq", ticker, updated)
    return updated


def rescore_all_tickers(tickers: list[str]) -> int:
    """Entry point per updater.py — ri-classifica tutti i ticker della lista."""
    total = 0
    for ticker in tickers:
        try:
            total += rescore_non_av_news(ticker)
        except Exception as e:
            logger.error("[Groq Sentiment] Errore su %s: %s", ticker, e)
    logger.info("[Groq Sentiment] Totale articoli ri-classificati: %d", total)
    return total
