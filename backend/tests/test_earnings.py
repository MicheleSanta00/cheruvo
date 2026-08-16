"""
test_earnings.py — Calendario earnings: refresh selettivo, endpoint con gating Pro.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("DATABASE_URL", "postgresql://fake:fake@localhost/fake")

from datetime import date
import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

UID = "11111111-1111-1111-1111-111111111111"


def _pool(fetchone=None, fetchall=None):
    pool, conn, cur = MagicMock(), MagicMock(), MagicMock()
    conn.cursor.return_value = cur
    cur.fetchone.return_value = fetchone
    cur.fetchall.return_value = fetchall or []
    pool.getconn.return_value = conn
    return pool, conn, cur


@pytest.fixture(scope="module")
def app():
    with patch("database.get_pool", return_value=_pool()[0]):
        from earnings import router
        _app = FastAPI()
        _app.include_router(router, prefix="/api")
        from auth import get_current_user_optional
        _app.dependency_overrides[get_current_user_optional] = lambda: {"sub": UID}
        yield _app
        _app.dependency_overrides.clear()


class TestRefresh:

    def test_salta_i_ticker_freschi(self):
        import earnings
        pool, _, cur = _pool(fetchall=[("NVDA",), ("AAPL",)])   # entrambi freschi
        with patch("database.get_pool", return_value=pool), \
             patch("earnings._next_earnings_date") as nxt:
            n = earnings.refresh_earnings(["NVDA", "AAPL"])
        assert n == 0
        nxt.assert_not_called()

    def test_aggiorna_i_ticker_vecchi(self):
        import earnings
        pool, conn, cur = _pool(fetchall=[("NVDA",)])           # NVDA fresco, TSLA no
        with patch("database.get_pool", return_value=pool), \
             patch("earnings._next_earnings_date", return_value=date(2026, 7, 20)) as nxt:
            n = earnings.refresh_earnings(["NVDA", "TSLA"])
        assert n == 1
        nxt.assert_called_once_with("TSLA")


class TestUpcoming:

    ROWS = [
        {"ticker": "NVDA", "date": "2026-07-19", "days_left": 5,
         "sentiment": 0.31, "trend": 0.12, "news": 42},
    ]

    def test_pro_vede_il_sentiment(self, app):
        with patch("earnings.cache_get", return_value=self.ROWS), \
             patch("earnings.tier_di", return_value="pro"):
            with TestClient(app, raise_server_exceptions=False) as c:
                d = c.get("/api/earnings/upcoming").json()
        assert d["is_pro"] is True
        assert d["rows"][0]["sentiment"] == 0.31
        assert d["rows"][0]["trend"] == 0.12

    def test_free_vede_date_ma_non_sentiment(self, app):
        with patch("earnings.cache_get", return_value=self.ROWS), \
             patch("earnings.tier_di", return_value="free"):
            with TestClient(app, raise_server_exceptions=False) as c:
                d = c.get("/api/earnings/upcoming").json()
        assert d["is_pro"] is False
        r = d["rows"][0]
        assert r["ticker"] == "NVDA" and r["days_left"] == 5   # calendario visibile
        assert r["sentiment"] is None and r["trend"] is None   # sentiment mascherato

    def test_db_giu_lista_vuota(self, app):
        broken = MagicMock()
        broken.getconn.side_effect = RuntimeError("down")
        with patch("earnings.cache_get", return_value=None), \
             patch("earnings.cache_set"), \
             patch("database.get_pool", return_value=broken), \
             patch("earnings.tier_di", return_value="free"):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.get("/api/earnings/upcoming")
        assert resp.status_code == 200
        assert resp.json()["rows"] == []


# ── Il calendario si vede anche senza account ─────────────────────────────
#
# "Calendario per tutti" comprende chi non e' registrato, dal 16 agosto 2026.
# Prima l'endpoint pretendeva un token: a un visitatore rispondeva 401 e il
# calendario spariva dalla schermata di mercato senza dire perche', perche'
# chi lo chiama ignora l'errore di proposito.
class TestSenzaAccount:

    @pytest.fixture(autouse=True)
    def setup(self, app):
        from auth import get_current_user_optional
        app.dependency_overrides[get_current_user_optional] = lambda: None
        yield
        app.dependency_overrides.clear()

    def test_le_date_arrivano_lo_stesso(self, app):
        with patch("earnings._upcoming_rows", return_value=[
                    {"ticker": "AAPL", "data": "2026-08-20",
                     "sentiment": 0.4, "trend": "su"}]), \
             patch("earnings.cache_get", return_value=None), \
             patch("earnings.cache_set"):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.get("/api/earnings/upcoming")
        assert resp.status_code == 200, resp.text
        dati = resp.json()
        assert dati["rows"][0]["ticker"] == "AAPL"

    def test_ma_il_sentiment_pre_conti_resta_oscurato(self, app):
        with patch("earnings._upcoming_rows", return_value=[
                    {"ticker": "AAPL", "data": "2026-08-20",
                     "sentiment": 0.4, "trend": "su"}]), \
             patch("earnings.cache_get", return_value=None), \
             patch("earnings.cache_set"):
            with TestClient(app, raise_server_exceptions=False) as c:
                dati = c.get("/api/earnings/upcoming").json()
        assert dati["is_pro"] is False
        assert dati["rows"][0]["sentiment"] is None
        assert dati["rows"][0]["trend"] is None
