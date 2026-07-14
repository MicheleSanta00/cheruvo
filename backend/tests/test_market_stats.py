"""
test_market_stats.py — Contatori pubblici /market/stats.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("DATABASE_URL", "postgresql://fake:fake@localhost/fake")

import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _pool(fetchone=None):
    pool, conn, cur = MagicMock(), MagicMock(), MagicMock()
    conn.cursor.return_value = cur
    cur.fetchone.return_value = fetchone
    pool.getconn.return_value = conn
    return pool


@pytest.fixture(scope="module")
def app():
    with patch("database.get_pool", return_value=_pool()):
        from market import router
        _app = FastAPI()
        _app.include_router(router, prefix="/api")
        yield _app


class TestMarketStats:

    def test_contatori(self, app):
        from datetime import datetime
        row = (1240, 58200, 18, datetime(2026, 7, 14, 12, 0))
        with patch("market.cache_get", return_value=None), \
             patch("market.cache_set"), \
             patch("market.get_pool", return_value=_pool(row)):
            with TestClient(app, raise_server_exceptions=False) as c:
                d = c.get("/api/market/stats").json()
        assert d["news_today"] == 1240
        assert d["news_total"] == 58200
        assert d["tickers"] == 18
        assert d["last_update"].startswith("2026-07-14")

    def test_db_giu_restituisce_zeri(self, app):
        broken = MagicMock()
        broken.getconn.side_effect = RuntimeError("down")
        with patch("market.cache_get", return_value=None), \
             patch("market.cache_set"), \
             patch("market.get_pool", return_value=broken):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.get("/api/market/stats")
        assert resp.status_code == 200
        assert resp.json()["news_total"] == 0

    def test_cache_hit(self, app):
        sentinel = {"news_today": 1, "news_total": 2, "tickers": 3, "last_update": None}
        pool = _pool()
        with patch("market.cache_get", return_value=sentinel), \
             patch("market.get_pool", return_value=pool):
            with TestClient(app, raise_server_exceptions=False) as c:
                assert c.get("/api/market/stats").json() == sentinel
        pool.getconn.assert_not_called()
