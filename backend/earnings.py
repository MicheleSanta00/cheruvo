"""
earnings.py — Calendario earnings con sentiment pre-conti.

"NVDA presenta i conti tra 5 giorni — sentiment degli ultimi 7 giorni: +0.31
e in salita": l'informazione più cercata dai retail prima delle trimestrali.

- Le date arrivano da yfinance e vengono salvate in earnings_calendar,
  aggiornate dal cron (updater.py) — mai chiamare yfinance a richiesta.
- GET /api/earnings/upcoming: il calendario lo vedono tutti (login richiesto);
  il sentiment pre-earnings e il trend sono SOLO Pro (leva di upgrade).
"""
import logging
from datetime import datetime, date, timezone

from fastapi import APIRouter, Depends

import database
from auth import get_current_user, get_user_tier
from cache import cache_get, cache_set

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/earnings")

WINDOW_DAYS = 14        # quanto avanti guarda il calendario
SENT_DAYS = 7           # finestra sentiment pre-earnings
CACHE_TTL = 30 * 60
STALE_HOURS = 24        # refresh date più vecchie di così


def _conn():
    return database.get_pool().getconn()

def _rel(conn):
    database.get_pool().putconn(conn)


def init_earnings_tables():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS earnings_calendar (
                ticker     TEXT PRIMARY KEY,
                next_date  DATE,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        conn.commit()
        cur.close()
    finally:
        _rel(conn)


# ── Refresh dal cron ────────────────────────────────────────────────────────
def _next_earnings_date(ticker: str):
    """Prossima data earnings via yfinance. None se non disponibile."""
    import yfinance as yf
    try:
        t = yf.Ticker(ticker)
        cal = t.calendar
        dates = None
        if isinstance(cal, dict):
            dates = cal.get("Earnings Date") or cal.get("Earnings High Date")
        if dates:
            d = dates[0] if isinstance(dates, (list, tuple)) else dates
            d = d.date() if hasattr(d, "date") and not isinstance(d, date) else d
            if isinstance(d, date) and d >= date.today():
                return d
        # fallback: tabella earnings_dates (contiene anche date future)
        try:
            df = t.get_earnings_dates(limit=8)
            if df is not None and len(df):
                future = [ts.date() for ts in df.index if ts.date() >= date.today()]
                if future:
                    return min(future)
        except Exception:
            pass
    except Exception as e:
        logger.warning("[Earnings] %s: %s", ticker, e)
    return None


def refresh_earnings(tickers: list[str]) -> int:
    """Aggiorna le date earnings per i ticker con dato più vecchio di 24h."""
    # Le criptovalute non depositano bilanci: filtrarle qui evita una chiamata
    # a yfinance per ognuna e righe vuote nel calendario.
    tickers = [t for t in tickers if not str(t).upper().endswith("-USD")]
    if not tickers:
        return 0
    conn = _conn()
    try:
        cur = conn.cursor()
        ph = ",".join(["%s"] * len(tickers))
        cur.execute(f"""
            SELECT ticker FROM earnings_calendar
            WHERE ticker IN ({ph})
              AND updated_at > NOW() - INTERVAL '{int(STALE_HOURS)} hours'
        """, tickers)
        fresh = {r[0] for r in cur.fetchall()}
        cur.close()
    finally:
        _rel(conn)

    todo = [t for t in tickers if t not in fresh]
    updated = 0
    for tk in todo:
        d = _next_earnings_date(tk)
        conn = _conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO earnings_calendar (ticker, next_date, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (ticker) DO UPDATE
                  SET next_date = EXCLUDED.next_date, updated_at = NOW()
            """, (tk, d))
            conn.commit()
            cur.close()
            updated += 1
        finally:
            _rel(conn)
    if updated:
        logger.info("[Earnings] %d ticker aggiornati", updated)
    return updated


# ── Endpoint ────────────────────────────────────────────────────────────────
def _upcoming_rows() -> list[dict]:
    """Ticker con earnings nei prossimi WINDOW_DAYS + sentiment pre-conti."""
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"""
            WITH up AS (
                SELECT ticker, next_date
                FROM earnings_calendar
                WHERE next_date IS NOT NULL
                  AND next_date >= CURRENT_DATE
                  AND next_date <= CURRENT_DATE + INTERVAL '{int(WINDOW_DAYS)} days'
            ),
            sent AS (
                SELECT n.ticker,
                       AVG(n.sentiment) FILTER (WHERE n.published_date >= NOW() - INTERVAL '{int(SENT_DAYS)} days')  AS avg_now,
                       COUNT(*)         FILTER (WHERE n.published_date >= NOW() - INTERVAL '{int(SENT_DAYS)} days')  AS n_now,
                       AVG(n.sentiment) FILTER (WHERE n.published_date <  NOW() - INTERVAL '{int(SENT_DAYS)} days'
                                                  AND n.published_date >= NOW() - INTERVAL '{int(SENT_DAYS) * 2} days') AS avg_prev
                FROM news n
                JOIN up ON up.ticker = n.ticker
                GROUP BY n.ticker
            )
            SELECT up.ticker, up.next_date, s.avg_now, s.n_now, s.avg_prev
            FROM up
            LEFT JOIN sent s ON s.ticker = up.ticker
            ORDER BY up.next_date, up.ticker
        """)
        rows = cur.fetchall()
        cur.close()
    finally:
        _rel(conn)

    out = []
    today = date.today()
    for tk, nd, avg_now, n_now, avg_prev in rows:
        sent = round(float(avg_now), 3) if avg_now is not None else None
        trend = None
        if avg_now is not None and avg_prev is not None:
            trend = round(float(avg_now) - float(avg_prev), 3)
        out.append({
            "ticker": tk,
            "date": nd.isoformat(),
            "days_left": (nd - today).days,
            "sentiment": sent,
            "trend": trend,
            "news": int(n_now or 0),
        })
    return out


@router.get("/upcoming")
def upcoming(user: dict = Depends(get_current_user)):
    """Calendario per tutti; sentiment/trend pre-conti solo Pro."""
    rows = cache_get("earnings:upcoming", ttl=CACHE_TTL)
    if rows is None:
        try:
            rows = _upcoming_rows()
        except Exception as e:
            logger.error("earnings upcoming error: %s", e)
            rows = []
        cache_set("earnings:upcoming", rows, ttl=CACHE_TTL if rows else 60)

    is_pro = get_user_tier(user["sub"]) == "pro"
    if not is_pro:
        rows = [{**r, "sentiment": None, "trend": None} for r in rows]
    return {"window_days": WINDOW_DAYS, "is_pro": is_pro, "rows": rows}
