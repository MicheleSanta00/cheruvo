"""
L'ora delle notizie arriva fino al browser.

Il difetto, visto sull'app vera il 24 settembre 2026: tutte le notizie di oggi
mostravano "02:00 AM". /api/news tagliava la data a "%Y-%m-%d", il browser la
leggeva come mezzanotte UTC e TopNews.jsx, che per le notizie di oggi scrive
l'ora, scriveva le due di notte italiane per tutte.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("DATABASE_URL", "postgresql://fake:fake@localhost/fake")
os.environ.setdefault("GROQ_API_KEY", "gsk_fake_key_for_tests")

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def app():
    pool = MagicMock()
    with patch("database.get_pool", return_value=pool), \
         patch("database._get_connection"):
        from main import app as _app
        yield _app
        _app.dependency_overrides.clear()


def _archivio():
    return pd.DataFrame({
        "title": ["Nvidia sale", "Nvidia scende"],
        "source": ["GDELT · a.com", "GDELT · b.com"],
        "sentiment": [0.3, -0.2],
        # Come le rende psycopg2 da una colonna TIMESTAMPTZ: con il fuso.
        "published_date": [datetime(2026, 9, 24, 14, 5, tzinfo=timezone.utc),
                           datetime(2026, 9, 24, 9, 30, tzinfo=timezone.utc)],
    })


def _chiedi(app, ticker="NVDA"):
    from auth import get_current_user_optional
    app.dependency_overrides[get_current_user_optional] = lambda: None
    analizzatore = MagicMock()
    analizzatore.get_data.return_value = _archivio()
    try:
        with patch("main.SuperNewsAnalyzer", return_value=analizzatore), \
             patch("main.cache_get", return_value=None), \
             patch("main.cache_set"):
            with TestClient(app, raise_server_exceptions=False) as c:
                return c.get(f"/api/news/{ticker}?days=2")
    finally:
        app.dependency_overrides.clear()


def test_la_notizia_porta_anche_l_ora(app):
    resp = _chiedi(app)
    assert resp.status_code == 200
    date = [n["published_date"] for n in resp.json()["news"]]
    assert "2026-09-24T14:05:00Z" in date
    assert "2026-09-24T09:30:00Z" in date


def test_i_primi_dieci_caratteri_restano_la_data(app):
    """CSV (App.jsx) e PDF (generatePDF.js) tagliano a dieci: devono restare uguali."""
    resp = _chiedi(app)
    assert {n["published_date"][:10] for n in resp.json()["news"]} == {"2026-09-24"}
