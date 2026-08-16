"""
Test della misura sullo sbilanciamento del filtro.

Il rischio qui non e' il calcolo, e' il verdetto. Una misura che dice "si'"
quando i dati dicono "non lo so" e' peggio di nessuna misura, perche' porta a
riscaricare un giga di archivio per correggere un problema che non c'e'.
"""
import re
from unittest.mock import patch

import misura_sbilanciamento as ms


# ── Il vocabolario congelato ──────────────────────────────────────────────
def test_il_vocabolario_di_prima_boccia_le_perdite():
    """
    Se questo test si accende, qualcuno ha "allineato" la copia congelata a
    quella vera. Non va allineata: il suo lavoro e' restare indietro.
    """
    assert ms.CONTESTO_PRIMA.search("SAP meldet Gewinn im zweiten Quartal")
    assert not ms.CONTESTO_PRIMA.search("SAP meldet Verlust im zweiten Quartal")
    assert not ms.CONTESTO_PRIMA.search("Eni chiude in perdita nel trimestre")


def test_il_vocabolario_di_adesso_le_fa_passare():
    from gdelt_grezzo import CONTESTO
    assert CONTESTO.search("SAP meldet Verlust im zweiten Quartal")
    assert CONTESTO.search("Eni chiude in perdita nel trimestre")


# ── La divisione in due gruppi ────────────────────────────────────────────
_TERMINI = {"SAP.DE": "SAP", "ENI.MI": "Eni", "BTC-USD": "Bitcoin"}


def test_separa_mette_ogni_titolo_dalla_parte_giusta():
    titoli = [
        "SAP meldet Gewinn im zweiten Quartal",      # gia' prima
        "SAP meldet Verlust im zweiten Quartal",     # solo adesso
        "Eni chiude in perdita nel trimestre",       # solo adesso
        "SAP-Entwickler verdienen gut in Deutschland",   # ne' l'uno ne' l'altro
        "Mia parla della sorella Eni Begovic",       # cronaca, fuori
    ]
    prima, adesso = ms.separa(titoli, _TERMINI)
    assert prima == ["SAP meldet Gewinn im zweiten Quartal"]
    assert adesso == ["SAP meldet Verlust im zweiten Quartal",
                      "Eni chiude in perdita nel trimestre"]


def test_le_monete_non_entrano_nel_confronto():
    """
    A Bitcoin il contesto non viene chiesto ne' prima ne' adesso, quindi le
    sue righe non dicono niente su questa domanda e sporcherebbero le medie.
    """
    prima, adesso = ms.separa(["Bitcoin crolla sotto i 60mila dollari"], _TERMINI)
    assert prima == [] and adesso == []


def test_un_titolo_che_non_nomina_nessuno_viene_saltato():
    prima, adesso = ms.separa(["Il tempo domani sara' brutto"], _TERMINI)
    assert prima == [] and adesso == []


# ── Le medie e la differenza ──────────────────────────────────────────────
def test_sotto_i_cinque_valori_non_si_pronuncia():
    m = ms.media_con_banda([0.1, -0.2, 0.3, 0.0])
    assert m["media"] is None and m["n"] == 4


def test_la_banda_si_stringe_quando_i_valori_sono_tanti():
    """Stessa dispersione, piu' valori, banda piu' stretta."""
    pochi = ms.media_con_banda([-0.5, 0.5] * 5)
    tanti = ms.media_con_banda([-0.5, 0.5] * 30)
    assert (pochi["hi"] - pochi["lo"]) > (tanti["hi"] - tanti["lo"])


def test_la_differenza_e_negativa_se_il_secondo_gruppo_e_piu_cattivo():
    a = [0.4, 0.5, 0.6, 0.5, 0.4, 0.5]
    b = [-0.4, -0.5, -0.6, -0.5, -0.4, -0.5]
    d = ms.differenza(a, b)
    assert d["delta"] < 0
    assert d["hi"] < 0, "due gruppi cosi' separati devono escludere lo zero"


def test_due_gruppi_uguali_non_distinguono_niente():
    a = [0.1, -0.1, 0.2, -0.2, 0.0, 0.1]
    d = ms.differenza(a, list(a))
    assert d["delta"] == 0
    assert d["lo"] <= 0 <= d["hi"]


# ── Il verdetto ───────────────────────────────────────────────────────────
def test_verdetto_non_decide_quando_la_banda_comprende_lo_zero():
    v = ms.verdetto({"delta": -0.08, "lo": -0.30, "hi": 0.14,
                     "_delta": -0.08, "_lo": -0.30, "_hi": 0.14})
    assert "NON DECIDE" in v
    assert "backfill" in v


def test_il_verdetto_non_dipende_da_come_si_arrotonda():
    """
    Il primo giro vero, il 16 agosto 2026, e' finito con la banda a -0.0004.
    Arrotondata diventa "-0.000", e in Python "0 <= -0.000" e' vero: il
    verdetto usciva dal ramo "comprende lo zero" per colpa della stampa.
    """
    d = ms.differenza([0.30] * 30 + [-0.30] * 30, [0.15] * 30 + [-0.45] * 30)
    assert d["hi"] < 0, "questa coppia deve escludere lo zero"
    assert "NON DECIDE" not in ms.verdetto(d)


def test_una_banda_che_sfiora_lo_zero_non_e_una_risposta():
    """
    Chiamare "confermato" un effetto la cui banda arriva a -0.0004 sarebbe
    la stessa cosa della soglia inventata a 0.6 che passava per 0.003.
    """
    v = ms.verdetto({"delta": -0.139, "lo": -0.278, "hi": -0.0004,
                     "_delta": -0.139, "_lo": -0.278, "_hi": -0.0004})
    assert "AL LIMITE" in v
    assert "--quante 0" in v


def test_verdetto_conferma_solo_se_la_banda_sta_tutta_sotto_zero():
    v = ms.verdetto({"delta": -0.31, "lo": -0.52, "hi": -0.10,
                     "_delta": -0.31, "_lo": -0.52, "_hi": -0.10})
    assert "CONFERMATO" in v


def test_verdetto_dice_anche_il_contrario_se_i_dati_lo_dicono():
    """
    Se le righe perse fossero piu' positive, la misura deve poterlo dire.
    Un test che puo' solo confermare l'ipotesi non e' una misura.
    """
    v = ms.verdetto({"delta": 0.28, "lo": 0.09, "hi": 0.47,
                     "_delta": 0.28, "_lo": 0.09, "_hi": 0.47})
    assert "POSITIVE" in v


def test_verdetto_ammette_di_non_avere_abbastanza_roba():
    assert "Troppi pochi" in ms.verdetto({"delta": None, "lo": None, "hi": None})


# ── Il giro completo, senza rete e senza Groq ─────────────────────────────
def _riga(titolo):
    c = [""] * 27
    c[26] = f"<PAGE_TITLE>{titolo}</PAGE_TITLE>"
    return c


def test_il_giro_completo_non_scrive_niente_e_arriva_in_fondo(capsys):
    buone = ["SAP meldet Gewinn im Quartal %d" % i for i in range(12)]
    cattive = ["SAP meldet Verlust im Quartal %d" % i for i in range(12)]
    righe = [_riga(t) for t in buone + cattive]

    punteggi = {**{t: 0.5 for t in buone}, **{t: -0.5 for t in cattive}}

    def finto_score(articoli, prompt=None):
        return [punteggi[a["title"]] for a in articoli]

    with patch("gdelt_grezzo.righe_della_finestra", return_value=(righe, 8, 0)), \
         patch("sentiment_groq.score_batch", side_effect=finto_score), \
         patch("gdelt_source.TERMINE_QUERY", {"SAP.DE": "SAP"}):
        uscita = ms.misura(ore=1, quante=20)

    testo = capsys.readouterr().out
    assert uscita == 0
    assert "Nessuna riga e' stata scritta" in testo
    assert "CONFERMATO" in testo, testo


def test_se_non_ci_sono_righe_nuove_lo_dice_invece_di_inventare(capsys):
    righe = [_riga("SAP meldet Gewinn im Quartal %d" % i) for i in range(12)]
    with patch("gdelt_grezzo.righe_della_finestra", return_value=(righe, 8, 0)), \
         patch("gdelt_source.TERMINE_QUERY", {"SAP.DE": "SAP"}):
        uscita = ms.misura(ore=1, quante=20)
    assert uscita == 1
    assert "Troppo poche" in capsys.readouterr().out
