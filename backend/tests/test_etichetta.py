"""
Test dell'etichettatura a mano.

Il rischio qui non e' di calcolo, e' di contaminazione.

Se chi etichetta vede il punteggio della macchina prima di rispondere, non sta
dando un giudizio: sta confermando. E un campione preso a caso su un archivio
dove meta' delle notizie e' neutra misurerebbe soprattutto la noia, non il
disaccordo.
"""
import json
from unittest.mock import patch

import etichetta as e


def _righe(quante=100):
    """(ticker, titolo, gdelt, modello) con scarti crescenti."""
    fuori = []
    for i in range(quante):
        scarto = i / quante          # da 0 a ~1
        fuori.append(("NVDA", f"titolo numero {i}", 0.0, scarto))
    return fuori


# ── Il campione ───────────────────────────────────────────────────────────
def test_il_campione_e_di_cinquanta_piu_la_riserva():
    scelte = e._campione(_righe(200))
    assert len(scelte) == 50 + e.QUANTI_DI_RISERVA


def test_ci_sono_i_litigiosi_i_concordi_e_quelli_a_caso():
    """
    Solo i litigiosi misurerebbero gli estremi, solo quelli a caso
    misurerebbero la noia. Servono tutti e tre i gruppi.
    """
    campione = e._campione(_righe(200))[:50]
    scarti = sorted(abs(r[3] - r[2]) for r in campione)
    assert scarti[0] < 0.1, "manca almeno un caso su cui i due concordano"
    assert scarti[-1] > 0.9, "manca almeno un caso su cui i due litigano"


def test_il_campione_e_ricostruibile():
    """
    Seme fisso: se un domani si rifa' la misura con altri prompt, devono
    essere gli STESSI titoli, altrimenti si confrontano due campioni diversi.
    """
    a = [r[1] for r in e._campione(_righe(200))]
    b = [r[1] for r in e._campione(_righe(200))]
    assert a == b


def test_l_ordine_e_mescolato():
    """
    In ordine di scarto, chi etichetta capirebbe dopo cinque titoli che i
    primi sono i casi difficili, e cambierebbe metro.
    """
    campione = e._campione(_righe(200))[:50]
    scarti = [abs(r[3] - r[2]) for r in campione]
    assert scarti != sorted(scarti) and scarti != sorted(scarti, reverse=True)


def test_senza_secondo_parere_non_si_puo_fare_niente():
    righe = [("NVDA", "titolo", 0.1, None)] * 40
    assert e._campione(righe) == []


# ── La contaminazione ─────────────────────────────────────────────────────
def test_i_punteggi_delle_macchine_non_si_vedono_mentre_si_etichetta(capsys, tmp_path):
    """
    Vedere cosa ha detto il modello prima di rispondere e' il modo piu' rapido
    di fargli dire quello che voleva sentirsi dire.
    """
    archivio = tmp_path / "e.json"
    lavoro = [{"ticker": "NVDA", "titolo": "Nvidia beats expectations",
               "gdelt": -0.77, "modello": 0.88, "umano": None}]
    with patch.object(e, "ARCHIVIO", str(archivio)), \
         patch("builtins.input", side_effect=["0.5"]):
        e.sessione(lavoro)
    fuori = capsys.readouterr().out
    assert "Nvidia beats expectations" in fuori
    assert "0.88" not in fuori and "-0.77" not in fuori, \
        "ha mostrato il punteggio della macchina prima della risposta"


# ── Il salvataggio ────────────────────────────────────────────────────────
def test_ogni_risposta_viene_salvata_subito(tmp_path):
    """Un'ora di lavoro non deve dipendere dal chiudere bene il programma."""
    archivio = tmp_path / "e.json"
    lavoro = [{"ticker": "A", "titolo": "uno", "gdelt": 0, "modello": 0, "umano": None},
              {"ticker": "B", "titolo": "due", "gdelt": 0, "modello": 0, "umano": None}]
    with patch.object(e, "ARCHIVIO", str(archivio)), \
         patch("builtins.input", side_effect=["0.3", KeyboardInterrupt()]):
        e.sessione(lavoro)
    salvato = json.loads(archivio.read_text(encoding="utf-8"))
    assert salvato[0]["umano"] == 0.3


def test_si_puo_tornare_indietro_di_uno(tmp_path):
    archivio = tmp_path / "e.json"
    lavoro = [{"ticker": "A", "titolo": "uno", "gdelt": 0, "modello": 0, "umano": None},
              {"ticker": "B", "titolo": "due", "gdelt": 0, "modello": 0, "umano": None}]
    with patch.object(e, "ARCHIVIO", str(archivio)), \
         patch("builtins.input", side_effect=["0.3", "s", "-0.4", "0.1", "q"]):
        e.sessione(lavoro)
    salvato = json.loads(archivio.read_text(encoding="utf-8"))
    assert salvato[0]["umano"] == -0.4, "il ritorno indietro non ha riscritto il primo"


def test_un_numero_fuori_scala_viene_rifiutato(tmp_path):
    archivio = tmp_path / "e.json"
    lavoro = [{"ticker": "A", "titolo": "uno", "gdelt": 0, "modello": 0, "umano": None}]
    with patch.object(e, "ARCHIVIO", str(archivio)), \
         patch("builtins.input", side_effect=["5", "pippo", "0.2"]):
        e.sessione(lavoro)
    assert json.loads(archivio.read_text(encoding="utf-8"))[0]["umano"] == 0.2


# ── Il rapporto ───────────────────────────────────────────────────────────
def test_con_poche_etichette_non_da_numeri(tmp_path):
    archivio = tmp_path / "e.json"
    archivio.write_text(json.dumps(
        [{"ticker": "A", "titolo": "x", "gdelt": 0.1, "modello": 0.2, "umano": 0.3}] * 5
    ), encoding="utf-8")
    with patch.object(e, "ARCHIVIO", str(archivio)):
        assert e.rapporto() == 1


def test_il_rapporto_dice_lo_scarto_medio_e_avvisa_che_sei_una_persona(capsys, tmp_path):
    archivio = tmp_path / "e.json"
    dati = [{"ticker": "A", "titolo": f"t{i}", "gdelt": (i % 5) / 10 - 0.2,
             "modello": (i % 7) / 10 - 0.3, "umano": (i % 4) / 10 - 0.15}
            for i in range(30)]
    archivio.write_text(json.dumps(dati), encoding="utf-8")
    with patch.object(e, "ARCHIVIO", str(archivio)):
        assert e.rapporto() == 0
    fuori = capsys.readouterr().out
    assert "scarto medio" in fuori
    assert "UNA persona" in fuori, "manca l'avvertenza che non e' la verita'"


# ── Le lingue che non si leggono ──────────────────────────────────────────
#
# Meta' dell'archivio arriva dal feed tradotto di GDELT, che restituisce il
# titolo nella lingua del giornale. "Bitcoin'de haftalik kayip yuzde 3'u asti"
# e' turco: chiedere un giudizio su quello vuol dire raccogliere un numero
# inventato, che e' peggio di nessun numero.
def _lista(n, riserva=0):
    fuori = [{"ticker": "A", "titolo": f"leggibile {i}", "gdelt": 0.0,
              "modello": 0.0, "umano": None, "illeggibile": False,
              "riserva": False} for i in range(n)]
    fuori += [{"ticker": "R", "titolo": f"riserva {i}", "gdelt": 0.0,
               "modello": 0.0, "umano": None, "illeggibile": False,
               "riserva": True} for i in range(riserva)]
    return fuori


def test_x_scarta_il_titolo_e_ne_promuove_uno_dalla_riserva(tmp_path):
    archivio = tmp_path / "e.json"
    lavoro = _lista(2, riserva=2)
    with patch.object(e, "ARCHIVIO", str(archivio)), \
         patch("builtins.input", side_effect=["x", "0.2", "0.3", "q"]):
        e.sessione(lavoro)
    salvato = json.loads(archivio.read_text(encoding="utf-8"))
    assert salvato[0]["illeggibile"] is True
    assert salvato[0]["umano"] is None, "un titolo scartato non deve avere un voto"
    promossi = [v for v in salvato if v["titolo"].startswith("riserva") and not v["riserva"]]
    assert len(promossi) == 1, "non ha pescato dalla riserva"


def test_il_campione_non_si_restringe_finche_c_e_riserva(tmp_path):
    archivio = tmp_path / "e.json"
    lavoro = _lista(3, riserva=3)
    with patch.object(e, "ARCHIVIO", str(archivio)), \
         patch("builtins.input", side_effect=["x", "x", "0.1", "0.1", "0.1", "q"]):
        e.sessione(lavoro)
    salvato = json.loads(archivio.read_text(encoding="utf-8"))
    votati = sum(1 for v in salvato if v["umano"] is not None)
    assert votati == 3, "due scartati e due promossi devono lasciare il conto invariato"


def test_finita_la_riserva_lo_dice_invece_di_fingere(capsys, tmp_path):
    archivio = tmp_path / "e.json"
    lavoro = _lista(2, riserva=0)
    with patch.object(e, "ARCHIVIO", str(archivio)), \
         patch("builtins.input", side_effect=["x", "0.2"]):
        e.sessione(lavoro)
    assert "riserva finita" in capsys.readouterr().out


def test_il_rapporto_avvisa_che_il_risultato_vale_solo_per_le_lingue_lette(capsys, tmp_path):
    """
    I titoli scartati sono quelli in lingue non leggibili, e sono proprio
    quelli su cui il modello se la cava peggio: il numero che esce vale per
    le lingue che si leggono, non per l'archivio.
    """
    archivio = tmp_path / "e.json"
    dati = [{"ticker": "A", "titolo": f"t{i}", "gdelt": (i % 5) / 10 - 0.2,
             "modello": (i % 7) / 10 - 0.3, "umano": (i % 4) / 10 - 0.15,
             "illeggibile": False, "riserva": False} for i in range(30)]
    dati += [{"ticker": "T", "titolo": "Bitcoin'de haftalik kayip", "gdelt": 0.0,
              "modello": 0.0, "umano": None, "illeggibile": True, "riserva": False}
             for _ in range(6)]
    archivio.write_text(json.dumps(dati), encoding="utf-8")
    with patch.object(e, "ARCHIVIO", str(archivio)):
        assert e.rapporto() == 0
    fuori = capsys.readouterr().out
    assert "lingue non leggibili: 6" in fuori
    assert "vale per le lingue che leggi" in fuori
