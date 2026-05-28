"""
test_stripe_webhook.py — Test per i webhook Stripe.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Env vars necessarie PRIMA di importare i moduli
os.environ.setdefault("DATABASE_URL", "postgresql://fake:fake@localhost/fake")
os.environ.setdefault("GROQ_API_KEY", "gsk_fake_key_for_tests")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_fake")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_fake")
os.environ.setdefault("STRIPE_PRICE_ID", "price_fake")

import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


def _make_pool():
    pool = MagicMock()
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchone.return_value = None
    cur.fetchall.return_value = []
    pool.getconn.return_value = conn
    return pool, conn, cur


# ── Importa app una volta sola a livello di modulo ─────────────────────────

@pytest.fixture(scope="module")
def app():
    pool, conn, cur = _make_pool()
    with patch("database.get_pool", return_value=pool), \
         patch("database._get_connection", return_value=conn):
        from main import app as _app
        yield _app


# ── Test: firma webhook invalida ───────────────────────────────────────────

def test_webhook_firma_invalida(app):
    """Una richiesta senza firma Stripe valida deve restituire 400."""
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/api/webhook",
            content=b'{"type":"test"}',
            headers={"stripe-signature": "firma_falsa",
                     "content-type": "application/json"},
        )
    assert resp.status_code == 400


# ── Test: checkout.session.completed → status = pro ───────────────────────

def test_webhook_checkout_completed_imposta_pro(app):
    """checkout.session.completed deve inserire/aggiornare la subscription a 'pro'."""
    pool, conn, cur = _make_pool()
    fake_event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "metadata": {"user_id": "uuid-123"},
                "customer_email": "user@example.com",
                "customer": "cus_fake",
                "subscription": "sub_fake",
            }
        },
    }

    with patch("stripe_routes.get_pool", return_value=pool), \
         patch("stripe.Webhook.construct_event", return_value=fake_event):
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post(
                "/api/webhook",
                content=json.dumps(fake_event).encode(),
                headers={"stripe-signature": "fake",
                         "content-type": "application/json"},
            )

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

    # Verifica che execute() sia stato chiamato con INSERT INTO subscriptions
    calls = cur.execute.call_args_list
    assert any("subscriptions" in str(call) for call in calls), \
        "Mi aspettavo una query INSERT/UPDATE su subscriptions"


# ── Test: customer.subscription.deleted → status = free ──────────────────

def test_webhook_subscription_deleted_imposta_free(app):
    """customer.subscription.deleted deve aggiornare lo status a 'free'."""
    pool, conn, cur = _make_pool()
    fake_event = {
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": "sub_fake_123"}},
    }

    with patch("stripe_routes.get_pool", return_value=pool), \
         patch("stripe.Webhook.construct_event", return_value=fake_event):
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post(
                "/api/webhook",
                content=json.dumps(fake_event).encode(),
                headers={"stripe-signature": "fake",
                         "content-type": "application/json"},
            )

    assert resp.status_code == 200

    calls = cur.execute.call_args_list
    assert any("free" in str(call) for call in calls), \
        "Mi aspettavo un UPDATE con status='free'"


# ── Test: invoice.payment_failed → status = past_due ─────────────────────

def test_webhook_payment_failed_imposta_past_due(app):
    """invoice.payment_failed deve aggiornare lo status a 'past_due'."""
    pool, conn, cur = _make_pool()
    fake_event = {
        "type": "invoice.payment_failed",
        "data": {"object": {"subscription": "sub_fake_456"}},
    }

    with patch("stripe_routes.get_pool", return_value=pool), \
         patch("stripe.Webhook.construct_event", return_value=fake_event):
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post(
                "/api/webhook",
                content=json.dumps(fake_event).encode(),
                headers={"stripe-signature": "fake",
                         "content-type": "application/json"},
            )

    assert resp.status_code == 200

    calls = cur.execute.call_args_list
    assert any("past_due" in str(call) for call in calls), \
        "Mi aspettavo un UPDATE con status='past_due'"
