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
già usato per AI Summary — garantito attivo sull'account).
"""
import os
import re
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

CRITICAL: every item must be scored and must carry back its own number "n".
Never skip an item, never renumber, never reorder.

Respond ONLY with a JSON object of this exact shape (no text, no markdown):
{{"scores": [{{"n": 1, "s": 0.4}}, {{"n": 2, "s": -0.2}}, ...]}}

News to score:
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

    # I titoli GDELT arrivano con spazi attorno alla punteggiatura
    # ("Netflix , Inc . $NFLX", "Shares Up 1 . 6 %"): ripulirli prima di darli
    # al modello evita che li interpreti come frasi spezzate.
    def _titolo(t: str) -> str:
        t = t or ""
        t = re.sub(r"(\d)\s*([.,])\s*(\d)", r"\1\2\3", t)   # "1 . 6" -> "1.6"
        t = re.sub(r"(\d)\s*-\s*(\w)", r"\1-\2", t)          # "52 - Week" -> "52-Week"
        t = re.sub(r"\s+([,.;:%!?])", r"\1", t)              # spazio prima della punteggiatura
        t = re.sub(r"\(\s+", "(", t)
        t = re.sub(r"\s+\)", ")", t)
        return re.sub(r"\s{2,}", " ", t).strip()

    items_text = "\n".join(
        f"{i+1}. {_titolo(a['title'])} — {(a.get('summary') or '')[:120]}"
        for i, a in enumerate(articles)
    )
    prompt = BATCH_PROMPT.format(items=items_text)

    try:
        response = _get_groq().chat.completions.create(
            model=GROQ_SCORE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            # ~18 token per elemento {"n":12,"s":-0.4}, più margine per la cornice
            # JSON. Con un tetto fisso troppo basso la risposta veniva TRONCATA e
            # gli ultimi articoli restavano senza punteggio.
            max_tokens=120 + 20 * len(articles),
            # 0 e non 0.1: con 0.1 la stessa identica notizia riceveva punteggi
            # diversi in run diversi (osservato in produzione: +0.3 e -0.6).
            temperature=0,
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

        def _pulisci(v) -> float | None:
            try:
                return round(max(-1.0, min(1.0, float(v))), 4)
            except (TypeError, ValueError):
                return None

        result: list[float | None] = [None] * len(articles)

        # Formato con indice esplicito: {"n": 3, "s": 0.4}.
        # È l'unico affidabile. Prima si mappava per POSIZIONE: se il modello
        # saltava un articolo, tutti i punteggi successivi scalavano di uno e
        # finivano sulla notizia sbagliata, in silenzio. È così che nascevano i
        # sentiment assurdi (una notizia sul litio segnata +0.3 in un batch e
        # -0.6 in un altro). Con l'indice, un elemento saltato resta None e
        # basta: non contamina i vicini.
        con_indice = [x for x in scores if isinstance(x, dict)]
        if con_indice:
            fuori_range = 0
            for x in con_indice:
                n = x.get("n", x.get("i", x.get("index")))
                try:
                    pos = int(n) - 1          # il prompt numera da 1
                except (TypeError, ValueError):
                    continue
                if 0 <= pos < len(articles):
                    result[pos] = _pulisci(x.get("s", x.get("score")))
                else:
                    fuori_range += 1
            if fuori_range:
                logger.warning("Groq: %d indici fuori range su %d articoli",
                               fuori_range, len(articles))
        else:
            # Formato legacy (lista nuda di numeri): accettato SOLO se la
            # lunghezza combacia esattamente. Se non combacia non sappiamo
            # quale articolo sia stato saltato, quindi è più sicuro scartare
            # tutto il batch che assegnare punteggi a caso.
            if len(scores) != len(articles):
                logger.warning("Groq: %d punteggi per %d articoli, batch scartato "
                               "(rischio disallineamento)", len(scores), len(articles))
                return None
            result = [_pulisci(s) for s in scores]

        mancanti = sum(1 for r in result if r is None)
        if mancanti:
            logger.info("Groq: %d/%d articoli senza punteggio valido (restano com'erano)",
                        mancanti, len(articles))
        return result

    except json.JSONDecodeError as e:
        logger.warning("JSON non valido da Groq: %s | Raw: %r", e, raw[:200])
        return None
    except Exception as e:
        logger.error("Errore Groq batch (%s): %s", GROQ_SCORE_MODEL, e)
        return None


def rescore_non_av_news(ticker: str, batch_size: int = 10,
                         max_articles: int = 250) -> int:
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
              -- Il filtro sul NOME della fonte non bastava: Alpha Vantage
              -- salva le sue righe col nome della testata (Benzinga,
              -- MarketBeat), quindi questa riga da sola ne intercettava
              -- pochissime e Groq ri-classificava punteggi che Alpha Vantage
              -- aveva già calcolato meglio, sul suo stesso ticker. Il filtro
              -- che conta è quello su score_source, qui sotto.
              AND source != 'Alpha Vantage'
              AND COALESCE(score_source, 'vader') NOT IN ('llm2', 'av')
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
                    "UPDATE news SET sentiment = data.score, score_source = 'llm2' "
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
