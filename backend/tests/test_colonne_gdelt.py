"""
Test della misura sulle colonne GDELT che oggi non leggiamo.

Questo strumento serve a decidere se moltiplicare il volume dell'archivio, e
una decisione del genere si prende su un numero. Se il numero è sbagliato la
decisione è sbagliata, e nessuno se ne accorge: non c'è un errore che salta
fuori, c'è solo un archivio che da un certo giorno in poi è pieno di articoli
che nominano Bitcoin di sfuggita.

Quindi qui si protegge lo spacchettamento dei campi, che è il punto in cui è
facile sbagliare in silenzio.
"""
import gdelt_grezzo as gg


# ── Spacchettamento dei campi a lista ─────────────────────────────────────
def test_i_nomi_propri_perdono_la_posizione():
    """
    ALLNAMES scrive "Nome,4523". Tenendo la posizione, il confronto a parola
    intera fallirebbe su ogni voce e la misura direbbe zero.
    """
    campo = "Bitcoin,142;Elon Musk,891;New York Stock Exchange,1204;"
    assert gg._voci(campo, con_posizione=True) == [
        "Bitcoin", "Elon Musk", "New York Stock Exchange"]


def test_i_temi_non_hanno_posizione_da_togliere():
    campo = "ECON_STOCKMARKET;WB_1234_FINANCE;EPU_POLICY;"
    assert gg._voci(campo) == ["ECON_STOCKMARKET", "WB_1234_FINANCE",
                               "EPU_POLICY"]


def test_il_punto_e_virgola_finale_non_produce_una_voce_vuota():
    """GDELT chiude sempre con ';'. Una voce vuota falserebbe i conteggi."""
    assert gg._voci("uno;due;") == ["uno", "due"]
    assert gg._voci("") == []
    assert gg._voci(None) == []


def test_una_voce_senza_virgola_resta_intera():
    """Non tutte le voci di ALLNAMES portano la posizione."""
    assert gg._voci("Bitcoin;Ethereum", con_posizione=True) == ["Bitcoin",
                                                               "Ethereum"]


# ── Il confronto dentro le liste ──────────────────────────────────────────
def test_il_confronto_e_a_parola_intera():
    """
    Senza confini di parola "XRP" prenderebbe "XRPL" e i conteggi
    sembrerebbero migliori di quello che sono.
    """
    assert gg._compare_in(["XRP Ledger Foundation"], "XRP") is True
    assert gg._compare_in(["XRPL Labs"], "XRP") is False


def test_le_sigle_rispettano_le_maiuscole_anche_qui():
    """
    È la stessa regola del titolo: la moneta si chiama NEAR, la preposizione
    inglese si scrive near. Se le due misure divergessero, la decisione si
    prenderebbe su un numero che la raccolta non riprodurrà mai.
    """
    assert gg._compare_in(["NEAR Protocol"], "NEAR") is True
    assert gg._compare_in(["the near future"], "NEAR") is False
    assert gg._compare_in(["bitcoin foundation"], "Bitcoin") is True


# ── La sigla ricavata dal ticker ──────────────────────────────────────────
def test_la_sigla_perde_il_suffisso_del_mercato():
    """
    Cercare "BTC-USD" o "RACE.MI" dentro un titolo non troverebbe mai niente:
    nei titoli si scrive la sigla nuda.
    """
    assert gg.sigla_di("BTC-USD") == "BTC"
    assert gg.sigla_di("RACE.MI") == "RACE"
    assert gg.sigla_di("SHEL.L") == "SHEL"
    assert gg.sigla_di("NVDA") == "NVDA"


def test_la_sigla_di_un_ticker_vuoto_non_esplode():
    assert gg.sigla_di("") == ""
    assert gg.sigla_di(None) == ""
