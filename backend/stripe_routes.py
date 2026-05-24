import os
import stripe
import psycopg2
from fastapi import APIRouter, HTTPException, Request

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")
FRONTEND_URL = "https://finsentinel-three.vercel.app"

router = APIRouter()


def get_connection():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def init_subscriptions_table():
    conn = get_connection()
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
    conn.commit()
    cur.close()
    conn.close()


@router.post("/api/checkout")
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


@router.post("/api/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception:
        raise HTTPException(status_code=400, detail="Webhook invalido")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session["metadata"]["user_id"]
        email = session["customer_email"]
        customer_id = session["customer"]
        sub_id = session["subscription"]

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO subscriptions (user_id, email, stripe_customer_id, stripe_sub_id, status)
            VALUES (%s, %s, %s, %s, 'pro')
            ON CONFLICT (user_id) DO UPDATE SET
                stripe_customer_id = EXCLUDED.stripe_customer_id,
                stripe_sub_id = EXCLUDED.stripe_sub_id,
                status = 'pro'
        """, (user_id, email, customer_id, sub_id))
        conn.commit()
        cur.close()
        conn.close()

    elif event["type"] == "customer.subscription.deleted":
        sub_id = event["data"]["object"]["id"]
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE subscriptions SET status = 'free' WHERE stripe_sub_id = %s", (sub_id,))
        conn.commit()
        cur.close()
        conn.close()

    return {"status": "ok"}


@router.get("/api/subscription/{user_id}")
def get_subscription(user_id: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT status FROM subscriptions WHERE user_id = %s", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return {"status": row[0] if row else "free"}