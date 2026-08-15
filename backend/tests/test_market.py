"""
test_market.py — Screener pubblico "Mercato oggi" (/market/today).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("DATABASE_URL", "postgresql://fake:fake@localhost/fake")

import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_pool(fetchall=None):
    pool, conn, cur = MagicMock(), MagicMock(), MagicMock()
    conn.cursor.return_value = cur
    cur.fetchall.return_value = fetchall or []
    pool.getconn.return_value = conn
    return pool


@pytest.fixture(scope="module")
def app():
    with patch("database.get_pool", return_value=_make_pool()):
        from market import router
        _app = FastAPI()
        _app.include_router(router, prefix="/api")
        yield _app


class TestMarketToday:

    def test_pubblico_senza_login(self, app):
        """L'endpoint non richiede autenticazione."""
        with patch("market.cache_get", return_value=None), \
             patch("market.cache_set"), \
             patch("market.get_pool", return_value=_make_pool()):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.get("/api/market/today")
        assert resp.status_code == 200
        assert "rows" in resp.json()

    def test_shape_e_delta(self, app):
        # (ticker, media, notizie distinte, media precedente, riprese)
        rows = [("NVDA", 0.42, 12, 0.30, 3), ("TSLA", -0.21, 5, None, 0)]
        with patch("market.cache_get", return_value=None), \
             patch("market.cache_set"), \
             patch("market.get_pool", return_value=_make_pool(rows)):
            with TestClient(app, raise_server_exceptions=False) as c:
                data = c.get("/api/market/today").json()
        assert data["window_hours"] == 48
        r0, r1 = data["rows"]
        assert r0 == {"ticker": "NVDA", "sentiment": 0.42, "news": 12,
                      "delta": 0.12, "riprese": 3}
        assert r1["delta"] is None          # nessuna baseline → delta assente

    def test_cache_hit_non_tocca_il_db(self, app):
        sentinel = {"updated_at": "x", "window_hours": 48, "rows": [{"ticker": "AAPL"}]}
        pool = _make_pool()
        with patch("market.cache_get", return_value=sentinel), \
             patch("market.get_pool", return_value=pool):
            with TestClient(app, raise_server_exceptions=False) as c:
                data = c.get("/api/market/today").json()
        assert data == sentinel
        pool.getconn.assert_not_called()

    def test_la_soglia_e_nella_query_e_non_e_piu_due(self, app):
        """
        La riga che il 7 agosto 2026 apriva la home: "PIÙ RIALZISTI: 1. ADA
        +0,34 con 3 news". Con tre articoli l'incertezza sulla media è più
        grande dell'intera scala della classifica, quindi il primo posto era
        sorteggiato. Se qualcuno riabbassa questa soglia per riempire la
        pagina, questo test lo ferma.
        """
        import market
        assert market.MIN_NEWS >= 5

        pool = _make_pool([("BTC-USD", 0.10, 30, 0.05)])
        with patch("market.cache_get", return_value=None), \
             patch("market.cache_set"), \
             patch("market.get_pool", return_value=pool):
            with TestClient(app, raise_server_exceptions=False) as c:
                c.get("/api/market/today")

        cur = pool.getconn.return_value.cursor.return_value
        sql, params = cur.execute.call_args[0]
        assert "r.n_now >= %s" in sql, "il filtro non è più nella query"
        assert params[0] == market.MIN_NEWS, (
            "la query usa un valore diverso dalla costante: la soglia è stata "
            "scritta due volte e le due copie sono già divergenti")

    def test_la_soglia_viaggia_col_dato(self, app):
        """
        L'interfaccia scrive "almeno N notizie" leggendo questo campo. Se
        sparisse, la frase mostrata all'utente resterebbe ferma su un numero
        vecchio mentre il filtro ne usa un altro.
        """
        import market
        with patch("market.cache_get", return_value=None), \
             patch("market.cache_set"), \
             patch("market.get_pool", return_value=_make_pool()):
            with TestClient(app, raise_server_exceptions=False) as c:
                data = c.get("/api/market/today").json()
        assert data["min_news"] == market.MIN_NEWS

    def test_errore_db_restituisce_lista_vuota(self, app):
        broken = MagicMock()
        broken.getconn.side_effect = RuntimeError("db down")
        with patch("market.cache_get", return_value=None), \
             patch("market.cache_set"), \
             patch("market.get_pool", return_value=broken):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.get("/api/market/today")
        assert resp.status_code == 200
        assert resp.json()["rows"] == []


class TestClassificaSenzaDoppioni:
    """
    Un titolo non deve entrare in classifica grazie alle riprese.

    Il 15 agosto 2026, su un campione di 300 righe, 61 erano lo stesso lancio
    d'agenzia ripreso da 61 testate. Con COUNT(*) un titolo poteva superare
    MIN_NEWS con UNA notizia sola rilanciata cinque volte, e comparire in home
    con scritto "5 news".
    """

    def test_la_query_fonde_le_riprese_prima_di_mediare(self, app):
        pool = _make_pool([("NVDA", 0.4, 9, 0.3, 40)])
        with patch("market.cache_get", return_value=None), \
             patch("market.cache_set"), \
             patch("market.get_pool", return_value=pool):
            with TestClient(app, raise_server_exceptions=False) as c:
                c.get("/api/market/today")
        sql = pool.getconn.return_value.cursor.return_value.execute.call_args[0][0]
        assert "GROUP BY ticker, 2" in sql, "non raggruppa per titolo normalizzato"
        assert "FROM distinte" in sql, "media e conteggio non girano sulle distinte"

    def test_anche_la_baseline_fonde_le_riprese(self, app):
        """
        Se la finestra recente fonde e quella precedente no, il delta confronta
        due cose diverse e sembra un movimento dove non c'e'.
        """
        pool = _make_pool([("NVDA", 0.4, 9, 0.3, 40)])
        with patch("market.cache_get", return_value=None), \
             patch("market.cache_set"), \
             patch("market.get_pool", return_value=pool):
            with TestClient(app, raise_server_exceptions=False) as c:
                c.get("/api/market/today")
        sql = pool.getconn.return_value.cursor.return_value.execute.call_args[0][0]
        assert "distinte_prima" in sql and "FROM distinte_prima" in sql

    def test_un_titolo_vuoto_non_si_fonde_con_gli_altri_titoli_vuoti(self, app):
        """
        Senza testo non si puo' dire che due notizie siano la stessa: fonderle
        cancellerebbe righe vere. Il ripiego e' sull'id.
        """
        pool = _make_pool([("NVDA", 0.4, 9, 0.3, 0)])
        with patch("market.cache_get", return_value=None), \
             patch("market.cache_set"), \
             patch("market.get_pool", return_value=pool):
            with TestClient(app, raise_server_exceptions=False) as c:
                c.get("/api/market/today")
        sql = pool.getconn.return_value.cursor.return_value.execute.call_args[0][0]
        assert "'id:' || id::text" in sql

    def test_la_normalizzazione_e_la_stessa_del_grafico(self, app):
        """
        La chiave SQL deve rispecchiare `giornaliero.chiave_titolo`: minuscole,
        punteggiatura a spazi, spazi collassati, primi 90 caratteri. Se le due
        divergono, il grafico e la classifica fondono gruppi diversi e mostrano
        numeri che non tornano fra loro.
        """
        pool = _make_pool([("NVDA", 0.4, 9, 0.3, 0)])
        with patch("market.cache_get", return_value=None), \
             patch("market.cache_set"), \
             patch("market.get_pool", return_value=pool):
            with TestClient(app, raise_server_exceptions=False) as c:
                c.get("/api/market/today")
        sql = pool.getconn.return_value.cursor.return_value.execute.call_args[0][0]
        for pezzo in ("lower(", "[^[:alnum:][:space:]]", "left(", "90)"):
            assert pezzo in sql, f"manca {pezzo} nella normalizzazione"


def test_la_classifica_copre_tutti_i_titoli_seguiti(app):
    """
    MAX_ROWS non e' solo "quante righe mostrare": questo endpoint e' anche la
    fonte dei punteggi della barra laterale, con una chiamata sola, pubblica e
    in cache.

    Col taglio a 20, un titolo fuori dai primi venti per sentiment non c'era e
    la barra doveva chiederlo a /api/news uno per uno, endpoint limitato a 20
    al minuto. Il 15 agosto 2026 META aveva 179 notizie e media -0.16 e
    mostrava un trattino, perche' quelle richieste venivano respinte in
    silenzio.
    """
    import market
    from gdelt_source import TERMINE_QUERY
    assert market.MAX_ROWS >= len(TERMINE_QUERY), (
        f"MAX_ROWS ({market.MAX_ROWS}) non copre i {len(TERMINE_QUERY)} titoli "
        "seguiti: la barra laterale tornera' a mostrare trattini"
    )
