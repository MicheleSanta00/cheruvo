"""
test_contesto_cripto.py — Il vocabolario di CONTESTO sulle monete.

CONTESTO e' nato leggendo notizie azionarie, e il 18 agosto 2026 si e' visto
che non conosce la lingua delle monete. Su SOL-USD proponeva di cancellare 34
righe su 127 e, delle prime trenta, ne passava ZERO: erano ETP, staking, RWA,
esposizioni di Goldman Sachs e Bank of America, il report trimestrale della
chain.

I titoli qui sotto sono quelli veri dell'archivio in produzione. Servono a due
cose in tensione fra loro: che le notizie cripto vere entrino, e che la
spazzatura che il filtro gia' fermava resti fuori. Allargare un filtro finche'
non taglia piu' niente e' facile, ed e' un altro modo di romperlo.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("DATABASE_URL", "postgresql://fake:fake@localhost/fake")

import pytest

from gdelt_grezzo import CONTESTO


VERE = [
    "Morgan Stanley Launches Ether and Solana ETPs with Staking",
    "Bank of America discloses exposure to Bitcoin , XRP , Ether , Solana",
    "Goldman Sachs Dumps XRP and Solana , Cuts Ethereum Exposure by 70",
    "Is Solana ( SOL ) a Buy Right Now ?",
    "Solana RWA Ecosystem Leads All Chains With 300 , 000+ Holders",
    "Solana News : Solana Hits $5 . 77B Tokenized Asset Volume in Q2 2026",
    "Solana Q1 2026 Report : Chain GDP Hits $342M , RWAs Top $2B",
    "Krypto News zu SOLANA und dem Burn - Votum , das 18,9 Millionen SOL",
    "Solana Prognose vor der Abstimmung uber neue SOL Burns im August",
    "Solana news : MoneyGram takes role validator role amid stablecoin",
    "SurancePlus to Launch Tokenized Reinsurance RWA Securities on Solana",
    "Best Solana meme coins to watch as July rally builds",
]


@pytest.mark.parametrize("titolo", VERE)
def test_le_notizie_cripto_vere_passano(titolo):
    assert CONTESTO.search(titolo), titolo


# Quello che il filtro gia' fermava e deve continuare a fermare.
SPAZZATURA = [
    "El Centro de Mayores de La Solana fomenta el ejercicio , la memoria",
    "Senior Job Captain - Solana Beach , CA , US | Jobs",
    "2026 WSOP - S ( World Series of Poker Solana Showdown )",
    "Avalanche face a tough situation amid Cale Makar extension",
    "Five more bodies of climbers retrieved from Broad Peak avalanche",
    "Pakistan : Mortal remains of Nirmal Purja , 4 climbers airlifted",
    "Cosmos DB outage hits Azure customers",
    "Milwaukee fire near 18th and Mineral , house uninhabitable",
    "Stellar AfricaGold Announces Drilling Results",
    "Firefighters tackle New Forest heath fire near car park",
    "Woman , 60 , dies after falling near Dunnet Head as body recovered",
    "Law student charged over intercepted bomb near Border appears in court",
]


@pytest.mark.parametrize("titolo", SPAZZATURA)
def test_la_spazzatura_resta_fuori(titolo):
    assert not CONTESTO.search(titolo), titolo


def test_i_buchi_che_restano_sono_dichiarati():
    """
    Due titoli veri che non passano, e non e' una svista: non contengono UNA
    parola di mercato. Un filtro che prendesse anche questi prenderebbe tutto.

    Se un giorno passassero, questo test si accende e va riletto: potrebbe
    essere un miglioramento, o potrebbe voler dire che il vocabolario e'
    diventato cosi' largo da non filtrare piu' niente.
    """
    for titolo in ["Where Will Solana ( SOL ) Be in 5 Years ?",
                   "Solana Institute urges CLARITY Act developer protections"]:
        assert not CONTESTO.search(titolo), titolo


def test_i_plurali_e_le_derivate_non_sfuggono_piu():
    """
    Tre casi di confine di parola che facevano perdere notizie vere:
    "tokenized" non e' "token", "meme coins" non e' "coin", e "Bitcoin" non
    contiene "coin" perche' il confine cade prima di "Bit".
    """
    assert CONTESTO.search("Tokenized Asset Volume hits a record")
    assert CONTESTO.search("Best meme coins to watch this July")
    assert CONTESTO.search("Bank of America discloses Bitcoin holdings")


def test_il_movimento_di_prezzo_e_le_previsioni():
    """
    Secondo giro. "Cardano Crashes To 5-Year Lows" non passava per un motivo
    banale: c'era "markets" al plurale e non "market" al singolare.
    """
    for titolo in [
        "Cardano Crashes To 5 - Year Lows As Hoskinson Warning Sparks Market Fear",
        "Microsoft Copilot Predicts $0 . 65 Cardano by 2027 . Whales Are Also Buying",
        "So lohnend waere eine Investition in Solana von vor 5 Jahren gewesen",
        "Cardano hits all - time low amid selloff",
    ]:
        assert CONTESTO.search(titolo), titolo


def test_market_al_singolare_resta_fuori():
    """
    Il primo tentativo aveva aggiunto "market" al singolare, e l'ha fermato
    `test_ingest_grezzo::test_market_da_solo_non_e_un_contesto_finanziario`,
    che viene dall'8 agosto 2026: "New York Shoe Market Week 2026: Fashion
    Styles Spur Optimism" era archiviata come notizia su Optimism con +0,20.

    Il titolo di Cardano passa lo stesso, perche' ha "Crashes To" e
    "5-Year Lows". Non serviva allargare fin li'.
    """
    assert not CONTESTO.search("New York Shoe Market Week 2026 : Fashion Styles Spur Optimism")
    assert not CONTESTO.search("Farmers market brings new optimism to the village")
    assert CONTESTO.search("Cardano markets stay flat"), "il plurale c'era gia'"


NON_FINANZIARI = [
    # "crash" e "lows" da soli NON sono nel vocabolario: li' fuori ci sono
    # gli incidenti stradali e i bollettini meteo, due delle famiglie di
    # rumore trovate il 18 agosto 2026.
    "Motorcyclist critically injured in Midwest City crash near Air Depot",
    "Reno and South Lake Tahoe set for near - average highs with sun and clouds",
    "Astronomers Unfurl Record 5 . 6 Trillion Pixel Map Of The Entire Cosmos",
    "No Man Sky Turns 10 With Record Players , Dual Awards , and COSMOS",
    "Jac Caglianone joins exclusive company with stellar performance",
    "Stellar stream discovery beyond Milky Way helps map dark matter",
    "Europe readies for total solar eclipse",
    "Cosmos DB outage hits Azure customers",
]


@pytest.mark.parametrize("titolo", NON_FINANZIARI)
def test_le_parole_di_prezzo_non_hanno_aperto_la_porta(titolo):
    assert not CONTESTO.search(titolo), titolo


def test_le_azioni_non_sono_state_toccate():
    """Le aggiunte sono additive: quello che passava prima passa ancora."""
    for titolo in ["Nvidia shares rise after earnings beat",
                   "SAP meldet Verlust im zweiten Quartal",
                   "Ferrari beats quarterly expectations",
                   "AMD raises $4.75bn in its biggest ever bond offering"]:
        assert CONTESTO.search(titolo), titolo
