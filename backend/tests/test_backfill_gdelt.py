"""
Test della ricostruzione storica da GDELT.

Il motivo per cui questi casi esistono è che la ricostruzione può fallire in
un modo che NON si vede: se le date non arrivano a GDELT, o se la cache dei
mercati serve gli stessi articoli a ogni finestra, il lavoro gira per un'ora,
scrive nel log "0 nuove" trenta volte e sembra semplicemente che non ci fosse
niente da recuperare. Nessun errore, nessun allarme, e uno se ne accorge solo
molto dopo guardando le date in archivio.

Ognuno dei due modi ha il suo caso qui sotto.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

import gdelt_source as g


@pytest.fixture(autouse=True)
def _niente_attese():
    g.PAUSA_MINIMA = 0
    g._pausa_corrente = 0
    g._cache_mercato.clear()
    g._or_supportato = None
    yield


def _risposta(articoli):
    r = MagicMock()
    r.status_code = 200
    r.text = "{}"
    r.raise_for_status = lambda: None
    r.json = lambda: {"articles": articoli}
    return r


GIUGNO = (datetime(2026, 6, 6, tzinfo=timezone.utc),
          datetime(2026, 6, 9, tzinfo=timezone.utc))
LUGLIO = (datetime(2026, 7, 6, tzinfo=timezone.utc),
          datetime(2026, 7, 9, tzinfo=timezone.utc))


# ── Le date devono arrivare a GDELT ───────────────────────────────────────
def test_finestra_manda_le_date_e_toglie_timespan():
    """
    Con una finestra, la chiamata deve portare startdatetime/enddatetime e NON
    timespan. GDELT accetta i due modi ma non insieme: mandandoli entrambi si
    otterrebbero le notizie di oggi, cioè esattamente quello che la
    ricostruzione non deve fare.
    """
    with patch.object(g.requests, "get", return_value=_risposta([])) as mock:
        g._interroga("Bitcoin", 250, "1d", finestra=GIUGNO)

    params = mock.call_args.kwargs["params"]
    assert params["startdatetime"] == "20260606000000"
    assert params["enddatetime"] == "20260609000000"
    assert "timespan" not in params


def test_senza_finestra_resta_il_comportamento_di_sempre():
    """Il fetch quotidiano non deve cambiare: manda timespan e nessuna data."""
    with patch.object(g.requests, "get", return_value=_risposta([])) as mock:
        g._interroga("Bitcoin", 250, "7d")

    params = mock.call_args.kwargs["params"]
    assert params["timespan"] == "7d"
    assert "startdatetime" not in params and "enddatetime" not in params


def test_le_date_sono_sempre_in_utc():
    """
    GDELT ragiona in UTC. Se passasse un orario locale, ogni finestra
    slitterebbe di un paio d'ore e sui confini si perderebbero articoli.
    """
    fuso_avanti = timezone(timedelta(hours=2))
    d = datetime(2026, 6, 6, 1, 30, tzinfo=fuso_avanti)   # = 5 giugno 23:30 UTC
    assert g._fmt_finestra(d) == "20260605233000"


# ── La cache non deve mescolare le finestre ───────────────────────────────
def test_finestre_diverse_non_si_servono_dalla_stessa_cache():
    """
    Il caso che avrebbe rovinato tutto in silenzio.

    La cache dei mercati era indicizzata sulla sola lingua. Ricostruendo mese
    per mese, la prima finestra avrebbe riempito la cache e TUTTE le successive
    avrebbero riletto quei ventiquattro articoli invece di chiedere le loro
    date. Risultato: novanta giorni di storico tutti uguali al primo, e nessun
    errore da nessuna parte.
    """
    giugno = [{"title": "Bitcoin rallies in June", "language": "English",
               "domain": "coindesk.com", "url": "http://x/giugno",
               "seendate": "20260607T120000Z"}]
    luglio = [{"title": "Bitcoin dips in July", "language": "English",
               "domain": "coindesk.com", "url": "http://x/luglio",
               "seendate": "20260707T120000Z"}]

    with patch.object(g.requests, "get", side_effect=[_risposta(giugno),
                                                      _risposta(luglio)]) as mock:
        a = g._articoli_del_mercato("Crypto", 250, "1d", finestra=GIUGNO)
        b = g._articoli_del_mercato("Crypto", 250, "1d", finestra=LUGLIO)

    assert mock.call_count == 2, "la seconda finestra non ha interrogato GDELT"
    assert a[0]["title"] != b[0]["title"], "due finestre, stessi articoli"
    assert "June" in a[0]["title"] and "July" in b[0]["title"]


def test_la_stessa_finestra_invece_usa_la_cache():
    """
    Il risparmio deve restare: venti monete nella stessa finestra devono
    costare UNA chiamata, non venti. È il motivo per cui ricostruire le
    criptovalute costa minuti invece di ore.
    """
    art = [{"title": "Bitcoin steady", "language": "English",
            "domain": "coindesk.com", "url": "http://x/1",
            "seendate": "20260607T120000Z"}]

    with patch.object(g.requests, "get", return_value=_risposta(art)) as mock:
        g._articoli_del_mercato("Crypto", 250, "1d", finestra=GIUGNO)
        g._articoli_del_mercato("Crypto", 250, "1d", finestra=GIUGNO)

    assert mock.call_count == 1


def test_la_cache_distingue_anche_i_timespan():
    """Stessa logica per il fetch dal vivo: 1d e 7d sono richieste diverse."""
    art = [{"title": "Bitcoin news", "language": "English",
            "domain": "coindesk.com", "url": "http://x/1",
            "seendate": "20260807T120000Z"}]

    with patch.object(g.requests, "get", return_value=_risposta(art)) as mock:
        g._articoli_del_mercato("Crypto", 250, "1d")
        g._articoli_del_mercato("Crypto", 250, "7d")

    assert mock.call_count == 2


# ── La sonda deve accorgersi se GDELT ignora le date ──────────────────────
def test_la_sonda_boccia_gdelt_se_ignora_le_date():
    """
    Se GDELT rispondesse 200 con le notizie di oggi invece di quelle chieste,
    la sonda deve fermare tutto. Senza questo controllo la ricostruzione
    scriverebbe trenta volte le stesse notizie recenti, gonfiando l'archivio
    di doppioni mascherati da storico.
    """
    import backfill_gdelt as bf

    oggi = datetime.now(timezone.utc).strftime("%Y%m%dT120000Z")
    fuori_finestra = [{"title": "Notizia di oggi", "language": "English",
                       "domain": "coindesk.com", "url": "http://x/1",
                       "seendate": oggi}]

    with patch.object(bf, "_interroga", return_value=fuori_finestra):
        assert bf.sonda_finestre() is False


def test_la_sonda_passa_se_le_date_sono_giuste():
    import backfill_gdelt as bf

    dentro = (datetime.now(timezone.utc) - timedelta(days=31)).strftime("%Y%m%dT120000Z")
    articoli = [{"title": "Notizia vecchia", "language": "English",
                 "domain": "coindesk.com", "url": "http://x/1",
                 "seendate": dentro}]

    with patch.object(bf, "_interroga", return_value=articoli):
        assert bf.sonda_finestre() is True


def test_la_sonda_boccia_il_silenzio():
    """Nessuna risposta (rate limit) non è un via libera."""
    import backfill_gdelt as bf

    with patch.object(bf, "_interroga", return_value=[]):
        assert bf.sonda_finestre() is False
