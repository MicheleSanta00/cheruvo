"""
backfill_sentiment.py — Ripassa con Groq le notizie che non hanno ancora un
punteggio del modello (score_source diverso da 'llm2').

COSA FA DAVVERO, scritto il 24 settembre 2026.

Questo testo diceva "processa solo le news 'vader', non tocca Alpha Vantage
ne' quelle gia' LLM". La query invece prende tutto cio' che non e' 'llm2',
quindi ANCHE le righe 'gdelt', cioe' quelle col tono calcolato da GDELT sul
testo integrale, che il README dice che Groq non tocca. E il workflow gira
ogni notte, con un tetto di 1.500 righe: piu' di quante ne arrivino in un
giorno. In pratica ogni notte il tono GDELT della giornata veniva sostituito
dal punteggio del modello sul solo titolo, e perso per sempre. E' il motivo
per cui l'11 agosto l'archivio era llm2 al 99% e gdelt all'1%, e la
calibrazione fra i due si e' fermata con diciotto righe gdelt.

Cambiare adesso cosa si ripunteggia sposterebbe la scala di tutto il sito
dall'oggi al domani (le medie, la classifica, il rilevatore di anomalie
confrontano l'oggi con le quattro settimane prima, che sono llm2), quindi il
comportamento resta questo finche' non si decide. Cambiano tre cose:

  1. il tono GDELT non si butta piu': prima di scriverci sopra finisce nella
     colonna `tono_gdelt`, cosi' la calibrazione ha di nuovo i suoi dati;
  2. le righe di Fed, BCE ed ESMA tengono il marchio 'istituzionale' (vedi
     sentiment_groq.rescore_non_av_news: e' la nota di licenza);
  3. una riga a cui il modello non riesce a dare un punteggio viene saltata
     per il resto del giro. Prima veniva richiesta di nuovo a ogni lotto,
     essendo sempre la piu' recente: con quindici righe cosi' il giro girava
     a vuoto per cinquanta minuti bruciando la quota di Groq.

Avvio:
  - da GitHub Actions: workflow "Backfill sentiment" (ogni notte e a mano), oppure
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
os.environ.setdefault("GROQ_SCORE_MODEL", "openai/gpt-oss-20b")

from database import get_pool, init_database
from sentiment_groq import score_batch

# Righe che il giro non deve prendere: gia' punteggiate dal modello, oppure
# regolatorie gia' punteggiate (che tengono il loro marchio).
FATTE = ("llm2", "istituzionale_llm2")

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
              AND COALESCE(score_source, 'vader') <> ALL(%s)
        """, (list(FATTE),))
        n = cur.fetchone()[0]
        cur.close()
    finally:
        pool.putconn(conn)
    return int(n or 0)


def _fetch_chunk(limit: int, saltare=()):
    """Le prossime righe da ripassare, escluse quelle gia' fallite in questo giro."""
    pool = get_pool(); conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, title, summary FROM news
            WHERE source <> 'Alpha Vantage'
              AND COALESCE(score_source, 'vader') <> ALL(%s)
              AND NOT (id = ANY(%s))
            ORDER BY published_date DESC NULLS LAST
            LIMIT %s
        """, (list(FATTE), list(saltare), limit))
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
        # Il tono GDELT si mette da parte PRIMA di scriverci sopra, e il
        # marchio delle fonti regolatorie resta: vedi il testo in cima.
        psycopg2.extras.execute_values(
            cur,
            "UPDATE news SET "
            "tono_gdelt = CASE WHEN news.score_source = 'gdelt' "
            "THEN news.sentiment ELSE news.tono_gdelt END, "
            "sentiment = data.score, "
            "score_source = CASE WHEN news.score_source = 'istituzionale' "
            "THEN 'istituzionale_llm2' ELSE 'llm2' END "
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

    # La colonna tono_gdelt deve esistere prima del primo UPDATE: il
    # workflow puo' girare prima che il backend nuovo sia su Render.
    init_database()

    remaining = _count_remaining()
    log.info("News ancora con score VADER da ripassare: %d", remaining)
    log.info("Modello: %s · cap questo run: %d", os.environ["GROQ_SCORE_MODEL"], MAX_UPDATES)
    if remaining == 0:
        log.info("Niente da fare: lo storico è già pulito.")
        return

    start = time.time()
    updated = 0
    fails = 0
    saltati: set = set()     # righe senza punteggio in questo giro
    while updated < MAX_UPDATES and (time.time() - start) < TIME_BUDGET_SEC:
        rows = _fetch_chunk(BATCH, saltati)
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
        saltati.update(i for i, sc in zip(ids, scores) if sc is None)
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
