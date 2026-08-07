"""
Test della raccolta dai file grezzi di GDELT.

Due cose vanno protette qui dentro più delle altre.

La prima è che il filtro sui termini ambigui sia lo STESSO della misura. Sono
scritti in due punti diversi (`conta_pertinenti` misura, `_quale_ticker`
raccoglie) e se divergono si scopre solo un mese dopo, guardando un archivio
sporco di valanghe e raccolti di mele.

La seconda è la conversione del tono. GDELT lavora su una scala diversa dalla
nostra, e sbagliare quel passaggio non produce nessun errore: produce
sentiment plausibili e sbagliati.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import gdelt_grezzo as gg
import ingest_grezzo as ing
from gdelt_source import TERMINE_QUERY


def _riga(titolo, dominio="coindesk.com", tono=2.0, data="20260806180000",
          lingua_src=None):
    c = [""] * 27
    c[gg.COL_DATA] = data
    c[gg.COL_DOMINIO] = dominio
    c[gg.COL_URL] = f"http://{dominio}/articolo"
    c[gg.COL_TONO] = f"{tono},3.1,1.2,4.3,20,10,300"
    if lingua_src:
        c[gg.COL_TRADUZIONE] = f"srclc:{lingua_src};eng:Moses"
    if titolo:
        c[gg.COL_EXTRA] = f"<PAGE_TITLE>{titolo}</PAGE_TITLE>"
    return c


# ── La conversione del tono ───────────────────────────────────────────────
def test_il_tono_finisce_nella_nostra_scala():
    """
    GDELT dichiara -100..+100, noi usiamo -1..+1. Senza conversione un tono di
    +3 verrebbe salvato come +3, cioè tre volte il massimo della nostra scala,
    e trascinerebbe da solo qualunque media giornaliera.
    """
    assert ing._tono_nostro(2.0) == 0.2
    assert ing._tono_nostro(-1.98) == -0.198
    assert ing._tono_nostro(0.0) == 0.0


def test_i_toni_estremi_vengono_tagliati():
    """Anche un tono fuori scala non deve uscire dall'intervallo nostro."""
    assert ing._tono_nostro(85.0) == 1.0
    assert ing._tono_nostro(-85.0) == -1.0


def test_tono_mancante_vale_zero_non_esplode():
    assert ing._tono_nostro(None) == 0.0


def test_la_conversione_conserva_l_ordine():
    """
    È l'unica proprietà che serve davvero: due articoli devono restare nello
    stesso ordine relativo, perché è così che si costruiscono medie e
    classifiche.
    """
    toni = [-8.0, -1.5, 0.0, 0.3, 4.0]
    convertiti = [ing._tono_nostro(t) for t in toni]
    assert convertiti == sorted(convertiti)


# ── Il filtro deve combaciare con quello della misura ─────────────────────
def test_raccolta_e_misura_usano_lo_stesso_filtro():
    """
    Il caso che si scopre tardi e male: se i due filtri divergono, la misura
    dice "ottimo affare" e la raccolta porta a casa un'altra cosa.
    """
    titoli = [
        "Bitcoin hits new record high",
        "Avalanche kills three skiers in the Alps",
        "Avalanche price jumps as AVAX token rallies",
        "Stocks near record highs as traders wait",
        "NEAR crypto surges on protocol upgrade",
        "Apple harvest hit by drought in Trentino",
        "Apple shares rise after earnings beat",
    ]
    righe = [_riga(t) for t in titoli]

    dalla_misura, _, _ = gg.conta_pertinenti(righe, TERMINE_QUERY)
    dalla_raccolta = {}
    for t in titoli:
        for tk in ing._quali_ticker(t, TERMINE_QUERY):
            dalla_raccolta[tk] = dalla_raccolta.get(tk, 0) + 1

    assert dict(dalla_misura) == dalla_raccolta, (
        "misura e raccolta contano cose diverse: uno dei due filtri è stato "
        "cambiato senza l'altro")


def test_la_raccolta_scarta_i_falsi_positivi():
    assert ing._quali_ticker("Avalanche kills three skiers", TERMINE_QUERY) == []
    assert ing._quali_ticker("Stocks near record highs today", TERMINE_QUERY) == []
    assert ing._quali_ticker("Amazon rainforest fires spread", TERMINE_QUERY) == []


def test_la_raccolta_tiene_quelli_veri():
    assert ing._quali_ticker("Bitcoin hits new high", TERMINE_QUERY) == ["BTC-USD"]
    assert ing._quali_ticker("Avalanche token price jumps", TERMINE_QUERY) == ["AVAX-USD"]


# ── Il contesto obbligatorio per le azioni ────────────────────────────────
def test_un_titolo_di_prodotto_non_entra_come_azione():
    """
    Il caso che il 7 agosto 2026 valeva 816 righe su 1.541: "Google" e
    "Microsoft" non sono parole ambigue, ma compaiono ogni giorno in centinaia
    di titoli che non parlano del titolo azionario.
    """
    for t in ("Google Maps adds a new lane guidance feature",
              "Microsoft Teams down for thousands of users",
              "Tesla driver rescued after crash on the A4",
              "Nvidia releases a new driver for the RTX line"):
        assert ing._quali_ticker(t, TERMINE_QUERY) == [], t


def test_un_titolo_di_mercato_entra_come_azione():
    assert ing._quali_ticker("Google shares rise after earnings beat",
                             TERMINE_QUERY) == ["GOOGL"]
    assert ing._quali_ticker("Microsoft stock slides as investors sell",
                             TERMINE_QUERY) == ["MSFT"]
    assert ing._quali_ticker("Eni sale in borsa dopo i ricavi del trimestre",
                             TERMINE_QUERY) == ["ENI.MI"]


def test_le_monete_non_hanno_bisogno_del_contesto():
    """
    E non è una svista: il nome della moneta è già un termine di mercato.
    Chiedere il contesto anche a Bitcoin taglierebbe metà della copertura
    cripto senza togliere un solo falso positivo.
    """
    assert ing._quali_ticker("Bitcoin crolla sotto i 90.000 dollari",
                             TERMINE_QUERY) == ["BTC-USD"]
    assert ing._quali_ticker("Ethereum completa l'aggiornamento Pectra",
                             TERMINE_QUERY) == ["ETH-USD"]


def test_le_monete_dal_nome_comune_restano_filtrate():
    """
    Solana Beach e Aptos sono località della California, Cardano è un cognome
    italiano, Shiba è una razza di cane. Aggiunti agli ambigui il 7 agosto.
    """
    assert ing._quali_ticker("Solana Beach closes its pier for repairs",
                             TERMINE_QUERY) == []
    assert ing._quali_ticker("Gerolamo Cardano e la nascita della probabilità",
                             TERMINE_QUERY) == []
    assert ing._quali_ticker("Shiba wins best in show at Westminster",
                             TERMINE_QUERY) == []
    assert ing._quali_ticker("Solana price jumps as traders pile in",
                             TERMINE_QUERY) == ["SOL-USD"]


# ── Un articolo, più titoli ───────────────────────────────────────────────
def test_un_articolo_conta_per_ogni_asset_che_nomina():
    """
    Il difetto trovato il 7 agosto 2026: `_quale_ticker` si fermava al primo
    che combaciava e nel dizionario le azioni vengono prima delle monete,
    quindi le cripto perdevano ogni articolo che le nominava insieme a
    un'azienda. Un modo silenzioso di sottostimare proprio il prodotto.
    """
    trovati = ing._quali_ticker(
        "Microsoft adds Bitcoin to its treasury, shares rise", TERMINE_QUERY)
    assert set(trovati) == {"MSFT", "BTC-USD"}


def test_il_conteggio_per_lingua_conta_articoli_non_assegnazioni():
    """
    Se contasse le assegnazioni, un pezzo che nomina tre monete varrebbe tre
    articoli inglesi e la ripartizione per lingua direbbe una bugia.
    """
    righe = [_riga("Bitcoin, Ethereum and Solana price rally together")]
    per_ticker, per_lingua, _ = gg.conta_pertinenti(righe, TERMINE_QUERY)
    assert sum(per_ticker.values()) == 3
    assert sum(per_lingua.values()) == 1


def test_la_raccolta_salva_lo_stesso_articolo_sotto_entrambi_i_titoli():
    righe = [_riga("Microsoft adds Bitcoin to its treasury, shares rise")]
    salvati = {}

    def finto_save(ticker, news):
        salvati[ticker] = news
        return len(news)

    with patch.object(ing, "leggi_gkg", return_value=righe), \
         patch.object(ing, "save_news", side_effect=finto_save):
        ing.raccogli(ore=1, limite_minuti=1, solo_inglese=True)

    assert set(salvati) == {"MSFT", "BTC-USD"}
    assert salvati["MSFT"][0] is not salvati["BTC-USD"][0], (
        "le due righe condividono lo stesso oggetto: una modifica fatta da "
        "save_news sulla prima si ritroverebbe nella seconda")


# ── Le date ───────────────────────────────────────────────────────────────
def test_legge_la_data_di_pubblicazione():
    r = _riga("Bitcoin sale", data="20260806183000")
    assert ing._data(r).startswith("2026-08-06T18:30:00")


def test_una_data_rotta_diventa_adesso_invece_di_far_saltare_la_riga():
    """
    Una riga senza data cadrebbe fuori da ogni finestra temporale, cioè
    sarebbe come non averla raccolta. Meglio un'ora imprecisa che un buco.
    """
    r = _riga("Bitcoin sale", data="non-una-data")
    quando = datetime.fromisoformat(ing._data(r))
    assert abs((datetime.now(timezone.utc) - quando).total_seconds()) < 10


# ── I timestamp da scaricare ──────────────────────────────────────────────
def test_i_quarti_dora_sono_allineati_e_indietro_nel_tempo():
    """
    GDELT pubblica ai minuti 00, 15, 30, 45. Chiedere un file a un minuto
    diverso dà 404, e chiedere quello dell'istante corrente pure, perché non
    è ancora stato pubblicato.
    """
    stamp = ing.quarti_dora_indietro(2)
    assert len(stamp) == 8
    for s in stamp:
        assert int(s[10:12]) in (0, 15, 30, 45), f"{s} non è allineato al quarto d'ora"

    quando = datetime.strptime(stamp[0], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    assert quando < datetime.now(timezone.utc), "il primo file è nel futuro"


def test_i_file_si_scaricano_dal_piu_recente():
    """
    Se il tempo finisce si perde la coda. Partendo dai vecchi si perderebbero
    proprio le notizie di oggi, che sono le uniche che l'app mostra.
    """
    stamp = ing.quarti_dora_indietro(3)
    assert stamp == sorted(stamp, reverse=True)


# ── Il salvataggio ────────────────────────────────────────────────────────
def test_le_righe_salvate_sono_marcate_gdelt():
    """
    Senza questo marchio Groq le ri-classificherebbe usando solo il titolo,
    sostituendo un punteggio calcolato sul testo integrale con uno peggiore.
    """
    righe = [_riga("Bitcoin hits new record high", tono=3.0)]
    salvati = {}

    def finto_save(ticker, news):
        salvati[ticker] = news
        return len(news)

    with patch.object(ing, "leggi_gkg", return_value=righe), \
         patch.object(ing, "save_news", side_effect=finto_save):
        ing.raccogli(ore=1, limite_minuti=1, solo_inglese=True)

    assert "BTC-USD" in salvati
    riga = salvati["BTC-USD"][0]
    assert riga["score_source"] == "gdelt"
    assert riga["sentiment"] == 0.3
    assert riga["source"].startswith("GDELT · ")


def test_un_file_mancante_non_ferma_la_raccolta():
    """
    Il 404 è normale: il feed tradotto viaggia in ritardo rispetto
    all'inglese, quindi mancano regolarmente i quarti d'ora più recenti.
    """
    def a_volte_rotto(url):
        if "translation" in url:
            raise RuntimeError("404")
        return [_riga("Bitcoin hits new record high")]

    with patch.object(ing, "leggi_gkg", side_effect=a_volte_rotto), \
         patch.object(ing, "save_news", return_value=1):
        salvate = ing.raccogli(ore=1, limite_minuti=1)

    assert salvate > 0, "un feed rotto ha fermato anche l'altro"
