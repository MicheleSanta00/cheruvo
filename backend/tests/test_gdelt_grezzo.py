"""
Test del lettore dei file grezzi di GDELT.

Il rischio principale qui non è che il codice si rompa: è che conti troppo.
I file grezzi contengono TUTTO quello che GDELT vede nel mondo, meteo e sport
compresi, e undici dei nostri termini di ricerca sono anche parole comuni.
Senza filtro, "Avalanche kills three skiers" diventerebbe una notizia su AVAX
e il conteggio direbbe che la nuova fonte rende benissimo mentre in realtà
starebbe raccogliendo cronaca di montagna.
"""
import gdelt_grezzo as gg
from gdelt_source import TERMINE_QUERY, e_crypto


CRYPTO = {t: q for t, q in TERMINE_QUERY.items() if e_crypto(t)}
AZIONI = {t: q for t, q in TERMINE_QUERY.items() if not e_crypto(t)}


def _riga(titolo, dominio="esempio.com", tono=0.5, lingua_src=None):
    """Una riga GKG 2.1 finta, con le sue 27 colonne."""
    c = [""] * 27
    c[gg.COL_DATA] = "20260806180000"
    c[gg.COL_DOMINIO] = dominio
    c[gg.COL_URL] = f"http://{dominio}/x"
    c[gg.COL_TONO] = f"{tono},3.1,1.2,4.3,20,10,300"
    if lingua_src:
        c[gg.COL_TRADUZIONE] = f"srclc:{lingua_src};eng:Moses"
    if titolo:
        c[gg.COL_EXTRA] = f"<PAGE_TITLE>{titolo}</PAGE_TITLE>"
    return c


def _trovati(titolo):
    r = [_riga(titolo)]
    c, _, _ = gg.conta_pertinenti(r, CRYPTO)
    a, _, _ = gg.conta_pertinenti(r, AZIONI)
    return dict(c) | dict(a)


# ── Lettura del formato ───────────────────────────────────────────────────
def test_legge_titolo_tono_e_lingua():
    r = _riga("Bitcoin sale ancora", dominio="ilsole24ore.com",
              tono=2.7, lingua_src="ita")
    assert gg.titolo(r) == "Bitcoin sale ancora"
    assert gg.tono(r) == 2.7
    assert gg.lingua(r) == "ita"


def test_una_riga_senza_titolo_non_esplode():
    """Molte righe del GKG non hanno il titolo: vanno saltate, non contate."""
    r = _riga(None)
    assert gg.titolo(r) == ""
    assert _trovati("") == {}


def test_una_riga_troppo_corta_non_esplode():
    """
    Se GDELT cambiasse il numero di colonne, leggere per indice solleverebbe
    IndexError a metà di un file da decine di migliaia di righe.
    """
    corta = ["a", "b", "c"]
    assert gg.titolo(corta) == ""
    assert gg.tono(corta) is None
    assert gg.lingua(corta) == "eng"


def test_senza_info_di_traduzione_la_lingua_e_inglese():
    """Il feed inglese non porta il campo: l'assenza significa inglese."""
    assert gg.lingua(_riga("Bitcoin rallies")) == "eng"


# ── Il filtro contro i falsi positivi ─────────────────────────────────────
def test_scarta_le_parole_comuni_fuori_contesto():
    """
    Il caso che rende inutile la misura se non gestito: undici termini su
    trentuno sono anche parole di uso corrente.
    """
    assert _trovati("Avalanche kills three skiers in the Alps") == {}
    assert _trovati("Apple harvest hit by drought in Trentino") == {}
    assert _trovati("Amazon rainforest fires reach record levels") == {}
    assert _trovati("Stellar performance by the Italian swim team") == {}
    assert _trovati("Shell found on the beach sparks curiosity") == {}
    assert _trovati("Optimism grows ahead of the peace talks") == {}


def test_tiene_le_stesse_parole_quando_il_contesto_e_finanziario():
    assert _trovati("Avalanche price jumps 12% as AVAX token rallies") == {"AVAX-USD": 1}
    assert _trovati("Apple shares hit new high after earnings") == {"AAPL": 1}
    assert _trovati("Optimism token leads layer-2 market gains") == {"OP-USD": 1}


def test_le_sigle_rispettano_le_maiuscole():
    """
    "Stocks near record highs as traders wait" contiene due parole di contesto
    finanziario, quindi il filtro sul contesto da solo lo lascerebbe passare.
    L'unica cosa che separa la moneta dalla preposizione sono le maiuscole.
    """
    assert _trovati("Stocks near record highs as traders wait") == {}
    assert _trovati("NEAR crypto surges on protocol upgrade") == {"NEAR-USD": 1}


def test_il_contesto_funziona_anche_in_italiano():
    """
    Il feed tradotto è metà del valore dell'operazione: se le parole di
    contesto fossero solo inglesi, tutta la stampa italiana verrebbe scartata
    proprio mentre si va a cercarla.
    """
    assert _trovati("Bitcoin torna sopra i 100mila dollari in borsa") == {"BTC-USD": 1}
    assert _trovati("Enel, l'azione sale dopo i conti trimestrali") == {"ENEL.MI": 1}


def test_i_termini_non_ambigui_non_chiedono_contesto():
    """Bitcoin non ha omonimi: pretendere contesto perderebbe notizie vere."""
    assert _trovati("Bitcoin hits new record") == {"BTC-USD": 1}
    assert _trovati("Ethereum devs delay the upgrade again") == {"ETH-USD": 1}


def test_la_regola_del_contesto_e_quella_dichiarata():
    """
    Tre casi, tre motivi diversi. Se qualcuno un giorno cambia questa regola
    per alzare i numeri, è qui che il test deve fermarlo.
    """
    # Azienda: nome non ambiguo, ma "Google" compare in mezzo mondo di
    # notizie che col titolo azionario non c'entrano niente.
    assert gg.serve_contesto("GOOGL", "Google") is True
    # Moneta: il nome è già di per sé un termine di mercato.
    assert gg.serve_contesto("BTC-USD", "Bitcoin") is False
    # Moneta con un omonimo nel mondo reale.
    assert gg.serve_contesto("AVAX-USD", "Avalanche") is True


def test_le_azioni_senza_contesto_finanziario_restano_fuori():
    """
    Il difetto misurato il 7 agosto 2026: GOOGL e MSFT facevano 816 righe su
    1.541 raccolte in un giorno, quasi tutte aggiornamenti di prodotto.
    """
    assert _trovati("Google Maps adds lane guidance in Italy") == {}
    assert _trovati("Microsoft Teams down for thousands of users") == {}
    assert _trovati("Google shares rise after earnings beat") == {"GOOGL": 1}


def test_un_articolo_puo_valere_per_due_titoli():
    """
    Prima ci si fermava al primo che combaciava, e le azioni vengono prima
    delle monete nel dizionario: le cripto perdevano ogni articolo condiviso.
    """
    r = [_riga("Microsoft adds Bitcoin to its treasury, shares rise")]
    trovati, _, _ = gg.conta_pertinenti(r, TERMINE_QUERY)
    assert dict(trovati) == {"MSFT": 1, "BTC-USD": 1}


def test_i_confini_di_parola_reggono():
    """Senza confini, XRP prenderebbe XRPL e ogni sigla che lo contiene."""
    assert _trovati("XRPL ledger update ships") == {}


def test_la_versione_ingenua_conta_di_piu():
    """
    Il confronto fra i due conteggi è il numero che dice quanto rumore
    produrrebbe una raccolta senza filtro. Serve nel resoconto, quindi deve
    restare possibile chiederlo.
    """
    righe = [_riga("Avalanche kills three skiers in the Alps")]
    rigoroso, _, _ = gg.conta_pertinenti(righe, CRYPTO, rigoroso=True)
    ingenuo, _, _ = gg.conta_pertinenti(righe, CRYPTO, rigoroso=False)
    assert sum(rigoroso.values()) == 0
    assert sum(ingenuo.values()) == 1


# ── Il resoconto non deve rompersi sui casi limite ────────────────────────
def test_descrivi_formato_regge_un_file_vuoto(capsys):
    gg.descrivi_formato([])
    assert "vuoto" in capsys.readouterr().out
