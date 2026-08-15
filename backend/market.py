"""
market.py — Screener pubblico "Mercato oggi".

Classifica i ticker per sentiment recente calcolato dalle news già in DB:
- finestra "oggi": ultime 48 ore (le news finanziarie non escono di notte/weekend)
- delta: differenza rispetto alla media dei 7 giorni precedenti
- almeno MIN_NEWS news nella finestra per entrare in classifica: sotto quella
  soglia la media è più incerta della scala su cui viene mostrata, e il primo
  posto è sorteggiato. Le motivazioni coi numeri stanno accanto alla costante.

Endpoint PUBBLICO (niente login): alimenta la sezione live della landing e la
vista "Mercato" nell'app. Risposta in cache 15 minuti (Redis o in-memory),
quindi il DB viene interrogato al massimo 4 volte l'ora anche con traffico.
"""
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter

from database import get_pool
from cache import cache_get, cache_set

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/market")


def _finestra(secondi: int) -> int:
    """
    Numero della finestra temporale corrente.

    La chiave di cache lo include, così cambia da sola a ogni intervallo e il
    dato viene ricalcolato ANCHE se la scadenza lato Redis non funziona.
    Serviva davvero: /market/stats è rimasto congelato al 14 luglio per cinque
    giorni e /market/today ha servito la stessa risposta per oltre due ore
    nonostante una scadenza dichiarata di 15 minuti.
    """
    return int(time.time() // secondi)


MARKET_TTL = 15 * 60      # 15 minuti
WINDOW_HOURS = 48         # finestra "oggi"
BASELINE_DAYS = 7         # confronto per il delta
# Quante righe torna la classifica.
#
# Era 20, e sembrava ragionevole: in home se ne mostrano cinque per parte, chi
# ne vuole venti e' gia' tanto. Ma questo endpoint non serve solo alla
# classifica: la barra laterale ci prende i punteggi di TUTTI i titoli seguiti,
# con una chiamata sola, pubblica e in cache per un quarto d'ora.
#
# Con il taglio a venti, un titolo fuori dai primi venti per sentiment non
# c'era, e la barra doveva chiederlo a `/api/news` uno per uno. Quell'endpoint
# ha un limite di 20 al minuto: con sei titoli mancanti, piu' le chiamate che
# la pagina fa da sola, piu' un paio di ricariche, le richieste venivano
# respinte e l'errore finiva in un `catch` silenzioso. Risultato: un trattino
# al posto del punteggio su titoli che i dati ce li avevano eccome. META il 15
# agosto 2026 aveva 179 notizie e media -0.16, e mostrava un trattino.
#
# Sessanta coprono i 48 titoli seguiti con margine. Costa qualche centinaio di
# byte su una risposta gia' in cache, e toglie di mezzo N richieste fragili.
# Chi vuole una classifica corta la taglia lato frontend, che e' dove si decide
# cosa mostrare.
MAX_ROWS = 60

# News minime per entrare in classifica.
#
# Era 2, ed è stato il difetto più visibile del prodotto: il 7 agosto 2026 la
# home apriva con "PIÙ RIALZISTI: 1. ADA +0,34 con 3 news, 2. BCH +0,25 con 2".
# Un utente legge quella riga come "ADA è la moneta col sentiment migliore".
# Non lo è: è la moneta su cui abbiamo raccolto due articoli.
#
# I conti, con la variabilità dei punteggi misurata sull'archivio (σ ≈ 0,45).
# L'errore standard di una media è σ/√n:
#
#     n = 2  →  ±0,32     n = 5  →  ±0,20
#     n = 3  →  ±0,26     n = 10 →  ±0,14
#
# In classifica i punteggi stanno fra -0,10 e +0,35, quindi con due articoli
# l'incertezza è più grande di tutta la scala: il primo posto è sorteggiato.
#
# Cinque non rende il numero affidabile, rende la classifica non ridicola, ed
# è la stessa soglia che `verifica_segnale.py` pretende per considerare un
# giorno utilizzabile. Dieci sarebbe più difendibile ma oggi lascerebbe in
# classifica una moneta sola, e una classifica di uno non è una classifica.
#
# Da rivedere quando il volume cresce: se un giorno dieci monete superano
# dieci news, questa soglia va alzata invece che lasciata lì per inerzia.
MIN_NEWS = 5


def _fetch_market() -> list[dict]:
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        # WINDOW_HOURS/BASELINE_DAYS sono costanti di modulo (interi), non input utente:
        # sicuri dentro la f-string. MIN_NEWS e MAX_ROWS passano come parametri.
        # UNA NOTIZIA, UN VOTO — ANCHE QUI
        #
        # Prima questa query faceva AVG e COUNT su tutte le righe. Il 15 agosto
        # 2026, misurando un campione, 61 righe su 300 erano lo stesso lancio
        # d'agenzia ("Intel targets $15 billion stock sale after rally") ripreso
        # da 61 testate.
        #
        # Con quel conteggio un titolo poteva entrare in classifica con UNA
        # notizia sola rilanciata cinque volte, e comparire in home con scritto
        # "5 news". Sia la soglia MIN_NEWS sia la media erano falsate dalla
        # sindacazione invece che dai fatti.
        #
        # Le riprese si fondono prima: stesso ticker e stesso titolo diventano
        # una voce sola, col punteggio medio fra le copie. Il conteggio delle
        # riprese non si perde, esce come `riprese`.
        #
        # La normalizzazione del titolo rispecchia `giornaliero.chiave_titolo`:
        # minuscole, punteggiatura a spazi, spazi collassati, primi 90
        # caratteri. Le due DEVONO restare uguali, altrimenti il grafico e la
        # classifica fondono gruppi diversi e mostrano numeri che non tornano.
        #
        # Un titolo vuoto non si fonde con gli altri titoli vuoti: senza testo
        # non si puo' dire che due notizie siano la stessa, e fonderle
        # cancellerebbe righe vere. Per questo c'e' il ripiego sull'id.
        chiave = ("left(btrim(regexp_replace(regexp_replace("
                  "lower(coalesce(title, '')), '[^[:alnum:][:space:]]', ' ', 'g'"
                  "), '\\s+', ' ', 'g')), 90)")
        cur.execute(f"""
            WITH distinte AS (
                SELECT ticker,
                       COALESCE(NULLIF({chiave}, ''), 'id:' || id::text) AS chiave,
                       AVG(sentiment) AS sentiment,
                       COUNT(*)       AS copie
                FROM news
                WHERE published_date >= NOW() - INTERVAL '{int(WINDOW_HOURS)} hours'
                GROUP BY ticker, 2
            ),
            recent AS (
                SELECT ticker,
                       AVG(sentiment)      AS avg_now,
                       COUNT(*)            AS n_now,
                       SUM(copie) - COUNT(*) AS riprese
                FROM distinte
                GROUP BY ticker
            ),
            distinte_prima AS (
                SELECT ticker,
                       COALESCE(NULLIF({chiave}, ''), 'id:' || id::text) AS chiave,
                       AVG(sentiment) AS sentiment
                FROM news
                WHERE published_date <  NOW() - INTERVAL '{int(WINDOW_HOURS)} hours'
                  AND published_date >= NOW() - INTERVAL '{int(BASELINE_DAYS)} days'
                GROUP BY ticker, 2
            ),
            baseline AS (
                SELECT ticker, AVG(sentiment) AS avg_prev
                FROM distinte_prima
                GROUP BY ticker
            )
            SELECT r.ticker, r.avg_now, r.n_now, b.avg_prev, r.riprese
            FROM recent r
            LEFT JOIN baseline b ON b.ticker = r.ticker
            WHERE r.n_now >= %s
            ORDER BY r.avg_now DESC
            LIMIT %s
        """, (MIN_NEWS, MAX_ROWS))
        rows = cur.fetchall()
        cur.close()
    finally:
        pool.putconn(conn)

    out = []
    for t, avg_now, n_now, avg_prev, riprese in rows:
        avg_now = round(float(avg_now or 0), 3)
        delta = round(avg_now - float(avg_prev), 3) if avg_prev is not None else None
        out.append({"ticker": t, "sentiment": avg_now, "news": int(n_now),
                    "delta": delta, "riprese": int(riprese or 0)})
    return out


STATS_TTL = 30 * 60


@router.get("/stats")
def market_stats():
    """Contatori pubblici per la landing: news di oggi, totali, ticker seguiti."""
    chiave = f"market:stats:{_finestra(STATS_TTL)}"
    cached = cache_get(chiave, ttl=STATS_TTL)
    if cached is not None:
        return cached

    stats = {"news_today": 0, "news_total": 0, "tickers": 0, "last_update": None}
    try:
        pool = get_pool()
        conn = pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT
                  COUNT(*) FILTER (WHERE published_date >= NOW() - INTERVAL '24 hours'),
                  COUNT(*),
                  COUNT(DISTINCT ticker),
                  MAX(published_date)
                FROM news
            """)
            r = cur.fetchone()
            cur.close()
        finally:
            pool.putconn(conn)
        if r:
            stats = {"news_today": int(r[0] or 0), "news_total": int(r[1] or 0),
                     "tickers": int(r[2] or 0),
                     "last_update": r[3].isoformat() if r[3] else None}
    except Exception as e:
        logger.error("market stats error: %s", e)

    cache_set(chiave, stats, ttl=STATS_TTL if stats["news_total"] else 60)
    return stats


ANOMALIE_TTL = 15 * 60


@router.get("/anomalie")
def market_anomalie():
    """
    Cosa si è staccato oggi dalla propria normalità.

    Pubblico come /today, perché è la risposta alla domanda che un livello non
    sa dare: "è successo qualcosa?". Le monete ancora in apprendimento restano
    nell'elenco con il loro stato, invece di sparire: sapere che di una moneta
    non sappiamo ancora dire niente è più onesto che far finta che sia calma.
    """
    chiave = f"market:anomalie:{_finestra(ANOMALIE_TTL)}"
    cached = cache_get(chiave, ttl=ANOMALIE_TTL)
    if cached is not None:
        return cached

    try:
        import anomalie
        righe = anomalie.calcola()
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "baseline_giorni": anomalie.BASELINE_GIORNI,
            "minimo_giorni": anomalie.MINIMO_GIORNI,
            "soglia": anomalie.SOGLIA_Z,
            "anomalie": [r for r in righe if r["stato"] == "anomalia"],
            "righe": righe,
        }
    except Exception as e:
        logger.error("market anomalie error: %s", e)
        payload = {"updated_at": datetime.now(timezone.utc).isoformat(),
                   "anomalie": [], "righe": []}

    cache_set(chiave, payload, ttl=ANOMALIE_TTL if payload["righe"] else 60)
    return payload


@router.get("/today")
def market_today():
    """Classifica pubblica dei ticker per sentiment recente (cache 15 min)."""
    chiave = f"market:today:{_finestra(MARKET_TTL)}"
    cached = cache_get(chiave, ttl=MARKET_TTL)
    if cached is not None:
        return cached

    try:
        rows = _fetch_market()
    except Exception as e:
        logger.error("market today error: %s", e)
        rows = []

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "window_hours": WINDOW_HOURS,
        # La soglia viaggia col dato invece di essere riscritta a mano
        # nell'interfaccia: così quando cambia qui, cambia anche la frase che
        # l'utente legge, e le due non possono contraddirsi.
        "min_news": MIN_NEWS,
        "rows": rows,
    }
    # cache anche il risultato vuoto (60s) per non martellare il DB in caso di errori
    cache_set(chiave, payload, ttl=MARKET_TTL if rows else 60)
    return payload
