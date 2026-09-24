import logging
import os
import stripe
from fastapi import APIRouter, HTTPException, Request, Depends
from database import get_pool
from auth import get_current_user, invalidate_tier_cache

logger = logging.getLogger(__name__)

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")
# Il ripiego era "https://appcheruvo.app", un dominio che non e' di Cheruvo:
# se su Render mancava FRONTEND_URL, chi finiva di pagare veniva rimandato a
# un indirizzo che chiunque poteva registrare. Corretto il 24 settembre 2026.
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://app.cheruvo.com")

# Gli stati di Stripe tradotti nei nostri tre. "trialing" vale come pagato,
# "incomplete" no (il primo pagamento non e' andato a buon fine).
STATO_DA_STRIPE = {
    "active": "pro",
    "trialing": "pro",
    "past_due": "past_due",
    "unpaid": "past_due",
    "canceled": "free",
    "incomplete_expired": "free",
    "incomplete": "free",
    "paused": "free",
}

router = APIRouter()


def _conn():
    return get_pool().getconn()

def _rel(conn):
    get_pool().putconn(conn)


def init_subscriptions_table():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id                  SERIAL PRIMARY KEY,
                user_id             UUID NOT NULL,
                email               TEXT NOT NULL,
                stripe_customer_id  TEXT,
                stripe_sub_id       TEXT,
                status              TEXT DEFAULT 'free',
                created_at          TIMESTAMP DEFAULT NOW(),
                UNIQUE(user_id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                id         SERIAL PRIMARY KEY,
                user_id    UUID NOT NULL,
                ticker     TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(user_id, ticker)
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_watchlist_user
            ON watchlist (user_id)
        """)
        conn.commit()
        cur.close()
    finally:
        _rel(conn)


@router.post("/checkout")
async def create_checkout(user: dict = Depends(get_current_user)):
    """
    Apre il pagamento su Stripe per l'utente che lo chiede.

    Fino al 24 settembre 2026 non chiedeva il login e prendeva email e
    user_id dal CORPO della richiesta: chiunque poteva aprire sessioni a nome
    di un altro utente, o di un utente inventato, e riempire l'account Stripe
    di sessioni fasulle. Adesso l'identita' viene dal token verificato.
    """
    email = user.get("email")
    user_id = user.get("sub")
    if not email or not user_id:
        raise HTTPException(status_code=400, detail="Account senza email")
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            customer_email=email,
            line_items=[{"price": PRICE_ID, "quantity": 1}],
            success_url=f"{FRONTEND_URL}?pro=success",
            cancel_url=f"{FRONTEND_URL}?pro=cancel",
            metadata={"user_id": user_id},
        )
        return {"url": session.url}
    except Exception as e:
        # Il messaggio di Stripe resta nel log: all'utente non serve, e puo'
        # contenere dettagli di configurazione dell'account.
        logger.error("Checkout Stripe non riuscito per %s: %s", user_id, e)
        raise HTTPException(status_code=502, detail="Pagamento non disponibile in questo momento")


@router.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception:
        raise HTTPException(status_code=400, detail="Webhook invalido")

    conn = _conn()
    try:
        cur = conn.cursor()
        tipo = event["type"]
        if tipo == "checkout.session.completed":
            s = event["data"]["object"]
            user_id = s["metadata"]["user_id"]
            # `customer_email` e' valorizzato solo se l'email e' stata passata
            # alla creazione della sessione; altrimenti sta in
            # customer_details. La colonna e' NOT NULL: senza ripiego l'INSERT
            # falliva, il webhook rispondeva 500 e chi aveva pagato restava free.
            email = (s.get("customer_email")
                     or (s.get("customer_details") or {}).get("email")
                     or "")
            cur.execute("""
                INSERT INTO subscriptions (user_id, email, stripe_customer_id, stripe_sub_id, status)
                VALUES (%s, %s, %s, %s, 'pro')
                ON CONFLICT (user_id) DO UPDATE SET
                    stripe_customer_id = EXCLUDED.stripe_customer_id,
                    stripe_sub_id = EXCLUDED.stripe_sub_id,
                    status = 'pro'
            """, (user_id, email, s.get("customer"), s.get("subscription")))
            invalidate_tier_cache(user_id)  # upgrade immediato, senza aspettare TTL cache
        elif tipo == "customer.subscription.deleted":
            cur.execute(
                "UPDATE subscriptions SET status = 'free' WHERE stripe_sub_id = %s RETURNING user_id",
                (event["data"]["object"]["id"],)
            )
            row = cur.fetchone()
            if row:
                invalidate_tier_cache(row[0])  # downgrade immediato
        elif tipo == "invoice.payment_failed":
            # Il pagamento mensile è fallito — downgrade a past_due
            # Stripe riproverà automaticamente; se fallisce di nuovo invierà subscription.deleted
            sub_id = event["data"]["object"].get("subscription")
            if sub_id:
                cur.execute(
                    "UPDATE subscriptions SET status = 'past_due' WHERE stripe_sub_id = %s RETURNING user_id",
                    (sub_id,)
                )
                row = cur.fetchone()
                if row:
                    invalidate_tier_cache(row[0])
        elif tipo in ("invoice.paid", "invoice.payment_succeeded"):
            # IL RITORNO DA past_due NON C'ERA (24 settembre 2026).
            #
            # Una carta rifiutata una volta metteva l'utente in 'past_due';
            # quando Stripe ritentava e il pagamento passava, arrivava questo
            # evento e nessuno lo ascoltava. Risultato: un abbonato che paga
            # trattato come free per sempre. Si riporta a 'pro' solo chi era
            # in 'past_due', per non resuscitare un abbonamento cancellato.
            sub_id = event["data"]["object"].get("subscription")
            if sub_id:
                cur.execute(
                    "UPDATE subscriptions SET status = 'pro' "
                    "WHERE stripe_sub_id = %s AND status = 'past_due' RETURNING user_id",
                    (sub_id,)
                )
                row = cur.fetchone()
                if row:
                    invalidate_tier_cache(row[0])
        elif tipo == "customer.subscription.updated":
            # Lo stato vero dell'abbonamento, qualunque sia la strada da cui
            # ci e' arrivato (ritentativo riuscito, pausa, disdetta a fine
            # periodo diventata effettiva).
            oggetto = event["data"]["object"]
            nuovo = STATO_DA_STRIPE.get(oggetto.get("status"))
            if nuovo and oggetto.get("id"):
                cur.execute(
                    "UPDATE subscriptions SET status = %s WHERE stripe_sub_id = %s RETURNING user_id",
                    (nuovo, oggetto["id"])
                )
                row = cur.fetchone()
                if row:
                    invalidate_tier_cache(row[0])
        conn.commit()
        cur.close()
    finally:
        _rel(conn)
    return {"status": "ok"}


@router.get("/subscription/{user_id}")
def get_subscription(user_id: str, current_user: dict = Depends(get_current_user)):
    # Verifica che l'utente stia richiedendo info su se stesso
    if current_user["sub"] != user_id:
        raise HTTPException(status_code=403, detail="Non autorizzato")
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT status FROM subscriptions WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        cur.close()
    finally:
        _rel(conn)
    status = row[0] if row else "free"
    # past_due = pagamento fallito ma non ancora cancellato — trattalo come free
    if status == "past_due":
        status = "free"
    return {"status": status}