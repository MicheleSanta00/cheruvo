"""
backfill_sentiment.py — Bonifica una tantum dello storico sentiment.

Contesto: un bug del vecchio rescore azzerava gli score, e VADER (dizionario
inglese) restituisce spesso 0.0 sulle news italiane/europee. Risultato: una
colonna di sentiment "neutri" a 0.00 nello scatter. Il cron ordinario
ri-classifica solo gli ultimi 7 giorni, quindi lo storico resta sporco.

Questo script ripassa TUTTE le news ancora con score VADER (score_source
diverso da 'llm'/'av') e le ri-classifica con Groq, senza limite temporale.

È SICURO e RIPRENDIBILE:
- processa solo le news 'vader' → non tocca Alpha Vantage né quelle già LLM;
- dopo ogni aggiornamento imposta score_source='llm', quindi rilanciandolo
  riparte da dove era rimasto, senza rifare il lavoro;
- se Groq va in rate limit, si ferma in modo pulito (le news non toccate
  restano com'erano) e basta rilanciarlo il giorno dopo.

Uso consigliato: modello veloce ad alto rate-limit per il volume.
  GROQ_SCORE_MODEL=llama-3.1-8b-instant  (default qui sotto)

Avvio:
  - da GitHub Actions: workflow "Backfill sentiment" (workflow_dispatch), oppure
  - in locale:  GROQ_API_KEY=... DATABASE_URL=... python backfill_sentiment.py
"""
import os
import sys
import time
import logging

# path: gli import stanno in backend/
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "backend"))

# Per il backfill di massa conviene il modello veloce (rate-limit alto).
os.environ.setdefault("GROQ_SCORE_MODEL", "llama-3.1-8b-instant")

from database import get_pool
from sentiment_groq import score_batch

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("backfill")

BATCH = 20                 # articoli per richiesta Groq
PAUSE = 2.0                # secondi tra i batch (rispetto rate-limit)
MAX_UPDATES = int(os.environ.get("BACKFILL_MAX", "6000"))   # cap per run
STOP_AFTER_FAILS = 3       # batch falliti di fila → stop (probabile rate-limit)


def _count_remaining() -> int:
    pool = get_pool(); conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT count(*) FROM news
            WHERE source <> 'Alpha Vantage'
              AND COALESCE(score_source, 'vader') = 'vader'
        """)
        n = cur.fetchone()[0]
        cur.close()
    finally:
        pool.putconn(conn)
    return int(n or 0)


def _fetch_chunk(limit: int):
    pool = get_pool(); conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, title, summary FROM news
            WHERE source <> 'Alpha Vantage'
              AND COALESCE(score_source, 'vader') = 'vader'
            ORDER BY published_date DESC NULLS LAST
            LIMIT %s
        """, (limit,))
        rows = cur.fetchall()
        cur.close()
    finally:
        pool.putconn(conn)
    return rows


def _apply(ids_scores):
    """Aggiorna sentiment + score_source='llm' solo per gli score validi."""
    import psycopg2.extras
    pairs = [(i, s) for i, s in ids_scores if s is not None]
    if not pairs:
        return 0
    pool = get_pool(); conn = pool.getconn()
    try:
        cur = conn.cursor()
        psycopg2.extras.execute_values(
            cur,
            "UPDATE news SET sentiment = data.score, score_source = 'llm' "
            "FROM (VALUES %s) AS data(id, score) WHERE news.id = data.id",
            pairs, template="(%s, %s::real)")
        conn.commit()
        cur.close()
    finally:
        pool.putconn(conn)
    return len(pairs)


def main():
    if not os.environ.get("GROQ_API_KEY"):
        log.error("GROQ_API_KEY mancante — impossibile procedere.")
        sys.exit(1)

    remaining = _count_remaining()
    log.info("News ancora con score VADER da ripassare: %d", remaining)
    log.info("Modello: %s · cap questo run: %d", os.environ["GROQ_SCORE_MODEL"], MAX_UPDATES)
    if remaining == 0:
        log.info("Niente da fare: lo storico è già pulito.")
        return

    updated = 0
    fails = 0
    while updated < MAX_UPDATES:
        rows = _fetch_chunk(BATCH)
        if not rows:
            log.info("Storico esaurito.")
            break

        articles = [{"title": r[1], "summary": r[2] or ""} for r in rows]
        ids = [r[0] for r in rows]
        scores = score_batch(articles)

        if scores is None:
            fails += 1
            log.warning("Batch fallito (%d/%d) — probabile rate-limit.", fails, STOP_AFTER_FAILS)
            if fails >= STOP_AFTER_FAILS:
                log.info("Mi fermo: rilancia lo script più tardi, riprenderà da qui.")
                break
            time.sleep(15)
            continue

        fails = 0
        n = _apply(list(zip(ids, scores)))
        updated += n
        if updated % 200 < BATCH:
            log.info("Aggiornate ~%d news…", updated)
        time.sleep(PAUSE)

    left = _count_remaining()
    log.info("Fatto. Aggiornate in questo run: %d · ancora da ripassare: %d", updated, left)
    if left > 0:
        log.info("Rilancia il workflow per continuare (riparte da solo).")


if __name__ == "__main__":
    main()
