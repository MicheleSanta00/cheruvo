"""
test_digest.py — Digest settimanale: token, selezione ticker, guardia lunedì,
endpoint di disiscrizione e preferenze.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("DATABASE_URL", "postgresql://fake:fake@localhost/fake")
os.environ.setdefault("RESEND_API_KEY", "re_fake")

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

import digest
from digest import (unsubscribe_token, _token_valid, _week_key, _pick_tickers,
                    send_weekly_digests)

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
        from digest import router
        _app = FastAPI()
        _app.include_router(router, prefix="/api")
        yield _app
        _app.dependency_overrides.clear()


class TestHelpers:

    def test_token_valido_e_confronto(self):
        tok = unsubscribe_token(UID)
        assert len(tok) == 32
        assert _token_valid(UID, tok)
        assert not _token_valid(UID, "sbagliato")
        assert not _token_valid(UID, "")

    def test_week_key_formato_iso(self):
        assert _week_key(datetime(2026, 7, 14, tzinfo=timezone.utc)) == "2026-W29"

    def test_pick_tickers_free_vs_pro(self):
        tk = ["AAPL", "ENI.MI", "NVDA"]
        assert _pick_tickers(tk, "free") == ["AAPL"]
        assert _pick_tickers(tk, "pro") == tk
        assert len(_pick_tickers([f"T{i}" for i in range(30)], "pro")) == digest.PRO_TICKERS


class TestSendGuard:

    def test_non_lunedi_non_invia(self):
        martedi = datetime(2026, 7, 14, tzinfo=timezone.utc)   # martedì
        assert martedi.weekday() != 0
        with patch("digest.datetime") as dt:
            dt.now.return_value = martedi
            assert send_weekly_digests() == 0

    def test_lunedi_salta_chi_ha_gia_ricevuto(self):
        lunedi = datetime(2026, 7, 13, tzinfo=timezone.utc)    # lunedì
        assert lunedi.weekday() == 0
        with patch("digest.datetime") as dt, \
             patch("digest.get_recipients", return_value=[
                 {"user_id": UID, "email": "a@b.c", "plan": "free", "tickers": ["NVDA"]}]), \
             patch("digest._already_sent", return_value=True), \
             patch("resend.Emails.send") as send:
            dt.now.return_value = lunedi
            assert send_weekly_digests() == 0
        send.assert_not_called()

    def test_lunedi_invia_e_marca(self):
        lunedi = datetime(2026, 7, 13, tzinfo=timezone.utc)
        stats = {"NVDA": {"avg": 0.31, "n": 12, "prev": 0.1,
                          "news": [{"title": "t", "url": "u", "sentiment": 0.7}]}}
        with patch("digest.datetime") as dt, \
             patch("digest.get_recipients", return_value=[
                 {"user_id": UID, "email": "a@b.c", "plan": "pro", "tickers": ["NVDA"]}]), \
             patch("digest._already_sent", return_value=False), \
             patch("digest.get_week_stats", return_value=stats), \
             patch("digest._mark_sent") as mark, \
             patch("resend.Emails.send") as send:
            dt.now.return_value = lunedi
            assert send_weekly_digests() == 1
        send.assert_called_once()
        mark.assert_called_once_with(UID, "2026-W29")
        html = send.call_args[0][0]["html"]
        assert "NVDA" in html and "unsubscribe" in html

    def test_niente_email_senza_dati(self):
        lunedi = datetime(2026, 7, 13, tzinfo=timezone.utc)
        with patch("digest.datetime") as dt, \
             patch("digest.get_recipients", return_value=[
                 {"user_id": UID, "email": "a@b.c", "plan": "free", "tickers": ["XYZ"]}]), \
             patch("digest._already_sent", return_value=False), \
             patch("digest.get_week_stats", return_value={}), \
             patch("resend.Emails.send") as send:
            dt.now.return_value = lunedi
            assert send_weekly_digests() == 0
        send.assert_not_called()


class TestEndpoints:

    def test_unsubscribe_token_sbagliato_403(self, app):
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get(f"/api/digest/unsubscribe?u={UID}&t=abc")
        assert resp.status_code == 403

    def test_unsubscribe_token_giusto_disattiva(self, app):
        pool, conn, cur = _pool()
        with patch("database.get_pool", return_value=pool):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.get(f"/api/digest/unsubscribe?u={UID}&t={unsubscribe_token(UID)}")
        assert resp.status_code == 200
        # Dal 24 settembre 2026 lo stesso link spegne tutte le email
        # facoltative (digest, avvisi, consigli dei primi giorni), e la
        # pagina lo dice.
        assert "Email facoltative disattivate" in resp.text
        sql = cur.execute.call_args[0][0]
        assert "enabled = FALSE" in sql or "VALUES (%s, FALSE" in sql

    def test_prefs_default_true(self, app):
        from auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: {"sub": UID}
        pool, _, cur = _pool(fetchone=None)
        with patch("database.get_pool", return_value=pool):
            with TestClient(app, raise_server_exceptions=False) as c:
                assert c.get("/api/digest/prefs").json() == {"enabled": True}
        app.dependency_overrides.clear()


# ── 24 settembre 2026: testo di terzi dentro l'HTML ───────────────────────

def test_un_titolo_con_dentro_html_resta_testo():
    """
    I titoli arrivano da migliaia di siti che non controlliamo: un titolo con
    un link dentro diventava un link vero, con il nostro nome sopra.
    """
    utente = {"user_id": UID, "plan": "pro", "tickers": ["NVDA"]}
    stats = {"NVDA": {"avg": 0.1, "prev": 0.0, "n": 3, "news": [
        {"title": '<a href="https://truffa.example">Clicca qui</a>',
         "url": "javascript:alert(1)", "sentiment": 0.4}]}}
    corpo = digest._build_digest_html(utente, stats, ["NVDA"])
    assert "<a href=\"https://truffa.example\">" not in corpo
    assert "&lt;a href=" in corpo
    assert "javascript:" not in corpo


def test_gli_indirizzi_veri_restano():
    assert digest.url_sicuro("https://www.reuters.com/x?a=1&b=2") == \
        "https://www.reuters.com/x?a=1&amp;b=2"
    assert digest.url_sicuro("ftp://x") == "#"
    assert digest.url_sicuro(None) == "#"


def test_le_notizie_senza_punteggio_non_passano_davanti():
    """In Postgres i NULL vengono PRIMA in un ordinamento discendente."""
    import inspect
    assert "NULLS LAST" in inspect.getsource(digest.get_week_stats)
