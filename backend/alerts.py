"""
alerts.py — Sistema di alert sentiment per Cheruvo.
"""
import os
import sys
import html
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


def watchlist_per_utente() -> dict[str, list[str]]:
    """
    {email: [ticker, ...]} per CHIUNQUE abbia un account e una watchlist.

    SI CHIAMAVA get_pro_users_watchlists, E NON ARRIVAVA A NESSUNO.

    La versione precedente faceva un JOIN stretto su `subscriptions` con
    `status = 'pro'`. Il paywall è spento dal 7 agosto 2026 e gli abbonati
    sono zero, quindi quella tabella non ha righe 'pro': l'interrogazione
    tornava vuota, `check_and_send_alerts` scriveva "Nessun utente PRO con
    watchlist. Skip." e usciva. Quattro volte al giorno, da settimane.

    Cioè: il rilevatore di anomalie calcolava tutto correttamente e l'email
    non partiva mai, per nessuno, senza che niente si lamentasse.

    È lo stesso difetto del muro di accesso trovato il 18 agosto: un residuo
    del piano a pagamento che blocca il prodotto gratuito. Quando un pezzo di
    codice chiede "sei PRO?" in un prodotto dove PRO non esiste, la risposta è
    sempre no.

    `digest.py` lo faceva già giusto: si passa da `auth.users`, che è dove
    stanno davvero le email, e l'abbonamento semmai si legge a parte.
    """
    return {email: d["tickers"] for email, d in destinatari().items()}


def destinatari() -> dict[str, dict]:
    """
    {email: {"user_id": ..., "tickers": [...]}}, saltando chi ha chiesto di
    non ricevere email facoltative (24 settembre 2026: prima non c'era modo
    di smettere di ricevere gli avvisi, se non togliendo la watchlist).
    """
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT u.email, w.ticker, u.id
            FROM watchlist w
            JOIN auth.users u ON u.id = w.user_id
            LEFT JOIN digest_prefs dp ON dp.user_id = w.user_id
            WHERE u.email IS NOT NULL
              AND COALESCE(dp.enabled, TRUE)
            ORDER BY u.email, w.ticker
        """)
        rows = cur.fetchall()
        cur.close()
    finally:
        _rel(conn)

    result: dict[str, dict] = {}
    for riga in rows:
        email, ticker = riga[0], riga[1]
        uid = str(riga[2]) if len(riga) > 2 and riga[2] is not None else None
        voce = result.setdefault(email, {"user_id": uid, "tickers": []})
        voce["tickers"].append(ticker)
    return result


# ── Un avviso per titolo al giorno ────────────────────────────────────────
#
# IL DIFETTO, 24 settembre 2026. Il cron gira quattro volte al giorno e
# `anomalie.calcola()` guarda la giornata intera: un'anomalia delle 6 del
# mattino c'era ancora a mezzogiorno, alle 18 e a mezzanotte. Nessuno si
# ricordava di averla gia' mandata, quindi la stessa email partiva fino a
# quattro volte. Il piede dell'email promette "capita meno di una volta a
# settimana": con i doppioni era falso, ed e' il modo piu' rapido di finire
# nello spam, per quell'utente e per il dominio intero.
def init_alert_log() -> None:
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS alert_log (
                email   TEXT NOT NULL,
                ticker  TEXT NOT NULL,
                giorno  DATE NOT NULL,
                sent_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (email, ticker, giorno)
            )
        """)
        conn.commit()
        cur.close()
    finally:
        _rel(conn)


def gia_avvisati(email: str, tickers: list[str]) -> set:
    """I titoli per cui questa persona ha gia' ricevuto l'avviso oggi."""
    if not tickers:
        return set()
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT ticker FROM alert_log
            WHERE email = %s AND giorno = CURRENT_DATE AND ticker = ANY(%s)
        """, (email, list(tickers)))
        fatti = {r[0] for r in cur.fetchall()}
        cur.close()
    finally:
        _rel(conn)
    return fatti


def segna_avvisati(email: str, tickers: list[str]) -> None:
    if not tickers:
        return
    conn = _conn()
    try:
        cur = conn.cursor()
        for tk in tickers:
            cur.execute("""
                INSERT INTO alert_log (email, ticker, giorno)
                VALUES (%s, %s, CURRENT_DATE)
                ON CONFLICT DO NOTHING
            """, (email, tk))
        conn.commit()
        cur.close()
    finally:
        _rel(conn)


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
    """
    Ritorna (emoji, label, colore) in base al sentiment.

    Mancava la fascia neutra (24 settembre 2026): tutto quello che stava fra
    -0,15 e +0,15, zero compreso, finiva nell'`else` e veniva scritto
    "negativo" in rosso. Da quando gli avvisi nascono dal VOLUME di notizie
    il tono e' spesso vicino a zero, quindi era il caso piu' frequente.
    """
    if score is None:
        return "•", "n.d.", "#6b7280"
    if score >= 0.3:
        return "🟢", "molto positivo", "#16a34a"
    elif score >= 0.15:
        return "📈", "positivo", "#22c55e"
    elif score <= -0.3:
        return "🔴", "molto negativo", "#dc2626"
    elif score <= -0.15:
        return "📉", "negativo", "#ef4444"
    return "•", "neutro", "#6b7280"


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


def _build_email_html(alerts: list[dict], disiscrizione: str = "") -> str:
    rows_html = ""
    for a in alerts:
        emoji, label, color = _sentiment_label(a["avg_sentiment"])
        rows_html += f"""
        <tr>
          <td style="padding:12px 0;border-bottom:1px solid #f0f0f0;vertical-align:top">
            <div style="font-weight:600">{html.escape(str(a['ticker']))}</div>
            <div style="color:#666;font-size:13px;margin-top:3px">{html.escape(_riga_motivo(a))}</div>
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
        {f'<br><a href="{disiscrizione}" style="color:#999">Non voglio più ricevere questi avvisi</a>' if disiscrizione else ''}
      </p>
    </div>"""


def check_and_send_alerts():
    """Entry point principale — chiamato da updater.py."""
    logger.info("[Alerts] Controllo avvisi sulle watchlist...")

    try:
        init_alert_log()
        # La scelta di non ricevere email sta in digest_prefs, e nel cron il
        # digest gira dopo: la tabella va garantita prima di leggerla.
        from digest import init_digest_tables
        init_digest_tables()
    except Exception as e:
        logger.warning("[Alerts] tabelle di servizio non verificabili: %s", e)

    persone = destinatari()
    if not persone:
        logger.info("[Alerts] Nessuno ha una watchlist. Skip.")
        return
    logger.info("[Alerts] %d utenti con watchlist", len(persone))

    # Raccogli tutti i ticker unici
    all_tickers = list({t for d in persone.values() for t in d["tickers"]})
    alerts_by_ticker = {a["ticker"]: a for a in get_sentiment_alerts(all_tickers)}

    if not alerts_by_ticker:
        logger.info("[Alerts] Nessun movimento significativo nelle ultime 24h.")
        return

    sent = 0
    for email, dati in persone.items():
        user_alerts = [alerts_by_ticker[t] for t in dati["tickers"] if t in alerts_by_ticker]
        if not user_alerts:
            continue
        try:
            fatti = gia_avvisati(email, [a["ticker"] for a in user_alerts])
        except Exception as e:
            # Senza registro non si sa cosa e' gia' partito: meglio un giro
            # senza avvisi che quattro copie della stessa email.
            logger.error("[Alerts] registro invii illeggibile per %s: %s", email, e)
            continue
        user_alerts = [a for a in user_alerts if a["ticker"] not in fatti]
        if not user_alerts:
            continue

        subject = f"Cheruvo Alert — {', '.join(a['ticker'] for a in user_alerts[:3])}"
        if len(user_alerts) > 3:
            subject += f" +{len(user_alerts)-3} altri"

        disiscrizione = ""
        if dati.get("user_id"):
            try:
                from digest import BACKEND_PUBLIC_URL, unsubscribe_token
                disiscrizione = (f"{BACKEND_PUBLIC_URL}/api/digest/unsubscribe"
                                 f"?u={dati['user_id']}&t={unsubscribe_token(dati['user_id'])}")
            except Exception:
                disiscrizione = ""

        try:
            resend.Emails.send({
                "from": FROM_EMAIL,
                "to": email,
                "subject": subject,
                "html": _build_email_html(user_alerts, disiscrizione),
            })
            segna_avvisati(email, [a["ticker"] for a in user_alerts])
            logger.info("[Alerts] Inviato a %s (%d ticker)", email, len(user_alerts))
            sent += 1
        except Exception as e:
            logger.error("[Alerts] Errore per %s: %s", email, e)

    logger.info("[Alerts] Completato: %d email inviate.", sent)


if __name__ == "__main__":
    check_and_send_alerts()