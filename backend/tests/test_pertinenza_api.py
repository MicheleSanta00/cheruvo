"""
test_pertinenza_api.py — Le difese nel percorso dell'API.

COSA E' SUCCESSO

Ad agosto 2026 sono state costruite due difese contro il rumore: il confronto
che rispetta le maiuscole per le sigle che sono anche parole comuni (NEAR, GE,
XRP) e il contesto finanziario obbligatorio per i nomi ambigui. Sono finite in
`gdelt_grezzo.py`, cioe' nel percorso dei file grezzi.

L'altro percorso, quello dell'API in `gdelt_source._e_pertinente`, non ne ha
avuta nessuna. Faceva `titolo.lower()` e cercava il nome, e da li' passano
`quick_fetch` (update_news, quattro volte al giorno, piu' il bottone di
scarico) e `backfill_gdelt`.

Il 18 agosto 2026 NEAR-USD aveva 43 notizie in 48 ore, piu' di Ethereum, e
nessuna parlava della moneta. I titoli qui sotto sono quelli veri, presi
dall'archivio in produzione.

La cosa da proteggere non e' il singolo filtro: e' che i due percorsi non
possano piu' divergere.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("DATABASE_URL", "postgresql://fake:fake@localhost/fake")

import re

import pytest

from gdelt_source import _e_pertinente, _parole_chiave


def pertinente(ticker: str, termine: str, titolo: str) -> bool:
    return _e_pertinente(titolo, _parole_chiave(ticker, termine), ticker, termine)


# ── I titoli veri che erano entrati ───────────────────────────────────────
SPAZZATURA_NEAR = [
    "Blondo Street construction mix - up causes traffic backups near Waterloo",
    "Milwaukee fire near 18th and Mineral , house uninhabitable",
    "Six Thai workers injured by unexploded ordnance near Metula",
    "Mother drowns saving son in Des Plaines River near Libertyville forest preserve",
    "Russia Builds Drone Bases Near NATO , Putting Poland Within Reach",
    "Bihar tiger attack : Farmer killed near Valmiki reserve , mob assaults forest staff",
    "Body found in water near Lawyers Head in Dunedin",
    "Firefighters tackle New Forest heath fire near car park",
    "Measures in place to protect historic oak tree near Grantham",
    "Archaeologists hunt for Spanish shipwreck near Winyah Bay",
]


@pytest.mark.parametrize("titolo", SPAZZATURA_NEAR)
def test_la_cronaca_non_entra_piu_come_moneta(titolo):
    assert not pertinente("NEAR-USD", "NEAR", titolo)


# Questi hanno il contesto finanziario e sarebbero passati anche con la
# regola del contesto da sola: li ferma SOLO il rispetto delle maiuscole.
SPAZZATURA_NEAR_CON_CONTESTO = [
    "US stocks hang near their record heights",
    "US Dollar Hovers Near Multi - Month Lows as Fed Rate Hike Bets Ease",
    "Gold Prices Hold Near $4 , 400 as Fed Rate Hike Bets Fade",
    "HDFC Bank shares slip under selling pressure , near 52 - week low",
    "Indian lender dollar bond sales hit record near $9 billion",
    "Copper squeeze builds with spreads surging and price near record",
]


@pytest.mark.parametrize("titolo", SPAZZATURA_NEAR_CON_CONTESTO)
def test_il_contesto_da_solo_non_basterebbe(titolo):
    """
    Il caso descritto nel commento accanto a MAIUSCOLI: "Stocks near record
    highs as traders wait" contiene parole di mercato, quindi supera il filtro
    di contesto pur non parlando affatto della moneta.
    """
    assert not pertinente("NEAR-USD", "NEAR", titolo)


def test_la_moneta_vera_passa_ancora():
    """Una difesa che scarta tutto non e' una difesa, e' un rubinetto chiuso."""
    for titolo in [
        "NEAR Protocol price rallies as investors buy the token",
        "NEAR jumps 12% as crypto market recovers",
    ]:
        assert pertinente("NEAR-USD", "NEAR", titolo), titolo


def test_le_altre_monete_ambigue():
    assert not pertinente("XLM-USD", "Stellar",
                          "Stellar AfricaGold Announces Drilling Results")
    assert pertinente("XLM-USD", "Stellar",
                      "Stellar price jumps as XLM investors move in")
    assert not pertinente("AVAX-USD", "Avalanche",
                          "Avalanche warning issued for the Alps this weekend")


def test_bitcoin_non_viene_rotto_dalla_maiuscola_di_near():
    """
    "Bitcoin Near $60K" contiene "Near" ma il ticker qui e' BTC: la regola
    delle maiuscole si applica al TERMINE di questo titolo, non al titolo.
    """
    assert pertinente("BTC-USD", "Bitcoin",
                      "Bitcoin Near $60K : Why Liquidity Is Drawing Trader Focus")


# ── Quello che questa correzione NON risolve ──────────────────────────────
def test_solana_biofuels_passa_ancora_e_va_detto():
    """
    Il contesto finanziario non distingue una societa' indiana di
    biocarburanti che dichiara una perdita netta dalla moneta omonima: e'
    davvero un articolo finanziario, su un'altra azienda.

    Serve un meccanismo diverso (elenco di esclusioni, o disambiguazione per
    entita'), non questo. Il test esiste per non far credere che sia risolto:
    se un giorno lo si risolve, questo test si accende e si aggiorna.
    """
    assert pertinente("SOL-USD", "Solana",
                      "Solana Biofuels reports standalone net loss")


# ── I due percorsi non devono piu' divergere ──────────────────────────────
class TestNessunaDivergenza:

    def test_sui_nomi_ambigui_i_due_percorsi_dicono_la_stessa_cosa(self):
        """
        Gli stessi titoli, le stesse costanti, lo stesso verdetto. E' la
        divergenza fra i due percorsi ad aver fatto entrare le 52 righe, non
        la debolezza di uno dei due.

        Il confronto vale sui nomi AMBIGUI, che sono la classe dove i due
        percorsi devono coincidere. Sui nomi netti divergono di proposito,
        e il perche' e' nel test qui sotto.
        """
        from gdelt_grezzo import CONTESTO, MAIUSCOLI, serve_contesto

        def come_i_grezzi(ticker, termine, titolo):
            rx = re.compile(r"\b" + re.escape(termine) + r"\b",
                            0 if termine in MAIUSCOLI else re.I)
            if not rx.search(titolo):
                return False
            if serve_contesto(ticker, termine):
                return bool(CONTESTO.search(titolo))
            return True

        casi = [("NEAR-USD", "NEAR", t) for t in
                SPAZZATURA_NEAR + SPAZZATURA_NEAR_CON_CONTESTO]
        casi += [
            ("NEAR-USD", "NEAR", "NEAR Protocol price rallies as investors buy"),
            ("XLM-USD", "Stellar", "Stellar AfricaGold Announces Drilling Results"),
            ("XLM-USD", "Stellar", "Stellar price jumps as XLM investors move in"),
            ("AVAX-USD", "Avalanche", "Avalanche warning issued for the Alps"),
            ("BTC-USD", "Bitcoin", "Bitcoin rallies past $60,000 as traders return"),
        ]
        for ticker, termine, titolo in casi:
            assert pertinente(ticker, termine, titolo) == \
                   come_i_grezzi(ticker, termine, titolo), \
                   f"i due percorsi non sono d'accordo su: {titolo}"

    def test_sui_nomi_netti_la_divergenza_e_voluta_e_documentata(self):
        """
        CONTESTO e' un vocabolario tarato sul firehose. Misurato il 18 agosto
        2026, su questo percorso scarterebbe notizie societarie vere:

            Nvidia hits record high as AI demand surges
            Boeing wins order from Emirates
            Eni firma un accordo in Libia

        Quindi qui NON si applica ai nomi netti, e finche' non c'e' il conto
        di `bonifica_pertinenza.py` resta cosi'. Questo test protegge la
        scelta: se un giorno la si cambia, la si cambia sapendolo.
        """
        for titolo in ["Nvidia hits record high as AI demand surges",
                       "Nvidia unveils new Blackwell chip at GTC"]:
            assert pertinente("NVDA", "Nvidia", titolo), titolo

        from gdelt_grezzo import CONTESTO
        assert not CONTESTO.search("Nvidia hits record high as AI demand surges"), (
            "se CONTESTO ha imparato questa frase, la divergenza si e' chiusa "
            "da sola e questo test va riscritto")

    def test_le_costanti_sono_le_stesse_non_ricopiate(self):
        import inspect
        import gdelt_source
        sorgente = inspect.getsource(gdelt_source._e_pertinente)
        assert "from gdelt_grezzo import" in sorgente, (
            "le regole sono state ricopiate invece che importate: possono "
            "tornare a divergere senza che nessun test se ne accorga")
        for nome in ("AMBIGUI", "CONTESTO", "MAIUSCOLI"):
            assert nome in sorgente, nome

    def test_ticker_e_termine_sono_obbligatori(self):
        """
        Con un valore predefinito, un chiamante che se li dimentica perde le
        difese in silenzio. E' esattamente com'e' nata questa storia.
        """
        import inspect
        import gdelt_source
        firma = inspect.signature(gdelt_source._e_pertinente)
        for nome in ("ticker", "termine"):
            assert firma.parameters[nome].default is inspect.Parameter.empty, nome
