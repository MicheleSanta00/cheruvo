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


# ── 24 settembre 2026: il ritorno da past_due, e il checkout ──────────────

def _manda(app, evento, pool):
    with patch("stripe_routes.get_pool", return_value=pool), \
         patch("stripe.Webhook.construct_event", return_value=evento):
        with TestClient(app, raise_server_exceptions=False) as c:
            return c.post("/api/webhook", content=json.dumps(evento).encode(),
                          headers={"stripe-signature": "fake",
                                   "content-type": "application/json"})


def test_un_pagamento_riuscito_riporta_a_pro_chi_era_past_due(app):
    """
    Prima nessuno ascoltava invoice.paid: una carta rifiutata una volta e poi
    passata al ritentativo lasciava l'abbonato 'past_due', cioe' free, per
    sempre.
    """
    pool, conn, cur = _make_pool()
    resp = _manda(app, {"type": "invoice.paid",
                        "data": {"object": {"subscription": "sub_1"}}}, pool)
    assert resp.status_code == 200
    sql = " ".join(str(c) for c in cur.execute.call_args_list)
    assert "status = 'pro'" in sql and "past_due" in sql, \
        "si torna a pro solo da past_due, non da una disdetta"


def test_lo_stato_aggiornato_da_stripe_viene_tradotto(app):
    pool, conn, cur = _make_pool()
    resp = _manda(app, {"type": "customer.subscription.updated",
                        "data": {"object": {"id": "sub_2", "status": "active"}}}, pool)
    assert resp.status_code == 200
    aggiornamenti = [c[0][1] for c in cur.execute.call_args_list
                     if "UPDATE subscriptions" in str(c)]
    assert aggiornamenti == [("pro", "sub_2")]


def test_uno_stato_sconosciuto_non_tocca_niente(app):
    pool, conn, cur = _make_pool()
    _manda(app, {"type": "customer.subscription.updated",
                 "data": {"object": {"id": "sub_3", "status": "stato_nuovo"}}}, pool)
    # All'avvio l'app crea le sue tabelle sullo stesso cursore finto: si
    # guarda solo che nessuno abbia toccato gli abbonamenti.
    assert not any("UPDATE subscriptions" in str(c) for c in cur.execute.call_args_list)


def test_senza_customer_email_si_prende_quella_dei_dettagli(app):
    """La colonna email e' NOT NULL: con None l'INSERT falliva e chi pagava restava free."""
    pool, conn, cur = _make_pool()
    _manda(app, {"type": "checkout.session.completed",
                 "data": {"object": {"metadata": {"user_id": "u9"},
                                     "customer_email": None,
                                     "customer_details": {"email": "d@x.it"},
                                     "customer": "cus", "subscription": "sub"}}}, pool)
    inserimenti = [c[0][1] for c in cur.execute.call_args_list
                   if "INSERT INTO subscriptions" in str(c)]
    assert inserimenti and inserimenti[0][1] == "d@x.it"


def test_il_checkout_chiede_l_account(app):
    """
    Prima email e user_id arrivavano dal corpo, senza login: chiunque apriva
    sessioni di pagamento a nome di chiunque.
    """
    from auth import get_current_user
    from fastapi import HTTPException

    def _nessuno():
        raise HTTPException(status_code=401, detail="Non autenticato")

    app.dependency_overrides[get_current_user] = _nessuno
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post("/api/checkout",
                          json={"email": "vittima@x.it", "user_id": "altro"})
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_il_checkout_usa_l_identita_del_token_non_quella_del_corpo(app):
    from auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: {"sub": "io", "email": "io@x.it"}
    sessione = MagicMock(url="https://checkout.stripe.com/x")
    try:
        with patch("stripe.checkout.Session.create", return_value=sessione) as crea:
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.post("/api/checkout",
                              json={"email": "vittima@x.it", "user_id": "altro"})
        assert resp.status_code == 200
        kw = crea.call_args.kwargs
        assert kw["customer_email"] == "io@x.it"
        assert kw["metadata"] == {"user_id": "io"}
        assert "appcheruvo.app" not in kw["success_url"]
    finally:
        app.dependency_overrides.clear()
