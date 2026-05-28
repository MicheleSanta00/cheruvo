import os
import stripe
from fastapi import APIRouter, HTTPException, Request
from database import get_pool

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://appcheruvo.app")

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
async def create_checkout(request: Request):
    body = await request.json()
    email = body.get("email")
    user_id = body.get("user_id")
    if not email or not user_id:
        raise HTTPException(status_code=400, detail="Email e user_id richiesti")
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
        raise HTTPException(status_code=500, detail=str(e))


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
        if event["type"] == "checkout.session.completed":
            s = event["data"]["object"]
            cur.execute("""
                INSERT INTO subscriptions (user_id, email, stripe_customer_id, stripe_sub_id, status)
                VALUES (%s, %s, %s, %s, 'pro')
                ON CONFLICT (user_id) DO UPDATE SET
                    stripe_customer_id = EXCLUDED.stripe_customer_id,
                    stripe_sub_id = EXCLUDED.stripe_sub_id,
                    status = 'pro'
            """, (s["metadata"]["user_id"], s["customer_email"], s["customer"], s["subscription"]))
        elif event["type"] == "customer.subscription.deleted":
            cur.execute(
                "UPDATE subscriptions SET status = 'free' WHERE stripe_sub_id = %s",
                (event["data"]["object"]["id"],)
            )
        elif event["type"] == "invoice.payment_failed":
            # Il pagamento mensile è fallito — downgrade a past_due
            # Stripe riproverà automaticamente; se fallisce di nuovo invierà subscription.deleted
            sub_id = event["data"]["object"].get("subscription")
            if sub_id:
                cur.execute(
                    "UPDATE subscriptions SET status = 'past_due' WHERE stripe_sub_id = %s",
                    (sub_id,)
                )
        conn.commit()
        cur.close()
    finally:
        _rel(conn)
    return {"status": "ok"}


@router.get("/subscription/{user_id}")
def get_subscription(user_id: str):
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