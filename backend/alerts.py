"""
alerts.py — Sistema di alert sentiment per Cheruvo.
"""
import os
import sys

# Fix import path quando chiamato da updater.py nella root
sys.path.insert(0, os.path.dirname(__file__))

import resend
from database import get_pool

resend.api_key = os.environ.get("RESEND_API_KEY", "")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "alerts@appcheruvo.com")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://appcheruvo.vercel.app")


def _conn():
    return get_pool().getconn()

def _rel(conn):
    get_pool().putconn(conn)


def get_pro_users_watchlists() -> dict[str, list[str]]:
    """Restituisce {email: [ticker, ...]} solo per utenti PRO con watchlist."""
    conn = _conn()
    try:
        cur = conn.cursor()
        # Join tra subscriptions (PRO) e watchlist
        cur.execute("""
            SELECT s.email, w.ticker
            FROM subscriptions s
            JOIN watchlist w ON w.user_id = s.user_id
            WHERE s.status = 'pro'
            ORDER BY s.email, w.ticker
        """)
        rows = cur.fetchall()
        cur.close()
    finally:
        _rel(conn)

    result: dict[str, list[str]] = {}
    for email, ticker in rows:
        result.setdefault(email, []).append(ticker)
    return result


def get_sentiment_alerts(tickers: list[str]) -> list[dict]:
    """Ritorna ticker con sentiment significativo (positivo o negativo)."""
    if not tickers:
        return []
    conn = _conn()
    try:
        cur = conn.cursor()
        placeholders = ",".join(["%s"] * len(tickers))
        cur.execute(f"""
            SELECT ticker, AVG(sentiment) as avg_sent, COUNT(*) as news_count
            FROM news
            WHERE published_date >= NOW() - INTERVAL '24 hours'
              AND ticker IN ({placeholders})
            GROUP BY ticker
            HAVING ABS(AVG(sentiment)) > 0.2
            ORDER BY ABS(AVG(sentiment)) DESC
        """, tickers)
        rows = cur.fetchall()
        cur.close()
    finally:
        _rel(conn)

    return [
        {"ticker": r[0], "avg_sentiment": round(r[1], 3), "news_count": r[2]}
        for r in rows
    ]


def _sentiment_label(score: float) -> tuple[str, str, str]:
    """Ritorna (emoji, label, colore) in base al sentiment."""
    if score >= 0.3:
        return "🟢", "molto positivo", "#16a34a"
    elif score >= 0.15:
        return "📈", "positivo", "#22c55e"
    elif score <= -0.3:
        return "🔴", "molto negativo", "#dc2626"
    else:
        return "📉", "negativo", "#ef4444"


def _build_email_html(alerts: list[dict]) -> str:
    rows_html = ""
    for a in alerts:
        emoji, label, color = _sentiment_label(a["avg_sentiment"])
        rows_html += f"""
        <tr>
          <td style="padding:10px 0;border-bottom:1px solid #f0f0f0;font-weight:500">{a['ticker']}</td>
          <td style="padding:10px 0;border-bottom:1px solid #f0f0f0;color:{color};font-weight:500">
            {emoji} {label} ({a['avg_sentiment']:+.3f})
          </td>
          <td style="padding:10px 0;border-bottom:1px solid #f0f0f0;color:#888">
            {a['news_count']} news
          </td>
        </tr>"""

    return f"""
    <div style="font-family:sans-serif;max-width:520px;margin:0 auto;padding:32px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:28px">
        <div style="width:32px;height:32px;background:#1e5cff;border-radius:8px"></div>
        <span style="font-size:16px;font-weight:500">Cheruvo</span>
      </div>
      <h2 style="font-size:20px;margin-bottom:6px">Sentiment alert nelle ultime 24h</h2>
      <p style="color:#666;margin-bottom:20px">Movimenti significativi nei tuoi ticker in watchlist.</p>
      <table style="width:100%;border-collapse:collapse;font-size:14px">
        <thead>
          <tr style="color:#888;font-size:12px;text-transform:uppercase">
            <th style="text-align:left;padding-bottom:8px">Ticker</th>
            <th style="text-align:left;padding-bottom:8px">Sentiment</th>
            <th style="text-align:left;padding-bottom:8px">Notizie</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
      <a href="{FRONTEND_URL}" style="display:inline-block;margin-top:24px;background:#1e5cff;color:white;
         padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:500">
        Apri Cheruvo →
      </a>
      <p style="color:#bbb;font-size:11px;margin-top:28px">
        Ricevi questa email perché sei un utente PRO di Cheruvo con ticker in watchlist.<br>
        Alert generati ogni 6 ore via GitHub Actions.
      </p>
    </div>"""


def check_and_send_alerts():
    """Entry point principale — chiamato da updater.py."""
    print("[Alerts] Controllo alert sentiment PRO...")

    user_watchlists = get_pro_users_watchlists()
    if not user_watchlists:
        print("[Alerts] Nessun utente PRO con watchlist. Skip.")
        return

    # Raccogli tutti i ticker unici
    all_tickers = list({t for tickers in user_watchlists.values() for t in tickers})
    alerts_by_ticker = {a["ticker"]: a for a in get_sentiment_alerts(all_tickers)}

    if not alerts_by_ticker:
        print("[Alerts] Nessun movimento significativo nelle ultime 24h.")
        return

    sent = 0
    for email, tickers in user_watchlists.items():
        user_alerts = [alerts_by_ticker[t] for t in tickers if t in alerts_by_ticker]
        if not user_alerts:
            continue

        subject = f"Cheruvo Alert — {', '.join(a['ticker'] for a in user_alerts[:3])}"
        if len(user_alerts) > 3:
            subject += f" +{len(user_alerts)-3} altri"

        try:
            resend.Emails.send({
                "from": FROM_EMAIL,
                "to": email,
                "subject": subject,
                "html": _build_email_html(user_alerts),
            })
            print(f"[Alerts] ✓ Inviato a {email} ({len(user_alerts)} ticker)")
            sent += 1
        except Exception as e:
            print(f"[Alerts] ✗ Errore per {email}: {e}")

    print(f"[Alerts] Completato: {sent} email inviate.")


if __name__ == "__main__":
    check_and_send_alerts()