"""
conftest.py — Fixtures condivise per tutti i test di Cheruvo.
"""
import sys
import os
import pytest
from unittest.mock import MagicMock, patch

# Assicura che il backend sia nel path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ── Variabili d'ambiente mock ──────────────────────────────────────────────
os.environ.setdefault("DATABASE_URL", "postgresql://fake:fake@localhost/fake")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_fake")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_fake")
os.environ.setdefault("STRIPE_PRICE_ID", "price_fake")
os.environ.setdefault("RESEND_API_KEY", "re_fake")
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake_key")
os.environ.setdefault("GROQ_API_KEY", "gsk_fake_key_for_tests")


# ── Mock del pool DB ───────────────────────────────────────────────────────
@pytest.fixture
def mock_pool():
    """Restituisce un pool psycopg2 completamente mockato."""
    pool = MagicMock()
    conn = MagicMock()
    cur = MagicMock()

    conn.cursor.return_value = cur
    cur.fetchone.return_value = None
    cur.fetchall.return_value = []
    pool.getconn.return_value = conn

    return pool, conn, cur


@pytest.fixture
def mock_db(mock_pool):
    """Patcha database.get_pool con il mock_pool."""
    pool, conn, cur = mock_pool
    with patch("database.get_pool", return_value=pool):
        yield pool, conn, cur


# ── Mock dell'autenticazione ───────────────────────────────────────────────
FAKE_USER = {"sub": "user-uuid-1234", "email": "test@example.com", "role": "authenticated"}
FAKE_PRO_USER = {"sub": "user-uuid-pro", "email": "pro@example.com", "role": "authenticated"}


@pytest.fixture
def mock_auth_user():
    """Patcha get_current_user per restituire un utente free."""
    with patch("auth.get_current_user", return_value=FAKE_USER):
        yield FAKE_USER


# ── FastAPI TestClient ─────────────────────────────────────────────────────
@pytest.fixture
def client(mock_db):
    """Client HTTP sincrono per testare i route FastAPI."""
    from fastapi.testclient import TestClient

    with patch("database.get_pool", return_value=mock_db[0]):
        # Importa app dopo aver patchato il DB per evitare connessioni reali
        from main import app
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c
