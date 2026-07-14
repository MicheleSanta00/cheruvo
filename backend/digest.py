"""
digest.py — Digest email settimanale della watchlist.

Ogni lunedì (primo run utile del cron updater) ogni utente con watchlist
riceve il riepilogo della settimana: sentiment medio 7 giorni per ticker,
variazione vs settimana precedente e le 2 notizie più forti.

- Free: 1 ticker nel digest (+ riga upgrade) · Pro: tutti (max 10)
- Anti-duplicato: tabella digest_log (user, settimana ISO)
- Disiscrizione: link con token HMAC (niente login) + toggle nel profilo
"""
import os
import hmac
import hashlib
import logging
from datetime import datetime, timezone

import resend
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import database
from auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/digest")

resend.api_key = os.environ.get("RESEND_API_KEY", "")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "alerts@appcheruvo.com")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://app.cheruvo.com")
BACKEND_PUBLIC_URL = os.environ.get(
    "BACKEND_PUBLIC_URL", "https://financial-sentiment-analysis-20px.onrender.com"
)

FREE_TICKERS = 1     # quanti ticker vede un utente Free nel digest
PRO_TICKERS = 10     # cap per i Pro (email leggibile)


def _conn():
    # risoluzione dinamica (database.get_pool) così i test possono patchare il pool
    # anche se questo modulo è già stato importato
    return database.get_pool().getconn()

def _rel(conn):
    database.get_pool().putconn(conn)


def init_digest_tables():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS digest_prefs (
                user_id    UUID PRIMARY KEY,
                enabled    BOOLEAN NOT NULL DEFAULT TRUE,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS digest_log (
                user_id UUID NOT NULL,
                week    TEXT NOT NULL,
                sent_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (user_id, week)
            );
        """)
        conn.commit()
        cur.close()
    finally:
        _rel(conn)


# ── Token di disiscrizione (HMAC: nessun login richiesto dal link email) ────
def _secret() -> bytes:
    s = os.environ.get("DIGEST_SECRET") or os.environ.get("DATABASE_URL", "cheruvo")
    return hashlib.sha256(s.encode()).digest()


def unsubscribe_token(user_id: str) -> str:
    return hmac.new(_secret(), str(user_id).encode(), hashlib.sha256).hexdigest()[:32]


def _token_valid(user_id: str, token: str) -> bool:
    return hmac.compare_digest(unsubscribe_token(user_id), token or "")


def _week_key(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    y, w, _ = now.isocalendar()
    return f"{y}-W{w:02d}"


def _pick_tickers(tickers: list[str], plan: str) -> list[str]:
    """Free: il primo ticker · Pro: tutti fino al cap."""
    return tickers[:FREE_TICKERS] if plan != "pro" else tickers[:PRO_TICKERS]


# ── Dati della settimana ────────────────────────────────────────────────────
def get_recipients() -> list[dict]:
    """Utenti con watchlist, email e digest attivo: [{user_id, email, plan, tickers}]"""
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT u.id, u.email, COALESCE(s.status, 'free') AS plan,
                   array_agg(w.ticker ORDER BY w.ticker) AS tickers
            FROM watchlist w
            JOIN auth.users u ON u.id = w.user_id
            LEFT JOIN subscriptions s ON s.user_id = w.user_id
            LEFT JOIN digest_prefs dp ON dp.user_id = w.user_id
            WHERE COALESCE(dp.enabled, TRUE)
              AND u.email IS NOT NULL
            GROUP BY u.id, u.email, s.status
        """)
        rows = cur.fetchall()
        cur.close()
    finally:
        _rel(conn)
    return [{"user_id": str(r[0]), "email": r[1],
             "plan": "pro" if r[2] == "pro" else "free",
             "tickers": list(r[3] or [])} for r in rows]


def get_week_stats(tickers: list[str]) -> dict:
    """Per ogni ticker: media 7gg, n. news, delta vs 7gg precedenti, top 2 news."""
    if not tickers:
        return {}
    ph = ",".join(["%s"] * len(tickers))
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT ticker,
                   AVG(sentiment) FILTER (WHERE published_date >= NOW() - INTERVAL '7 days')  AS avg_now,
                   COUNT(*)       FILTER (WHERE published_date >= NOW() - INTERVAL '7 days')  AS n_now,
                   AVG(sentiment) FILTER (WHERE published_date <  NOW() - INTERVAL '7 days'
                                            AND published_date >= NOW() - INTERVAL '14 days') AS avg_prev
            FROM news
            WHERE ticker IN ({ph})
              AND published_date >= NOW() - INTERVAL '14 days'
            GROUP BY ticker
        """, tickers)
        agg = {r[0]: {"avg": float(r[1]) if r[1] is not None else None,
                      "n": int(r[2] or 0),
                      "prev": float(r[3]) if r[3] is not None else None}
               for r in cur.fetchall()}

        cur.execute(f"""
            SELECT ticker, title, url, sentiment FROM (
                SELECT ticker, title, url, sentiment,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY ABS(sentiment) DESC) AS rn
                FROM news
                WHERE published_date >= NOW() - INTERVAL '7 days'
                  AND ticker IN ({ph})
            ) t WHERE rn <= 2
        """, tickers)
        for tk, title, url, sent in cur.fetchall():
            agg.setdefault(tk, {"avg": None, "n": 0, "prev": None})
            agg[tk].setdefault("news", []).append(
                {"title": title, "url": url, "sentiment": float(sent or 0)})
        cur.close()
    finally:
        _rel(conn)
    return agg


# ── Email HTML ──────────────────────────────────────────────────────────────
def _chip(score: float | None) -> str:
    if score is None:
        return '<span style="color:#888">n.d.</span>'
    color = "#16a34a" if score > 0.08 else "#dc2626" if score < -0.08 else "#6b7280"
    return (f'<span style="color:{color};font-weight:600">'
            f'{"+" if score > 0 else ""}{score:.2f}</span>')


def _build_digest_html(user: dict, stats: dict, shown: list[str]) -> str:
    blocks = ""
    for tk in shown:
        s = stats.get(tk, {})
        avg, prev = s.get("avg"), s.get("prev")
        delta_html = ""
        if avg is not None and prev is not None:
            d = avg - prev
            arrow = "▲" if d >= 0 else "▼"
            dcolor = "#16a34a" if d >= 0 else "#dc2626"
            delta_html = (f'<span style="color:{dcolor};font-size:12px"> {arrow} '
                          f'{"+" if d > 0 else ""}{d:.2f} vs settimana scorsa</span>')
        news_html = ""
        for nw in (s.get("news") or [])[:2]:
            news_html += (f'<div style="padding:6px 0;font-size:13px">'
                          f'{_chip(nw["sentiment"])} '
                          f'<a href="{nw["url"]}" style="color:#333;text-decoration:none">{nw["title"][:110]}</a></div>')
        blocks += f"""
        <div style="border:1px solid #eee;border-radius:10px;padding:14px 16px;margin-bottom:12px">
          <div style="font-size:15px;font-weight:700">{tk}
            <span style="font-size:14px;margin-left:8px">{_chip(avg)}</span>{delta_html}
            <span style="color:#999;font-size:12px;float:right">{s.get('n', 0)} news</span>
          </div>
          {news_html}
        </div>"""

    upsell = ""
    if user["plan"] != "pro" and len(user["tickers"]) > len(shown):
        upsell = (f'<p style="font-size:13px;color:#666;background:#f6f8ff;border-radius:8px;padding:10px 14px">'
                  f'Stai vedendo {len(shown)} ticker su {len(user["tickers"])} della tua watchlist. '
                  f'<a href="{FRONTEND_URL}" style="color:#1e5cff">Con Pro il digest è completo →</a></p>')

    unsub = f"{BACKEND_PUBLIC_URL}/api/digest/unsubscribe?u={user['user_id']}&t={unsubscribe_token(user['user_id'])}"
    return f"""
    <div style="font-family:sans-serif;max-width:540px;margin:0 auto;padding:32px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:24px">
        <div style="width:32px;height:32px;background:#1e5cff;border-radius:8px"></div>
        <span style="font-size:16px;font-weight:500">Cheruvo</span>
      </div>
      <h2 style="font-size:20px;margin-bottom:6px">La tua settimana sui mercati</h2>
      <p style="color:#666;margin-bottom:20px">Sentiment degli ultimi 7 giorni per la tua watchlist.</p>
      {blocks}
      {upsell}
      <a href="{FRONTEND_URL}" style="display:inline-block;margin-top:16px;background:#1e5cff;color:white;
         padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:500">Apri la dashboard →</a>
      <p style="color:#bbb;font-size:11px;margin-top:28px">
        Ricevi questo digest ogni lunedì perché hai ticker in watchlist su Cheruvo.<br>
        <a href="{unsub}" style="color:#999">Disattiva il digest</a> · puoi riattivarlo dal tuo profilo.
      </p>
    </div>"""


# ── Invio ───────────────────────────────────────────────────────────────────
def _already_sent(user_id: str, week: str) -> bool:
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM digest_log WHERE user_id = %s AND week = %s", (user_id, week))
        r = cur.fetchone()
        cur.close()
    finally:
        _rel(conn)
    return r is not None


def _mark_sent(user_id: str, week: str):
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO digest_log (user_id, week) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (user_id, week))
        conn.commit()
        cur.close()
    finally:
        _rel(conn)


def send_weekly_digests(force: bool = False) -> int:
    """Entry point per updater.py. Invia solo di lunedì (una volta a settimana per utente)."""
    now = datetime.now(timezone.utc)
    if not force and now.weekday() != 0:   # 0 = lunedì
        logger.info("[Digest] Non è lunedì — skip.")
        return 0
    if not resend.api_key:
        logger.warning("[Digest] RESEND_API_KEY mancante — skip.")
        return 0

    week = _week_key(now)
    recipients = get_recipients()
    if not recipients:
        logger.info("[Digest] Nessun destinatario con watchlist.")
        return 0

    sent = 0
    for user in recipients:
        try:
            if _already_sent(user["user_id"], week):
                continue
            shown = _pick_tickers(user["tickers"], user["plan"])
            stats = get_week_stats(shown)
            # niente email vuote: serve almeno un ticker con dati della settimana
            if not any(stats.get(t, {}).get("n") for t in shown):
                continue
            parts = [f"{t} {stats[t]['avg']:+.2f}" for t in shown
                     if stats.get(t, {}).get("avg") is not None][:3]
            subject = "Il tuo mercato, questa settimana" + (f" — {', '.join(parts)}" if parts else "")
            resend.Emails.send({
                "from": FROM_EMAIL,
                "to": user["email"],
                "subject": subject,
                "html": _build_digest_html(user, stats, shown),
            })
            _mark_sent(user["user_id"], week)
            sent += 1
            logger.info("[Digest] Inviato a %s (%d ticker)", user["email"], len(shown))
        except Exception as e:
            logger.error("[Digest] Errore per %s: %s", user.get("email"), e)

    logger.info("[Digest] Completato: %d email.", sent)
    return sent


# ── Endpoint: disiscrizione (dal link email) e preferenza (dall'app) ───────
@router.get("/unsubscribe", response_class=HTMLResponse)
def unsubscribe(u: str, t: str):
    if not _token_valid(u, t):
        raise HTTPException(status_code=403, detail="Link non valido")
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO digest_prefs (user_id, enabled, updated_at) VALUES (%s, FALSE, NOW())
            ON CONFLICT (user_id) DO UPDATE SET enabled = FALSE, updated_at = NOW()
        """, (u,))
        conn.commit()
        cur.close()
    finally:
        _rel(conn)
    return HTMLResponse("""<!DOCTYPE html><html lang="it"><head><meta charset="utf-8">
      <meta name="viewport" content="width=device-width,initial-scale=1"><title>Cheruvo</title></head>
      <body style="font-family:sans-serif;background:#0b0f16;color:#e6edf3;display:flex;
        align-items:center;justify-content:center;height:100vh;margin:0;text-align:center">
      <div><h2>Digest disattivato ✓</h2>
      <p style="color:#8b949e">Non riceverai più il riepilogo settimanale.<br>
      Puoi riattivarlo in ogni momento dal tuo profilo su
      <a href="https://app.cheruvo.com" style="color:#60a5fa">app.cheruvo.com</a>.</p></div></body></html>""")


class PrefsIn(BaseModel):
    enabled: bool


@router.get("/prefs")
def get_prefs(user: dict = Depends(get_current_user)):
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT enabled FROM digest_prefs WHERE user_id = %s", (user["sub"],))
        r = cur.fetchone()
        cur.close()
    finally:
        _rel(conn)
    return {"enabled": bool(r[0]) if r is not None else True}


@router.put("/prefs")
def set_prefs(body: PrefsIn, user: dict = Depends(get_current_user)):
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO digest_prefs (user_id, enabled, updated_at) VALUES (%s, %s, NOW())
            ON CONFLICT (user_id) DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = NOW()
        """, (user["sub"], body.enabled))
        conn.commit()
        cur.close()
    finally:
        _rel(conn)
    return {"enabled": body.enabled}
