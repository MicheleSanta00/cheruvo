"""
Test della raccolta GDELT per mercato e del controllo di salute.

I casi qui dentro non sono inventati: riproducono il crollo di copertura
avvenuto fra il 19 luglio e il 3 agosto 2026, quando gli articoli raccolti in
48 ore sono passati da 468 a 55 e i titoli italiani coperti da 3 a zero senza
che nessuno se ne accorgesse per due settimane.
"""
from unittest.mock import MagicMock, patch

import pytest

import gdelt_source as g
import salute as s


# ── Utilità ───────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _niente_attese():
    """Nei test non aspettiamo davvero il rate limit di GDELT."""
    g.PAUSA_MINIMA = 0
    g._pausa_corrente = 0
    g._cache_mercato.clear()
    g._or_supportato = None
    g._nomi_cache.clear()
    yield


def _risposta(articoli, codice=200):
    r = MagicMock()
    r.status_code = codice
    r.text = "{}"
    r.raise_for_status = lambda: None
    r.json = lambda: {"articles": articoli}
    return r


ARTICOLI_ITALIANI = [
    {"title": "Eni Versalis, presentato al Mimit il piano di riconversione",
     "language": "Italian", "domain": "qds.it", "url": "http://x/1",
     "seendate": "20260803T090000Z"},
    {"title": "Enel chiude il semestre con utile in crescita",
     "language": "Italian", "domain": "ansa.it", "url": "http://x/2",
     "seendate": "20260803T080000Z"},
    {"title": "UniCredit e Intesa a confronto sui dividendi",
     "language": "Italian", "domain": "milanofinanza.it", "url": "http://x/3",
     "seendate": "20260802T120000Z"},
    {"title": "Incidente sulla statale, traffico in tilt",
     "language": "Italian", "domain": "cronaca.it", "url": "http://x/4",
     "seendate": "20260803T070000Z"},
]


# ── Raccolta per mercato ──────────────────────────────────────────────────
def test_una_chiamata_copre_tutto_il_mercato():
    """Sei società italiane devono costare due chiamate, non dodici."""
    chiamate = []

    def finto(*a, **k):
        q = k.get("params", {}).get("query", "")
        chiamate.append(q)
        return _risposta(ARTICOLI_ITALIANI if "sourcelang:italian" in q else [])

    with patch.object(g.requests, "get", side_effect=finto):
        for tk in ["ENI.MI", "ENEL.MI", "UCG.MI", "ISP.MI", "RACE.MI", "STMMI.MI"]:
            g.fetch_gdelt(tk)

    assert len(chiamate) == 2, f"attese 2 chiamate, fatte {len(chiamate)}"
    assert " OR " in chiamate[0]


def test_articolo_su_due_societa_finisce_a_entrambe():
    """'UniCredit e Intesa a confronto' riguarda due titoli, non uno."""
    with patch.object(g.requests, "get",
                      side_effect=lambda *a, **k: _risposta(
                          ARTICOLI_ITALIANI
                          if "sourcelang:italian" in k.get("params", {}).get("query", "")
                          else [])):
        ucg = g.fetch_gdelt("UCG.MI")
        isp = g.fetch_gdelt("ISP.MI")

    assert any("dividendi" in n["title"] for n in ucg)
    assert any("dividendi" in n["title"] for n in isp)


def test_cronaca_locale_non_entra_in_nessun_titolo():
    with patch.object(g.requests, "get",
                      side_effect=lambda *a, **k: _risposta(
                          ARTICOLI_ITALIANI
                          if "sourcelang:italian" in k.get("params", {}).get("query", "")
                          else [])):
        tutte = [n for tk in ["ENI.MI", "ENEL.MI", "UCG.MI", "ISP.MI"]
                 for n in g.fetch_gdelt(tk)]
    assert not any("Incidente" in n["title"] for n in tutte)


def test_ripiega_se_la_query_raggruppata_non_rende():
    """
    Non è stato possibile verificare da fuori se GDELT accetta l'OR fra
    parentesi. Se non lo accetta il prodotto non deve restare a secco: deve
    tornare al metodo per singolo titolo.
    """
    def finto(*a, **k):
        q = k.get("params", {}).get("query", "")
        if " OR " in q:
            return _risposta([])
        return _risposta([ARTICOLI_ITALIANI[0]])

    with patch.object(g.requests, "get", side_effect=finto):
        news = g.fetch_gdelt("ENI.MI")

    assert len(news) == 1, "il ripiego per titolo deve recuperare la notizia"


def test_titoli_usa_invariati():
    """Quello che oggi funziona non deve cambiare comportamento."""
    chiamate = []

    def finto(*a, **k):
        chiamate.append(k.get("params", {}).get("query", ""))
        return _risposta([{"title": "Nvidia beats estimates", "language": "English",
                           "domain": "reuters.com", "url": "http://x/9",
                           "seendate": "20260803T090000Z"}])

    with patch.object(g.requests, "get", side_effect=finto):
        news = g.fetch_gdelt("NVDA")

    assert len(chiamate) == 1
    assert " OR " not in chiamate[0]
    assert len(news) == 1


def test_il_429_non_fa_perdere_il_giro():
    """Un rifiuto per eccesso di richieste va riprovato, non trattato da errore."""
    risposte = [_risposta([], 429),
                _risposta([{"title": "Nvidia beats estimates", "language": "English",
                            "domain": "reuters.com", "url": "http://x/9",
                            "seendate": "20260803T090000Z"}])]
    with patch.object(g.requests, "get", side_effect=lambda *a, **k: risposte.pop(0)):
        news = g.fetch_gdelt("NVDA")
    assert len(news) == 1


def test_sigla_di_borsa_non_sprecare_chiamate():
    """EZJ.L senza nome risolto darebbe query 'EZJ': inutile, meglio saltare."""
    chiamate = []

    def finto(*a, **k):
        chiamate.append(k.get("params", {}).get("query", ""))
        return _risposta([])

    with patch.object(g.requests, "get", side_effect=finto), \
         patch.object(g, "_nome_da_yfinance", return_value=None):
        assert g.fetch_gdelt("EZJ.L") == []
    assert not chiamate


# ── Controllo di salute ───────────────────────────────────────────────────
MEDIA_19_LUGLIO = {"articoli_48h": 468.0, "titoli_con_notizie": 17.0,
                   "titoli_italiani": 3.0, "giorni": 7}


def _controlla(oggi, storia):
    inviati = []
    with patch.object(s, "init_tabella_salute", lambda: None), \
         patch.object(s, "misura", lambda: oggi), \
         patch.object(s, "salva", lambda m: None), \
         patch.object(s, "_media_precedente", lambda: storia), \
         patch.object(s, "_avvisa", lambda righe: inviati.extend(righe)):
        s.controlla_e_registra()
    return inviati


def test_avrebbe_visto_il_crollo_del_3_agosto():
    allarmi = _controlla(
        {"titoli_totali": 34, "titoli_con_notizie": 8,
         "articoli_48h": 55, "titoli_italiani": 0},
        MEDIA_19_LUGLIO)
    assert len(allarmi) >= 2
    assert any("italiano" in a for a in allarmi)


def test_giornata_normale_nessun_allarme():
    assert not _controlla(
        {"titoli_totali": 34, "titoli_con_notizie": 16,
         "articoli_48h": 420, "titoli_italiani": 3},
        MEDIA_19_LUGLIO)


def test_weekend_non_genera_falsi_allarmi():
    """Coi mercati chiusi i volumi calano per tutti: non è un guasto."""
    assert not _controlla(
        {"titoli_totali": 34, "titoli_con_notizie": 3,
         "articoli_48h": 9, "titoli_italiani": 0},
        {"articoli_48h": 14.0, "titoli_con_notizie": 4.0,
         "titoli_italiani": 0.0, "giorni": 7})


def test_senza_storico_non_inventa_allarmi():
    assert not _controlla(
        {"titoli_totali": 34, "titoli_con_notizie": 8,
         "articoli_48h": 55, "titoli_italiani": 0},
        None)
