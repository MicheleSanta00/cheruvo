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


# Titoli finti ma DAVVERO diversi fra loro. La prima versione di questo aiuto
# generava "titolo numero 1", "titolo numero 2" e cosi' via: per il filtro sui
# fatti ripetuti sono la stessa notizia, ed e' giusto che li fonda. La finzione
# era sbagliata, non il filtro.
_SOGGETTI = ["fabbrica", "accordo", "bilancio", "causa", "brevetto", "fusione",
             "licenziamenti", "dividendo", "esordio", "richiamo", "multa",
             "concessione", "appalto", "scissione", "aumento", "riacquisto",
             "declassamento", "promozione", "trimestrale", "guidance"]
_LUOGHI = ["Milano", "Berlino", "Taiwan", "Texas", "Norvegia", "Cina", "Parigi",
           "Londra", "Osaka", "Detroit", "Seul", "Dublino", "Madrid", "Varsavia"]
_VERBI = ["annuncia", "smentisce", "rimanda", "chiude", "apre", "vende",
          "compra", "sospende", "raddoppia", "taglia"]


def _righe(quante=100):
    """(ticker, titolo, gdelt, modello) con scarti crescenti e titoli distinti."""
    fuori = []
    for i in range(quante):
        scarto = i / quante          # da 0 a ~1
        # Tre parole condivise al massimo, il resto e' unico per riga: cosi'
        # due titoli non arrivano mai alle quattro parole in comune che
        # `_stessa_notizia` chiede per fonderli. Con un vocabolario piccolo e
        # riusato le collisioni sono la norma, ed e' un difetto della finzione,
        # non del filtro.
        titolo = (f"societa{i} {_VERBI[i % len(_VERBI)]} "
                  f"{_SOGGETTI[i % len(_SOGGETTI)]} progetto{i} "
                  f"per {_LUOGHI[i % len(_LUOGHI)]} valore{i} milioni")
        fuori.append((f"TK{i}", titolo, 0.0, scarto))
    return fuori


# ── Riconoscere la stessa notizia riscritta ───────────────────────────────
#
# La coppia su Intel e' il motivo per cui questo filtro esiste, ed e' anche il
# caso che la prima versione NON riconosceva: i due titoli condividono due
# parole su sei, il 33%, molto sotto la soglia del 60%. La regola a proporzione
# prende le riscritture pigre, quella sulla cifra prende le riscritture vere.
#
# Nota su cosa vale questa prova: le coppie qui sotto sono scritte a mano, non
# pescate dall'archivio. Dicono che le due regole fanno quello per cui sono
# state scritte, NON con che frequenza sbagliano sui titoli veri. Quel numero
# si ottiene solo girando il filtro sull'archivio.
_STESSO_FATTO = [
    ("Intel targets $15 billion stock sale after rally",
     "Intel seeks $15 billion as turnaround boosts shares"),
    ("Intel to raise $15 billion in share sale",
     "Chipmaker Intel plans $15 billion equity raise"),
    ("Eni firma un accordo da 2 miliardi in Algeria",
     "Accordo da 2 miliardi per Eni sul gas algerino"),
    ("Nvidia beats earnings expectations for the fourth quarter",
     "Nvidia tops fourth quarter earnings expectations analysts say"),
    ("Tesla richiama 400.000 veicoli",
     "Tesla recalls 400,000 vehicles over camera fault"),
]

_FATTI_DIVERSI = [
    # Stessa societa', due vicende
    ("Eni taglia le stime", "Eni sale in borsa"),
    ("Ferrari alza la guidance dopo i conti del trimestre",
     "Ferrari conferma la guidance nonostante i dazi"),
    ("Shell taglia 200 posti nel settore rinnovabili",
     "Shell chiude il trimestre sopra le attese"),
    # L'anno non e' un fatto, dice quando e non cosa
    ("Nvidia alza le stime per il 2026",
     "Nvidia annuncia il riacquisto di azioni per il 2026"),
    # Una percentuale piccola non e' un'impronta: si ripete dappertutto
    ("Apple sale del 3% a Wall Street", "Tesla scende del 3% a Wall Street"),
    ("UniCredit sale del 2% dopo la trimestrale",
     "UniCredit apre un piano da 2 miliardi di buyback"),
    # Niente in comune
    ("Apple lancia il nuovo iPhone a settembre",
     "Tesla richiama 400.000 veicoli negli Stati Uniti"),
]


def test_riconosce_la_stessa_notizia_riscritta():
    for a, b in _STESSO_FATTO:
        assert e._stessa_notizia(a, b), f"non fusi: {a!r} / {b!r}"
        assert e._stessa_notizia(b, a), f"non simmetrico: {a!r} / {b!r}"


def test_non_fonde_fatti_diversi_della_stessa_societa():
    for a, b in _FATTI_DIVERSI:
        assert not e._stessa_notizia(a, b), f"fusi per sbaglio: {a!r} / {b!r}"


def test_gli_anni_non_contano_come_cifre():
    """Il 2026 dice quando, non cosa: due fatti dello stesso anno non sono
    lo stesso fatto."""
    assert e._cifre("Nvidia alza le stime per il 2026") == set()
    assert "15" in e._cifre("Intel raises $15 billion in 2026")


# ── Il campione ───────────────────────────────────────────────────────────
def test_il_campione_e_di_cinquanta_piu_la_riserva():
    scelte = e._campione(_righe(400))
    assert len(scelte) == 50 + e.QUANTI_DI_RISERVA


def test_con_poco_materiale_il_campione_si_accorcia_invece_di_ripetersi():
    """
    Meglio quaranta titoli distinti che cinquanta con dentro dieci copie: chi
    etichetta la stessa notizia due volte non aggiunge un dato, aggiunge una
    conferma di se stesso.
    """
    scelte = e._campione(_righe(30))
    titoli = [r[1] for r in scelte]
    assert len(titoli) == len(set(titoli))
    assert len(scelte) <= 30


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


# ── Lo stesso fatto raccontato in modo diverso ────────────────────────────
#
# `_chiave_titolo` riconosce solo le copie identiche. Ma "Intel targets $15
# billion stock sale after rally" e "Intel seeks $15 billion as turnaround
# boosts shares" sono due titoli diversi e lo stesso fatto: chi etichetta li
# vede tutti e due, e dopo la quinta variante smette di giudicare e comincia a
# copiare il voto di prima.
def test_riconosce_lo_stesso_fatto_riscritto():
    assert e._stessa_notizia(
        "Intel targets $15 billion stock sale after rally",
        "Intel targets a $15 billion stock sale, after the rally")


def test_due_fatti_diversi_sullo_stesso_titolo_restano_diversi():
    assert not e._stessa_notizia(
        "Intel raises $20 billion in upsized share sale",
        "Intel appoints new chief financial officer")


def test_il_campione_non_ripete_lo_stesso_fatto():
    """Venti riscritture della stessa notizia devono valere una riga sola."""
    righe = []
    for i in range(30):
        righe.append(("INTC", f"Intel targets 15 billion stock sale after rally {i//29}", 0.0, 0.9))
    for i in range(60):
        righe.append((f"TK{i}", f"notizia completamente diversa numero {i} su cose varie", 0.0, i/100))
    campione = e._campione(righe)[:50]
    intel = [r for r in campione if r[0] == "INTC"]
    assert len(intel) <= 1, f"{len(intel)} varianti della stessa notizia nel campione"


def test_nessun_titolo_occupa_piu_di_tre_posti():
    """
    Nel campione dell'11 agosto 2026 dodici disaccordi su dodici erano Intel.
    Un tetto per ticker costringe il campione a coprire il mercato invece di
    misurare una giornata sola di una societa' sola.
    """
    from collections import Counter
    righe = [("INTC", f"Intel fa una cosa diversa numero {i} in un settore", 0.0, 0.9 - i/200)
             for i in range(40)]
    righe += [(f"TK{i}", f"altra societa numero {i} annuncia qualcosa di suo", 0.0, i/100)
              for i in range(60)]
    campione = e._campione(righe)[:50]
    conta = Counter(r[0] for r in campione)
    assert conta.most_common(1)[0][1] <= 3, f"un ticker occupa {conta.most_common(1)[0][1]} posti"
