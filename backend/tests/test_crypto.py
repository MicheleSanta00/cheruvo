"""
Test delle criptovalute.

Le crypto attraversano quasi tutto il backend e in quattro punti si comportano
in modo diverso dai titoli azionari. Ognuno di quei punti, sbagliato, produce
un difetto che l'utente vede: una chiamata sprecata, un confronto su venti ore
spacciato per ventiquattro, un calendario con righe vuote, un prezzo troncato.
"""
import time
from unittest.mock import MagicMock, patch

import pytest

import earnings
import gdelt_source as g
import prices as p
import sec_source as s


@pytest.fixture(autouse=True)
def _niente_attese():
    g.PAUSA_MINIMA = 0
    g._pausa_corrente = 0
    g._cache_mercato.clear()
    g._or_supportato = None
    g._nomi_cache.clear()
    yield


# ── Riconoscimento ────────────────────────────────────────────────────────
def test_riconosce_le_crypto():
    for tk in ("BTC-USD", "eth-usd", "SOL-USD"):
        assert p.e_crypto(tk) and g.e_crypto(tk)
    for tk in ("NVDA", "ENI.MI", "SHEL.L"):
        assert not p.e_crypto(tk) and not g.e_crypto(tk)


# ── Nessuna chiamata sprecata ─────────────────────────────────────────────
def test_le_crypto_non_vanno_alla_sec():
    """Bitcoin non deposita bilanci: senza il filtro sprecheremmo una ricerca."""
    assert s.fetch_sec("BTC-USD") == []


def test_le_crypto_non_entrano_nel_calendario_earnings():
    with patch.object(earnings, "_conn", side_effect=AssertionError("mai qui")):
        assert earnings.refresh_earnings(["BTC-USD", "ETH-USD"]) == 0


def _gdelt_finto(chiamate, articoli):
    def finto(*a, **k):
        chiamate.append(k.get("params", {}).get("query", ""))
        r = MagicMock(); r.status_code = 200; r.text = "{}"
        r.raise_for_status = lambda: None
        r.json = lambda: {"articles": articoli}
        return r
    return finto


def test_gdelt_cerca_il_nome_non_il_ticker():
    """Nessun giornale scrive 'BTC-USD': si cerca 'Bitcoin'."""
    chiamate = []
    articoli = [{
        "title": "Bitcoin Flashes Death Cross That Preceded 30% Price Decline",
        "language": "English", "domain": "finance.yahoo.com",
        "url": "http://x/1", "seendate": "20260804T184500Z"}]

    with patch.object(g.requests, "get", side_effect=_gdelt_finto(chiamate, articoli)):
        news = g.fetch_gdelt("BTC-USD")

    assert len(chiamate) == 1
    assert "Bitcoin" in chiamate[0]
    assert "BTC-USD" not in chiamate[0]
    assert len(news) == 1


def test_tutte_le_crypto_con_una_sola_chiamata():
    """
    Venti monete devono costare UNA interrogazione, non venti.

    È lo stesso raggruppamento con OR usato per i titoli italiani, e sulle
    crypto funziona ancora meglio perché i nomi (Bitcoin, Solana, Chainlink)
    sono distintivi. Senza questo, ampliare il paniere avrebbe voluto dire
    moltiplicare le chiamate e tornare dritti nei 429.
    """
    chiamate = []
    articoli = [
        {"title": "Bitcoin Flashes Death Cross", "language": "English",
         "domain": "coindesk.com", "url": "http://x/1", "seendate": "20260805T090000Z"},
        # Qui c'era "Solana network hits record throughput", e dal 18 agosto
        # 2026 quel titolo non entra piu'. "Solana" sta in AMBIGUI, quindi
        # esige una parola di contesto finanziario, e "network hits record
        # throughput" non ne ha. Prima entrava SOLO da questo percorso, perche'
        # l'API non applicava la regola che i file grezzi applicavano gia': e'
        # la stessa divergenza che ha fatto entrare 52 righe di cronaca come
        # notizie su NEAR.
        #
        # Il costo va detto: quella era una notizia vera su Solana, e adesso
        # resta fuori da tutti e due i percorsi.
        {"title": "Solana price surges as traders pile into SOL", "language": "English",
         "domain": "theblock.co", "url": "http://x/2", "seendate": "20260805T083000Z"},
    ]
    crypto = [tk for tk in g.TERMINE_QUERY if g.e_crypto(tk)]
    assert len(crypto) >= 15, "il paniere crypto si è ristretto"

    with patch.object(g.requests, "get", side_effect=_gdelt_finto(chiamate, articoli)):
        risultati = {tk: g.fetch_gdelt(tk) for tk in crypto}

    assert len(chiamate) == 1, f"{len(crypto)} monete hanno fatto {len(chiamate)} chiamate"
    assert " OR " in chiamate[0]
    # Ogni moneta riceve solo ciò che la nomina davvero
    assert any("Death Cross" in n["title"] for n in risultati["BTC-USD"])
    assert any("Solana" in n["title"] for n in risultati["SOL-USD"])
    assert not risultati["DOGE-USD"]


# ── Confronto a 24 ore vere ───────────────────────────────────────────────
def _yahoo_finto(prezzo_24h=60240.0, serie_ok=True):
    ora = time.time()

    def finto(url, headers=None, params=None, timeout=None):
        r = MagicMock(); r.status_code = 200; r.raise_for_status = lambda: None
        if params.get("interval") == "1h":
            if not serie_ok:
                raise Exception("serie oraria non disponibile")
            ts = [int(ora - 3600 * i) for i in range(47, -1, -1)]
            # il punto a 24h fa è l'indice 24 partendo dal fondo
            cl = [prezzo_24h] * 48
            r.json = lambda: {"chart": {"result": [{
                "timestamp": ts, "indicators": {"quote": [{"close": cl}]}}]}}
        else:
            r.json = lambda: {"chart": {"result": [{"meta": {
                "currency": "USD", "fullExchangeName": "CCC",
                "regularMarketPrice": 64366.85, "regularMarketTime": int(ora),
                "chartPreviousClose": 62813.74,
                "currentTradingPeriod": {"regular": {
                    "start": int(ora - 3600), "end": int(ora + 3600)}}}}]}}
        return r
    return finto


def test_crypto_confronta_su_24_ore_vere():
    """
    La 'chiusura di ieri' di Yahoo per una crypto è il prezzo a mezzanotte UTC.
    Alle otto di sera sarebbe un confronto su venti ore chiamato 'un giorno'.
    """
    with patch.object(p.requests, "get", side_effect=_yahoo_finto()):
        st = p.stato_mercato("BTC-USD")
    assert st["tipo_riferimento"] == "24h"
    assert abs(st["chiusura_precedente"] - 60240.0) < 1


def test_azioni_continuano_a_usare_la_chiusura_precedente():
    with patch.object(p.requests, "get", side_effect=_yahoo_finto()):
        st = p.stato_mercato("NVDA")
    assert st["tipo_riferimento"] == "chiusura_precedente"
    assert st["chiusura_precedente"] == 62813.74
    assert st["sempre_aperto"] is False


def test_crypto_sempre_aperte():
    with patch.object(p.requests, "get", side_effect=_yahoo_finto()):
        st = p.stato_mercato("BTC-USD")
    assert st["aperto"] is True and st["sempre_aperto"] is True


def test_serie_oraria_giu_ripiega_senza_esplodere():
    with patch.object(p.requests, "get", side_effect=_yahoo_finto(serie_ok=False)):
        st = p.stato_mercato("BTC-USD")
    assert st["chiusura_precedente"] == 62813.74
    assert st["tipo_riferimento"] == "chiusura_precedente"


def test_stato_mercato_non_solleva_mai():
    with patch.object(p.requests, "get", side_effect=Exception("rete giù")):
        st = p.stato_mercato("BTC-USD")
    assert st["prezzo"] is None and st["aperto"] is False
