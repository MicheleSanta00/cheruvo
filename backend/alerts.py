import os
import resend
import psycopg2

resend.api_key = os.environ.get("RESEND_API_KEY", "")


def get_connection():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def check_and_send_alerts():
    """Controlla il sentiment e manda alert se sotto soglia."""
    conn = get_connection()
    cur = conn.cursor()

    # Prendi sentiment medio degli ultimi 3 giorni per ogni ticker
    cur.execute("""
        SELECT ticker, AVG(sentiment) as avg_sent
        FROM news
        WHERE published_date >= NOW() - INTERVAL '3 days'
        GROUP BY ticker
        HAVING AVG(sentiment) < -0.2
    """)
    alerts = cur.fetchall()

    if not alerts:
        print("Nessun alert da mandare.")
        cur.close()
        conn.close()
        return

    # Prendi tutti gli utenti registrati
    cur.execute("SELECT email FROM auth.users")
    users = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()

    if not users:
        print("Nessun utente registrato.")
        return

    for ticker, avg_sent in alerts:
        sentiment_str = f"{avg_sent:.2f}"
        print(f"Alert: {ticker} sentiment {sentiment_str}")

        for email in users:
            try:
                resend.Emails.send({
                    "from": "onboarding@resend.dev",
                    "to": email,
                    "subject": f"⚠️ Cheruvo Alert — {ticker} sentiment negativo",
                    "html": f"""
                    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto; padding: 32px;">
                        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 24px;">
                            <div style="width: 32px; height: 32px; background: #1e5cff; border-radius: 8px;"></div>
                            <span style="font-size: 16px; font-weight: 500;">Cheruvo</span>
                        </div>
                        <h2 style="font-size: 20px; margin-bottom: 8px;">Sentiment negativo su {ticker}</h2>
                        <p style="color: #666; margin-bottom: 24px;">
                            Il sentiment medio degli ultimi 3 giorni su <strong>{ticker}</strong> 
                            è sceso a <strong style="color: #ef4444;">{sentiment_str}</strong>.
                        </p>
                        <p style="color: #666; margin-bottom: 24px;">
                            Questo potrebbe indicare un aumento di notizie negative. 
                            Apri l'app per analizzare la situazione.
                        </p>
                        <a href="https://finsentinel-three.vercel.app" 
                           style="background: #1e5cff; color: white; padding: 12px 24px; 
                                  border-radius: 8px; text-decoration: none; font-weight: 500;">
                            Apri Cheruvo
                        </a>
                        <p style="color: #999; font-size: 12px; margin-top: 32px;">
                            Stai ricevendo questa email perché sei registrato su Cheruvo.
                        </p>
                    </div>
                    """,
                })
                print(f"  ✓ Alert mandato a {email}")
            except Exception as e:
                print(f"  ✗ Errore invio a {email}: {e}")