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

    def test_gli_eventi_societari_veri_non_vengono_buttati(self):
        """
        Titoli VERI segnati da cancellare dalla mia prima versione della
        regola, il 18 agosto 2026. Sono cause, sentenze, cessioni e
        violazioni di dati: gli eventi che muovono un titolo.

        CONTESTO non li riconosce perche' e' un vocabolario nato per separare
        la finanza dalla cronaca, non per riconoscere un evento societario.
        Applicarlo ai nomi di societa' su questo percorso costava 190 righe su
        453 a META e 34 su 45 a SHEL.L.
        """
        for termine, ticker, titolo in [
            ("Meta", "META", "US states seek $200 billion penalty in blockbuster Meta lawsuit"),
            ("Meta", "META", "How New Mexico $567 Million Ruling Could Change Meta"),
            ("Meta", "META", "Jury selection begins in Meta youth harms trial in federal court"),
            ("Meta", "META", "Manus founders to return to China as Meta unwinds buyout deal"),
            ("Shell", "SHEL.L", "Shell to sell BG Cyprus and Aphrodite gas stake to MOL Group"),
            ("Shell", "SHEL.L", "Shell Sells European Onshore Renewables Portfolio to TotalEnergies"),
            ("Shell", "SHEL.L", "South Africa top court blocks Shell offshore oil exploration"),
            ("Apple", "AAPL", "Apple now has 65% of global premium smartphone market: report"),
        ]:
            assert pertinente(ticker, termine, titolo), titolo

    def test_le_monete_ambigue_tengono_la_regola(self):
        """
        Su queste il conto dava ragione al filtro: NEAR 299 righe su 302,
        Avalanche 27 su 32, Cosmos 21 su 25.
        """
        assert not pertinente("AVAX-USD", "Avalanche",
                              "Avalanche warning issued for the Alps this weekend")
        assert not pertinente("ATOM-USD", "Cosmos",
                              "Cosmos DB outage hits Azure customers")

    def test_quello_che_torna_dentro_va_detto(self):
        """
        Togliendo la regola ai nomi di societa' rientra anche il rumore che
        prendeva. Non e' risolto, e' tornato com'era: serve un meccanismo che
        sappia cos'e' una societa'.
        """
        assert pertinente("SHEL.L", "Shell", "The Ghost in the Shell Episode #06 Anime Review")

    def test_una_sigla_latina_dentro_un_testo_cinese_viene_riconosciuta(self):
        """
        `\\b` e' Unicode, e un ideogramma e' un carattere di parola: in
        "AMD公佈2026年第2季財務報告" il confine dopo "AMD" non esiste e la
        ricerca falliva. Erano il bilancio trimestrale di AMD in cinese e
        l'acquisizione di Taalas, segnati da cancellare il 18 agosto 2026.
        """
        for titolo in ["AMD公佈2026年第2季財務報告",
                       "AMD收购Taalas：将AI模型直接硬编码进芯片"]:
            assert pertinente("AMD", "AMD", titolo), titolo

    def test_il_confine_di_parola_resta_severo_sulle_lettere_latine(self):
        """La ragione per cui il confine esisteva: "beni" non contiene "eni"."""
        assert not pertinente("ENI.MI", "Eni", "Il governo tutela i beni culturali")
        assert pertinente("ENI.MI", "Eni", "Eni shares rise on Libya deal")

    def test_le_due_sigle_grandi_col_contesto(self):
        """
        Le chiavi vengono dal NOME: per ETH-USD escono 'ethereum' e
        'eth-usd', mai 'eth'. Chi scriveva solo la sigla non veniva
        riconosciuto, come i file grezzi fanno gia' da SIGLE_AMMESSE.
        """
        assert pertinente("ETH-USD", "Ethereum",
                          "Lido Staked ETH (stETH) Trading Up 2% Over Last Week")
        assert pertinente("BTC-USD", "Bitcoin",
                          "BTC breaks $60,000 as ETF inflows surge")

    def test_la_sigla_da_sola_non_basta_senza_contesto(self):
        """
        Senza contesto "BTC Development (NASDAQ:BDCIW)" e' un'altra azienda,
        ed e' la condizione con cui le due sigle sono state ammesse.
        """
        assert not pertinente("BTC-USD", "Bitcoin", "BTC Development names new CFO")

    def test_il_nome_col_simbolo_accanto_basta(self):
        """
        Titoli veri segnati da cancellare il 18 agosto 2026 perche' CONTESTO
        non conosce "volume of". La sigla accanto al nome li rende
        inequivocabili: nessun articolo di astronomia scrive "Stellar (XLM)".
        """
        assert pertinente("XLM-USD", "Stellar",
                          "Stellar ( XLM ) Reaches 24 - Hour Volume of $459 . 41 Million")
        assert pertinente("AVAX-USD", "Avalanche",
                          "Avalanche ( AVAX ) developer activity climbs")

    def test_la_sigla_da_sola_non_basta_sulle_monete_ambigue(self):
        """Servono tutti e due: il nome E la sigla."""
        assert not pertinente("AVAX-USD", "Avalanche",
                              "Five climbers killed in Broad Peak avalanche")
        assert not pertinente("ATOM-USD", "Cosmos",
                              "Painting the Cosmos earns scholarly praise")

    def test_le_altre_sigle_restano_fuori(self):
        """
        Misurato ad agosto 2026: DOGE e' il Department of Government
        Efficiency, OP l'operazione chirurgica in tedesco, SOL il sole in
        spagnolo, MU un podcast di ufologia. Solo BTC ed ETH sono ammesse.
        """
        assert not pertinente("SOL-USD", "Solana", "SOL brilla en el cielo de agosto")
        assert not pertinente("DOGE-USD", "Dogecoin", "DOGE cuts 400 federal jobs")

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
        for titolo in ["Boeing wins order from Emirates",
                       "Nvidia unveils new Blackwell chip at GTC"]:
            assert pertinente("BA" if "Boeing" in titolo else "NVDA",
                              "Boeing" if "Boeing" in titolo else "Nvidia",
                              titolo), titolo

        from gdelt_grezzo import CONTESTO
        assert not CONTESTO.search("Boeing wins order from Emirates"), (
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
