"""
test_market_copertura.py — Quanto c'e' dietro ogni nome della lista.

Il selettore offre 302 titoli, l'archivio ne segue 52, e il 18 agosto 2026
solo 27 arrivavano a cinque notizie distinte in 48 ore. Questo endpoint serve
a dirlo prima del clic invece che dopo.

La proprieta' da proteggere e' una sola e non e' il conteggio: e' che il
numero mostrato nel selettore sia LO STESSO che usa la classifica. Se le due
query divergono, il prodotto promette tre notizie e ne mostra una.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("DATABASE_URL", "postgresql://fake:fake@localhost/fake")

import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _pool(fetchall=None):
    pool, conn, cur = MagicMock(), MagicMock(), MagicMock()
    conn.cursor.return_value = cur
    cur.fetchall.return_value = fetchall if fetchall is not None else []
    pool.getconn.return_value = conn
    return pool


@pytest.fixture(scope="module")
def app():
    with patch("database.get_pool", return_value=_pool()):
        from market import router
        _app = FastAPI()
        _app.include_router(router, prefix="/api")
        yield _app


def _chiedi(app, righe):
    with patch("market.cache_get", return_value=None), \
         patch("market.cache_set"), \
         patch("market.get_pool", return_value=_pool(righe)):
        with TestClient(app, raise_server_exceptions=False) as c:
            return c.get("/api/market/copertura").json()


class TestCopertura:

    def test_dice_quante_notizie_ci_sono_per_titolo(self, app):
        d = _chiedi(app, [("NVDA", 21, 96), ("ENI.MI", 2, 9)])
        assert d["titoli"]["NVDA"] == {"ora": 21, "settimana": 96}
        assert d["titoli"]["ENI.MI"] == {"ora": 2, "settimana": 9}

    def test_porta_con_se_la_soglia_invece_di_farla_riscrivere(self, app):
        """
        Se la soglia viaggia col dato, quando cambia in market.py cambia
        anche la frase che l'utente legge, e le due non possono contraddirsi.
        E' la stessa scelta gia' fatta per `min_news` in /market/today.
        """
        import market
        d = _chiedi(app, [("NVDA", 21, 96)])
        assert d["min_news"] == market.MIN_NEWS
        assert d["finestra_ore"] == market.WINDOW_HOURS

    def test_un_titolo_senza_niente_semplicemente_non_c_e(self, app):
        """
        Chi non ha una riga in archivio non compare, e il frontend lo tratta
        come vuoto. Meglio dell'inventarsi uno zero che sembra una misura.
        """
        d = _chiedi(app, [("NVDA", 21, 96)])
        assert "ADIL" not in d["titoli"]

    def test_il_database_giu_non_diventa_un_errore_per_l_utente(self, app):
        rotto = MagicMock()
        rotto.getconn.side_effect = RuntimeError("down")
        with patch("market.cache_get", return_value=None), \
             patch("market.cache_set"), \
             patch("market.get_pool", return_value=rotto):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.get("/api/market/copertura")
        assert resp.status_code == 200
        assert resp.json()["titoli"] == {}

    def test_la_risposta_in_cache_non_ripassa_dal_database(self, app):
        pronto = {"min_news": 5, "finestra_ore": 48, "giorni_base": 7,
                  "titoli": {"NVDA": {"ora": 3, "settimana": 4}}}
        pool = _pool([])
        with patch("market.cache_get", return_value=pronto), \
             patch("market.get_pool", return_value=pool):
            with TestClient(app, raise_server_exceptions=False) as c:
                d = c.get("/api/market/copertura").json()
        assert d == pronto
        assert not pool.getconn.called


class TestStessoConteggioDellaClassifica:
    """
    La ragione per cui la chiave di normalizzazione e' una costante sola.
    """

    def test_la_chiave_del_titolo_e_condivisa_non_copiata(self):
        import inspect
        import market
        sorgente = inspect.getsource(market)
        # La definizione una volta, piu' gli usi: mai una seconda copia
        # letterale della regexp.
        assert sorgente.count("[^[:alnum:][:space:]]") == 1, (
            "la normalizzazione del titolo e' stata ricopiata: classifica e "
            "copertura possono ora divergere senza che nessun test se ne accorga")

    def test_le_due_query_usano_la_stessa_costante(self):
        import inspect
        import market
        for fn in (market._fetch_market, market._fetch_copertura):
            assert "CHIAVE_TITOLO_SQL" in inspect.getsource(fn), fn.__name__

    def test_la_finestra_e_la_stessa_della_classifica(self):
        import inspect
        import market
        sorgente = inspect.getsource(market._fetch_copertura)
        assert "WINDOW_HOURS" in sorgente
        assert "BASELINE_DAYS" in sorgente
