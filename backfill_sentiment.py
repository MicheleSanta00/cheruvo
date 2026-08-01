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

BATCH = 15                 # articoli per richiesta Groq (prompt più corto = meno 429)
PAUSE = 4.0                # secondi tra i batch (asseconda il rate-limit)
MAX_UPDATES = int(os.environ.get("BACKFILL_MAX", "100000"))   # cap per run (di fatto: usa il tempo)
TIME_BUDGET_SEC = 50 * 60  # esce PULITO prima del timeout del workflow (55 min)
STOP_AFTER_FAILS = 6       # batch falliti di fila → probabile limite giornaliero → stop
BACKOFF = [20, 40, 60, 90, 120, 180]   # attesa crescente sui 429


def _count_remaining() -> int:
    pool = get_pool(); conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT count(*) FROM news
            WHERE source <> 'Alpha Vantage'
              AND COALESCE(score_source, 'vader') <> 'llm2'
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
              AND COALESCE(score_source, 'vader') <> 'llm2'
            ORDER BY published_date DESC NULLS LAST
            LIMIT %s
        """, (limit,))
        rows = cur.fetchall()
        cur.close()
    finally:
        pool.putconn(conn)
    return rows


def _apply(ids_scores):
    """
    Aggiorna sentiment + score_source='llm2' solo per gli score validi.

    Il marcatore è VERSIONATO ('llm2', non 'llm') perché i punteggi scritti
    dalla versione precedente erano inaffidabili: il modello rispondeva con una
    lista posizionale e, se saltava un articolo, tutti i punteggi successivi
    finivano sulla notizia sbagliata. Quelle righe risultavano già 'llm' e non
    sarebbero mai state riprocessate. Con il marcatore nuovo vengono ripassate
    tutte, e in futuro basterà incrementare la versione per rifare la bonifica.
    """
    import psycopg2.extras
    pairs = [(i, s) for i, s in ids_scores if s is not None]
    if not pairs:
        return 0
    pool = get_pool(); conn = pool.getconn()
    try:
        cur = conn.cursor()
        psycopg2.extras.execute_values(
            cur,
            "UPDATE news SET sentiment = data.score, score_source = 'llm2' "
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

    start = time.time()
    updated = 0
    fails = 0
    while updated < MAX_UPDATES and (time.time() - start) < TIME_BUDGET_SEC:
        rows = _fetch_chunk(BATCH)
        if not rows:
            log.info("Storico esaurito — bonifica completata!")
            break

        articles = [{"title": r[1], "summary": r[2] or ""} for r in rows]
        ids = [r[0] for r in rows]
        scores = score_batch(articles)

        if scores is None:
            wait = BACKOFF[min(fails, len(BACKOFF) - 1)]
            fails += 1
            log.warning("Rate-limit (%d/%d) — attendo %ds e riprovo.", fails, STOP_AFTER_FAILS, wait)
            if fails >= STOP_AFTER_FAILS:
                log.info("Probabile limite giornaliero Groq raggiunto. Riprendi domani: ripartirà da qui.")
                break
            time.sleep(wait)
            continue

        fails = 0
        n = _apply(list(zip(ids, scores)))
        updated += n
        if updated % 300 < BATCH:
            log.info("Aggiornate ~%d news in questo run…", updated)
        time.sleep(PAUSE)

    if (time.time() - start) >= TIME_BUDGET_SEC:
        log.info("Tempo del run esaurito (uscita pulita). Rilancia per continuare.")

    left = _count_remaining()
    log.info("Fatto. Aggiornate in questo run: %d · ancora da ripassare: %d", updated, left)
    if left > 0:
        log.info("Rilancia il workflow per continuare (riparte da solo).")


if __name__ == "__main__":
    main()
