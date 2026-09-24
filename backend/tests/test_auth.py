"""
test_auth.py — Verifica che gli endpoint protetti richiedano autenticazione.

Usa app.dependency_overrides invece di patch() perché FastAPI ispeziona
la firma delle dipendenze al momento dell'import del router — patchare
la funzione PRIMA dell'import corrompe il MagicMock e rompe inspect.signature().
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Variabili env necessarie prima di importare i moduli
os.environ.setdefault("DATABASE_URL", "postgresql://fake:fake@localhost/fake")
os.environ.setdefault("GROQ_API_KEY", "gsk_fake_key_for_tests")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_fake")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_fake")
os.environ.setdefault("STRIPE_PRICE_ID", "price_fake")

import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient


FAKE_USER = {"sub": "user-uuid-1234", "email": "test@example.com"}


# ── Mock pool condiviso ────────────────────────────────────────────────────

def _make_pool(fetchone_value=None, fetchall_value=None):
    pool = MagicMock()
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchone.return_value = fetchone_value
    cur.fetchall.return_value = fetchall_value or []
    pool.getconn.return_value = conn
    return pool, conn, cur


# ── Importa app una volta sola ─────────────────────────────────────────────
# L'app viene importata a livello di modulo con il pool già mockato a livello
# di env (DATABASE_URL falso). Le singole query vengono bloccate via
# dependency_overrides o patch locale nei test.

@pytest.fixture(scope="module")
def app():
    pool, conn, cur = _make_pool()
    with patch("database.get_pool", return_value=pool), \
         patch("database._get_connection", return_value=conn):
        from main import app as _app
        yield _app
        # Pulisci gli override a fine modulo
        _app.dependency_overrides.clear()


# ── Dipendenze override ────────────────────────────────────────────────────

def _raise_401():
    raise HTTPException(status_code=401, detail="Non autenticato")

def _return_fake_user():
    return FAKE_USER

def _return_free_tier():
    return "free"


# ── Test: endpoint protetti senza token → 401 ─────────────────────────────

class TestEndpointProtetti:

    @pytest.fixture(autouse=True)
    def setup(self, app):
        """Overrida get_current_user con una funzione che solleva 401."""
        from auth import get_current_user
        app.dependency_overrides[get_current_user] = _raise_401
        yield
        app.dependency_overrides.clear()

    # news, prices e sentiment NON stanno piu' qui: dal 16 agosto 2026 si
    # leggono anche senza account, con meno storico. Le loro prove stanno
    # in TestLetturaSenzaAccount piu' sotto, insieme al motivo.

    def test_tickers_senza_token_401(self, app):
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/api/tickers")
        assert resp.status_code == 401

    def test_fetch_senza_token_401(self, app):
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post("/api/fetch/AAPL")
        assert resp.status_code == 401


# ── Test: /api/subscription — controllo ownership ─────────────────────────

class TestSubscriptionOwnership:

    @pytest.fixture(autouse=True)
    def setup(self, app):
        from auth import get_current_user
        app.dependency_overrides[get_current_user] = _return_fake_user
        yield
        app.dependency_overrides.clear()

    def test_utente_accede_a_sua_subscription(self, app):
        """L'utente può vedere la propria subscription."""
        pool, conn, cur = _make_pool(fetchone_value=("pro",))
        with patch("stripe_routes.get_pool", return_value=pool):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.get(
                    f"/api/subscription/{FAKE_USER['sub']}",
                    headers={"Authorization": "Bearer fake_token"},
                )
        assert resp.status_code == 200
        assert resp.json()["status"] in ("pro", "free")

    def test_utente_non_puo_vedere_subscription_altrui(self, app):
        """Un utente non può accedere alla subscription di un altro utente."""
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get(
                "/api/subscription/altro-utente-uuid",
                headers={"Authorization": "Bearer fake_token"},
            )
        assert resp.status_code == 403


# ── Test: cosa si legge senza account, e cosa no ──────────────────────────
#
# Il 16 agosto 2026, su r/ItaliaStartups: "Rimuovi il Login wall, voglio vedere
# prima di iscrivermi". `App.jsx` rimandava alla schermata di accesso CHIUNQUE,
# quindi del prodotto non si vedeva niente prima di registrarsi, e chi non lo
# prova non si registra.
#
# La riga di confine non e' "letto contro scritto", e' "costa contro non
# costa". /api/fetch fa partire una raccolta e /api/chat passa da Groq: sono
# le due che un visitatore potrebbe usare per bruciare il piano gratuito, e
# restano chiuse. Leggere notizie che sono titoli GDELT con licenza aperta,
# gia' visibili in home senza account, non toglie niente a nessuno.

class TestLetturaSenzaAccount:

    @pytest.fixture(autouse=True)
    def setup(self, app):
        """
        Nessun token: get_current_user_optional restituisce None.

        E niente rete: fino al 24 settembre 2026 questi test chiamavano Yahoo
        per davvero (tre tentativi con pausa, poi Alpha Vantage), quindi
        dipendevano dalla connessione e duravano secondi. Qui si prova chi
        puo' leggere cosa, non Yahoo.
        """
        import pandas as pd
        from auth import get_current_user_optional
        app.dependency_overrides[get_current_user_optional] = lambda: None
        finto = pd.DataFrame({"Close": [1.0, 2.0]},
                             index=pd.to_datetime(["2026-09-01", "2026-09-02"]))
        with patch("main.get_prices", return_value=finto), \
             patch("main.stato_mercato", return_value={"aperto": False}):
            yield
        app.dependency_overrides.clear()

    def test_le_notizie_si_leggono_senza_account(self, app):
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/api/news/AAPL")
        assert resp.status_code != 401, "il muro e' tornato su"

    def test_i_prezzi_si_leggono_senza_account(self, app):
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/api/prices/AAPL")
        assert resp.status_code == 200

    def test_il_sentiment_si_legge_senza_account(self, app):
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/api/sentiment/AAPL")
        assert resp.status_code != 401

    def test_col_paywall_acceso_un_periodo_lungo_resta_chiuso(self, app):
        """
        Aprire la lettura non vuol dire regalare il piano PRO: il giorno in
        cui il paywall si riaccende, i periodi lunghi tornano dove stavano,
        per il visitatore esattamente come per l'iscritto senza abbonamento.
        """
        with patch("auth.PAYWALL_ATTIVO", True):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.get("/api/prices/AAPL?period=5y")
        assert resp.status_code == 403

    def test_col_paywall_spento_il_visitatore_vede_quello_che_vede_un_iscritto(self, app):
        """
        Il difetto del 24 settembre 2026: con il paywall spento l'iscritto
        vedeva 6M e 1A, il visitatore riceveva 403, e l'interfaccia gli
        mostrava comunque i bottoni. Il risultato era un grafico vuoto.
        """
        with patch("auth.PAYWALL_ATTIVO", False):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.get("/api/prices/AAPL?period=1y")
        assert resp.status_code == 200

    def test_un_periodo_inventato_viene_respinto(self, app):
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/api/prices/AAPL?period=100y")
        assert resp.status_code == 400

    def test_un_simbolo_impossibile_viene_respinto(self, app):
        with TestClient(app, raise_server_exceptions=False) as c:
            assert c.get("/api/news/AAPL%3Bdrop").status_code == 400
            assert c.get("/api/prices/" + "A" * 40).status_code == 400


class TestQuelloCheSpendeRestaChiuso:
    """
    /api/fetch fa partire una raccolta, /api/chat passa da Groq. Sono le due
    porte da cui un visitatore anonimo puo' consumare il piano gratuito, e
    devono restare chiuse anche adesso che il resto e' aperto.
    """

    @pytest.fixture(autouse=True)
    def setup(self, app):
        from auth import get_current_user
        app.dependency_overrides[get_current_user] = _raise_401
        yield
        app.dependency_overrides.clear()

    def test_la_raccolta_resta_chiusa(self, app):
        with TestClient(app, raise_server_exceptions=False) as c:
            assert c.post("/api/fetch/AAPL").status_code == 401

    def test_la_chat_resta_chiusa(self, app):
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post("/api/chat", json={"messages": []})
        assert resp.status_code == 401

    def test_la_watchlist_resta_chiusa(self, app):
        with TestClient(app, raise_server_exceptions=False) as c:
            assert c.get("/api/tickers").status_code == 401


# ── Test: endpoint pubblici non richiedono auth ────────────────────────────

class TestEndpointPubblici:

    @pytest.fixture(autouse=True)
    def setup(self, app):
        app.dependency_overrides.clear()
        yield
        app.dependency_overrides.clear()

    def test_health_non_richiede_auth(self, app):
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/health")
        assert resp.status_code == 200

    def test_validate_ticker_non_richiede_auth(self, app):
        """validate accetta anche utenti non autenticati (get_current_user_optional)."""
        with patch("main.validate_ticker", return_value={
            "valid": True, "ticker": "AAPL", "nome": "Apple Inc.",
            "settore": "N/A", "prezzo": 150.0, "variazione": 1.5
        }):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.get("/api/validate/AAPL")
        assert resp.status_code == 200
        assert resp.json()["valid"] is True
