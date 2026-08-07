"""
alerts.py — Sistema di alert sentiment per Cheruvo.
"""
import os
import sys
import logging

# Fix import path quando chiamato da updater.py nella root
sys.path.insert(0, os.path.dirname(__file__))

import resend

logger = logging.getLogger(__name__)
from database import get_pool

resend.api_key = os.environ.get("RESEND_API_KEY", "")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "alerts@appcheruvo.com")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://app.cheruvo.com")


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
    """
    I ticker in watchlist su cui oggi è successo qualcosa di anomalo.

    Fino al 7 agosto 2026 questa funzione faceva un'altra cosa: prendeva le
    24 ore e teneva chi aveva `ABS(AVG(sentiment)) > 0.2`. Una soglia su un
    LIVELLO, e per questo sbagliata in tutte e due le direzioni. Scriveva per
    una moneta con tre articoli capitati sopra 0,2, e restava zitta il giorno
    in cui il volume di notizie su Bitcoin triplicava senza che la media si
    spostasse. Avvisava quando il numero era alto, mai quando era cambiato,
    che è l'unica cosa per cui vale la pena mandare un'email.

    Ora l'avviso nasce da `anomalie.py`, che confronta ogni moneta con la
    propria normalità delle quattro settimane precedenti. Se lo storico non
    basta ancora, non arriva niente: nessun avviso è meglio di un avviso
    fondato su due settimane di dati.
    """
    if not tickers:
        return []

    import anomalie

    voluti = {t.upper() for t in tickers}
    try:
        righe = anomalie.solo_anomalie(anomalie.calcola())
    except Exception as e:
        logger.error("anomalie non calcolabili: %s", e)
        return []

    fuori = []
    for r in righe:
        if r["ticker"].upper() not in voluti:
            continue
        fuori.append({
            "ticker": r["ticker"],
            "avg_sentiment": r["sentiment_oggi"] if r["sentiment_oggi"] is not None else 0.0,
            "news_count": r["notizie_oggi"],
            "notizie_tipiche": r["notizie_tipiche"],
            "z_volume": r["z_volume"],
            "z_tono": r["z_tono"],
        })
    return fuori


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


def _riga_motivo(a: dict) -> str:
    """
    Perché questa moneta è finita nell'email.

    La frase è il prodotto. Un'email che dice "sentiment −0,31" fa alzare le
    spalle; una che dice "il triplo delle notizie del solito" fa aprire il
    sito. E soprattutto è un'affermazione sulle NOTIZIE, che sappiamo
    dimostrare, non sul prezzo, che non sappiamo ancora.
    """
    pezzi = []
    zv, zt = a.get("z_volume"), a.get("z_tono")
    tipiche = a.get("notizie_tipiche")

    if zv is not None and abs(zv) >= 2 and tipiche:
        volte = a["news_count"] / tipiche if tipiche else 0
        if zv > 0:
            pezzi.append(f"{a['news_count']} notizie contro le {tipiche:g} solite"
                         + (f", quasi {volte:.0f} volte tanto" if volte >= 1.8 else ""))
        else:
            pezzi.append(f"solo {a['news_count']} notizie contro le {tipiche:g} solite")
    if zt is not None and abs(zt) >= 2:
        verso = "più positivo" if zt > 0 else "più negativo"
        pezzi.append(f"tono molto {verso} del suo normale")
    return " · ".join(pezzi) or "movimento fuori dalla norma"


def _build_email_html(alerts: list[dict]) -> str:
    rows_html = ""
    for a in alerts:
        emoji, label, color = _sentiment_label(a["avg_sentiment"])
        rows_html += f"""
        <tr>
          <td style="padding:12px 0;border-bottom:1px solid #f0f0f0;vertical-align:top">
            <div style="font-weight:600">{a['ticker']}</div>
            <div style="color:#666;font-size:13px;margin-top:3px">{_riga_motivo(a)}</div>
          </td>
          <td style="padding:12px 0;border-bottom:1px solid #f0f0f0;color:{color};
                     font-weight:500;vertical-align:top;text-align:right;white-space:nowrap">
            {emoji} {a['avg_sentiment']:+.2f}
          </td>
        </tr>"""

    return f"""
    <div style="font-family:sans-serif;max-width:520px;margin:0 auto;padding:32px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:28px">
        <div style="width:32px;height:32px;background:#1e5cff;border-radius:8px"></div>
        <span style="font-size:16px;font-weight:500">Cheruvo</span>
      </div>
      <h2 style="font-size:20px;margin-bottom:6px">Qualcosa è cambiato</h2>
      <p style="color:#666;margin-bottom:20px">
        Rispetto alla normalità delle ultime quattro settimane, su questi titoli
        della tua watchlist oggi è successo qualcosa fuori dal solito.
      </p>
      <table style="width:100%;border-collapse:collapse;font-size:14px">
        <tbody>{rows_html}</tbody>
      </table>
      <a href="{FRONTEND_URL}" style="display:inline-block;margin-top:24px;background:#1e5cff;color:white;
         padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:500">
        Apri Cheruvo →
      </a>
      <p style="color:#bbb;font-size:11px;margin-top:28px">
        Ricevi questa email perché hai dei titoli in watchlist su Cheruvo.<br>
        Un avviso parte solo quando il dato si stacca di quattro deviazioni
        dalla normalità del titolo stesso: capita meno di una volta a settimana
        su tutto l'elenco. Questo non è un segnale di acquisto o vendita, dice
        che se ne sta parlando in modo insolito.
      </p>
    </div>"""


def check_and_send_alerts():
    """Entry point principale — chiamato da updater.py."""
    logger.info("[Alerts] Controllo alert sentiment PRO...")

    user_watchlists = get_pro_users_watchlists()
    if not user_watchlists:
        logger.info("[Alerts] Nessun utente PRO con watchlist. Skip.")
        return

    # Raccogli tutti i ticker unici
    all_tickers = list({t for tickers in user_watchlists.values() for t in tickers})
    alerts_by_ticker = {a["ticker"]: a for a in get_sentiment_alerts(all_tickers)}

    if not alerts_by_ticker:
        logger.info("[Alerts] Nessun movimento significativo nelle ultime 24h.")
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
            logger.info("[Alerts] Inviato a %s (%d ticker)", email, len(user_alerts))
            sent += 1
        except Exception as e:
            logger.error("[Alerts] Errore per %s: %s", email, e)

    logger.info("[Alerts] Completato: %d email inviate.", sent)


if __name__ == "__main__":
    check_and_send_alerts()