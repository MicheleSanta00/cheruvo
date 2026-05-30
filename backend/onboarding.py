"""
onboarding.py — Sequenza email automatica per nuovi utenti.

Giorno 0: email di benvenuto + guida rapida (inviata subito dopo la registrazione)
Giorno 3: tips sulle funzionalità avanzate
Giorno 7: invito upgrade PRO con feature highlight

Chiamato da:
- /api/onboarding/welcome (POST) per giorno 0
- updater.py (cron GitHub Actions) per giorno 3 e 7
"""
import os
import logging
from datetime import datetime, timedelta, timezone
import psycopg2.extras
import resend

from database import get_pool

logger = logging.getLogger(__name__)

resend.api_key = os.environ.get("RESEND_API_KEY", "")
FROM_EMAIL   = os.environ.get("FROM_EMAIL", "noreply@cheruvo.com")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://app.cheruvo.com")


# ── DB helpers ────────────────────────────────────────────────────────────

def init_onboarding_table():
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS onboarding_emails (
                id            SERIAL PRIMARY KEY,
                user_id       UUID   NOT NULL,
                email         TEXT   NOT NULL,
                registered_at TIMESTAMPTZ DEFAULT NOW(),
                sent_day0     BOOLEAN DEFAULT FALSE,
                sent_day3     BOOLEAN DEFAULT FALSE,
                sent_day7     BOOLEAN DEFAULT FALSE,
                UNIQUE(user_id)
            )
        """)
        conn.commit()
        cur.close()
    finally:
        pool.putconn(conn)


def register_user(user_id: str, email: str):
    """Registra un nuovo utente nella tabella onboarding. Idempotente."""
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO onboarding_emails (user_id, email)
            VALUES (%s, %s)
            ON CONFLICT (user_id) DO NOTHING
        """, (user_id, email))
        conn.commit()
        cur.close()
    finally:
        pool.putconn(conn)


def mark_sent(user_id: str, day: int):
    col = f"sent_day{day}"
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(f"UPDATE onboarding_emails SET {col} = TRUE WHERE user_id = %s", (user_id,))
        conn.commit()
        cur.close()
    finally:
        pool.putconn(conn)


# ── Template email ────────────────────────────────────────────────────────

def _base_layout(title: str, body_html: str) -> str:
    return f"""
<div style="font-family:Arial,sans-serif;max-width:540px;margin:0 auto;padding:32px;color:#1a1a2e;background:#ffffff">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:32px">
    <div style="width:30px;height:30px;background:#1e5cff;border-radius:8px"></div>
    <span style="font-size:15px;font-weight:600;color:#1a1a2e">Cheruvo</span>
  </div>
  <h2 style="font-size:22px;font-weight:600;margin-bottom:8px;color:#1a1a2e">{title}</h2>
  {body_html}
  <div style="margin-top:40px;padding-top:20px;border-top:1px solid #eee;font-size:11px;color:#aaa">
    Hai ricevuto questa email perché ti sei registrato su Cheruvo.<br>
    <a href="{FRONTEND_URL}" style="color:#1e5cff;text-decoration:none">app.cheruvo.com</a>
  </div>
</div>"""


def _email_day0(email: str) -> tuple[str, str]:
    subject = "Benvenuto su Cheruvo 👋"
    body = _base_layout("Benvenuto su Cheruvo!", f"""
<p style="font-size:14px;color:#555;line-height:1.7;margin-bottom:20px">
  Ciao! Il tuo account è attivo. In meno di 30 secondi puoi vedere il sentiment
  di qualsiasi azione quotata in borsa.
</p>
<div style="background:#f8f9ff;border-radius:10px;padding:20px;margin-bottom:24px">
  <div style="font-size:13px;font-weight:600;color:#1a1a2e;margin-bottom:12px">Come iniziare:</div>
  <div style="font-size:13px;color:#555;line-height:2">
    <b>1.</b> Vai su <a href="{FRONTEND_URL}" style="color:#1e5cff">{FRONTEND_URL}</a><br>
    <b>2.</b> Inserisci un ticker nella sidebar (es. <b>NVDA</b>, <b>AAPL</b>, <b>ENI.MI</b>)<br>
    <b>3.</b> Clicca → per vedere il sentiment delle ultime notizie<br>
    <b>4.</b> Il grafico mostra prezzi + sentiment sovrapposti nel tempo
  </div>
</div>
<a href="{FRONTEND_URL}" style="display:inline-block;background:#1e5cff;color:white;
   padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px">
  Apri Cheruvo →
</a>
<p style="font-size:12px;color:#aaa;margin-top:24px">
  Piano gratuito: watchlist fino a 3 ticker, ultimi 30 giorni di news.
</p>""")
    return subject, body


def _email_day3(email: str) -> tuple[str, str]:
    subject = "Hai già provato queste funzioni? — Cheruvo"
    body = _base_layout("3 funzioni che forse non hai ancora visto", f"""
<p style="font-size:14px;color:#555;line-height:1.7;margin-bottom:24px">
  Sono passati 3 giorni dalla tua registrazione. Ecco le funzioni che
  gli utenti scoprono solo dopo un po':
</p>
<div style="margin-bottom:16px;padding:16px;border:1px solid #e8eeff;border-radius:10px">
  <div style="font-size:13px;font-weight:600;color:#1e5cff;margin-bottom:4px">📊 Grafico Sentiment + Prezzo</div>
  <div style="font-size:13px;color:#555;line-height:1.6">
    Il grafico principale mostra il prezzo OHLCV con i pallini
    del sentiment sovrapposti. I pallini verdi/rossi mostrano i giorni
    con notizie particolarmente positive o negative.
  </div>
</div>
<div style="margin-bottom:16px;padding:16px;border:1px solid #e8eeff;border-radius:10px">
  <div style="font-size:13px;font-weight:600;color:#1e5cff;margin-bottom:4px">🔄 Confronto Multi-Ticker</div>
  <div style="font-size:13px;color:#555;line-height:1.6">
    Puoi confrontare il sentiment di più azioni nello stesso grafico.
    Utile per vedere se un settore intero è in trend positivo o se
    è solo un'azienda specifica.
  </div>
</div>
<div style="margin-bottom:24px;padding:16px;border:1px solid #e8eeff;border-radius:10px">
  <div style="font-size:13px;font-weight:600;color:#1e5cff;margin-bottom:4px">💬 Assistente AI</div>
  <div style="font-size:13px;color:#555;line-height:1.6">
    Il pulsante blu in basso a destra apre una chat AI che conosce
    il ticker che stai analizzando. Puoi chiedergli di spiegare
    il sentiment score o cosa significano le notizie.
  </div>
</div>
<a href="{FRONTEND_URL}" style="display:inline-block;background:#1e5cff;color:white;
   padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px">
  Prova adesso →
</a>""")
    return subject, body


def _email_day7(email: str) -> tuple[str, str]:
    subject = "Sblocca tutto con Cheruvo PRO — €9/mese"
    body = _base_layout("Passa a PRO e sblocca tutte le funzioni", f"""
<p style="font-size:14px;color:#555;line-height:1.7;margin-bottom:24px">
  Sei su Cheruvo da una settimana. Se ti è stato utile, considera
  il piano PRO — costa meno di un caffè al giorno.
</p>
<div style="background:#f0f4ff;border-radius:10px;padding:20px;margin-bottom:24px">
  <div style="font-size:13px;font-weight:700;color:#1a1a2e;margin-bottom:14px">
    Con PRO sblocchi:
  </div>
  <div style="font-size:13px;color:#333;line-height:2.2">
    ✅ <b>Watchlist illimitata</b> — segui quanti ticker vuoi<br>
    ✅ <b>90 giorni di notizie</b> (vs 30 del piano free)<br>
    ✅ <b>AI Summary</b> — analisi bullish/bearish generata da Llama 3<br>
    ✅ <b>Correlazione sentiment/prezzo</b> — scatter plot avanzato<br>
    ✅ <b>Alert email</b> — notifiche automatiche sui tuoi ticker<br>
    ✅ <b>Export CSV</b> — scarica tutte le news in Excel<br>
    ✅ <b>Analytics avanzate</b> — distribuzione fonti e sentiment
  </div>
</div>
<a href="{FRONTEND_URL}" style="display:inline-block;background:#1e5cff;color:white;
   padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:600;font-size:15px">
  ⚡ Passa a PRO — €9/mese →
</a>
<p style="font-size:12px;color:#aaa;margin-top:20px">
  Puoi cancellare in qualsiasi momento dal tuo profilo. Nessun vincolo.
</p>""")
    return subject, body


# ── Invio email ───────────────────────────────────────────────────────────

def _send(to: str, subject: str, html: str) -> bool:
    try:
        resend.Emails.send({"from": FROM_EMAIL, "to": to, "subject": subject, "html": html})
        logger.info("[Onboarding] Inviata '%s' a %s", subject, to)
        return True
    except Exception as e:
        logger.error("[Onboarding] Errore invio a %s: %s", to, e)
        return False


def send_welcome(user_id: str, email: str):
    """Invia l'email di giorno 0 e registra l'utente nel DB."""
    register_user(user_id, email)
    subject, html = _email_day0(email)
    if _send(email, subject, html):
        mark_sent(user_id, 0)


def check_and_send_onboarding_emails():
    """
    Chiamato dal cron GitHub Actions.
    Invia le email di giorno 3 e 7 agli utenti che non le hanno ancora ricevute.
    """
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        now = datetime.now(timezone.utc)

        # Giorno 3: registrati >= 3 giorni fa, non ancora ricevuta
        cur.execute("""
            SELECT user_id, email FROM onboarding_emails
            WHERE sent_day3 = FALSE
              AND registered_at <= NOW() - INTERVAL '3 days'
        """)
        day3_users = cur.fetchall()

        # Giorno 7: registrati >= 7 giorni fa, non ancora ricevuta
        cur.execute("""
            SELECT user_id, email FROM onboarding_emails
            WHERE sent_day7 = FALSE
              AND registered_at <= NOW() - INTERVAL '7 days'
        """)
        day7_users = cur.fetchall()
        cur.close()
    finally:
        pool.putconn(conn)

    logger.info("[Onboarding] Giorno 3: %d utenti, Giorno 7: %d utenti",
                len(day3_users), len(day7_users))

    for row in day3_users:
        subject, html = _email_day3(row["email"])
        if _send(row["email"], subject, html):
            mark_sent(row["user_id"], 3)

    for row in day7_users:
        subject, html = _email_day7(row["email"])
        if _send(row["email"], subject, html):
            mark_sent(row["user_id"], 7)


if __name__ == "__main__":
    check_and_send_onboarding_emails()
