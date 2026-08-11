"""
Test dell'aggregazione giornaliera del sentiment.

Il rischio qui non è di calcolo, è di reticenza.

Una media giornaliera che viaggia da sola è una cifra che sembra un fatto. Il 7
agosto 2026 su NVDA l'archivio conteneva un -0.9 e un +0.7 sullo stesso identico
evento, letti da due giornali diversi. Usciva +0.2098 e il conflitto spariva.
Nessuno di quei due articoli era sbagliato: era la media a non dire abbastanza.

Questi test servono a impedire che i tre numeri che accompagnano la media (n,
dev, errore) vengano tolti perché "tanto il grafico non li usa".

Si importa da `giornaliero` e MAI da `main`. Quando questa funzione stava
dentro main.py, importarla qui la faceva entrare nella cache dei moduli a tempo
di raccolta, cioè prima che test_auth.py potesse applicare il suo
patch("database.get_pool"): tredici test finivano per aprire una connessione
vera a Supabase durante lo startup dell'app.
"""
import pandas as pd
import pytest

from giornaliero import aggrega_giornaliero


def _righe(coppie):
    """Da (giorno, [punteggi]) al DataFrame che si aspetta la funzione."""
    dati = []
    for giorno, punteggi in coppie:
        for i, s in enumerate(punteggi):
            dati.append({
                "published_date": pd.Timestamp(f"{giorno} {8 + i % 10}:00:00"),
                "sentiment": s,
            })
    return pd.DataFrame(dati)


# ── I tre numeri ci sono ───────────────────────────────────────────────────
def test_ogni_giorno_porta_media_conteggio_disaccordo_ed_errore():
    out = aggrega_giornaliero(_righe([("2026-08-07", [0.2, 0.4, -0.1])]))
    assert len(out) == 1
    for campo in ("date", "sentiment", "n", "dev", "errore"):
        assert campo in out[0], f"manca {campo}"


def test_il_conteggio_e_quello_vero():
    out = aggrega_giornaliero(_righe([("2026-08-07", [0.1] * 61)]))
    assert out[0]["n"] == 61


# ── Il caso che ha fatto nascere la modifica ───────────────────────────────
def test_due_notizie_opposte_lasciano_un_segno_invece_di_sparire():
    """
    Il caso del 7 agosto ridotto all'osso: stesso fatto, giudizi opposti.

    La media da sola direbbe "giornata neutra". Il disaccordo dice che non c'è
    nessuna giornata neutra, ci sono due letture inconciliabili dello stesso
    evento.
    """
    out = aggrega_giornaliero(_righe([("2026-08-07", [-0.9, 0.7])]))[0]

    assert out["sentiment"] == pytest.approx(-0.1, abs=0.001)
    assert out["dev"] > 1.0, "due giudizi opposti devono produrre un disaccordo grande"


def test_a_parita_di_disaccordo_piu_notizie_vuol_dire_media_piu_precisa():
    """
    Stesso disaccordo, numero di notizie diverso: `dev` resta lì dov'è,
    `errore` scende. È la prova che i due numeri misurano cose diverse e che
    tenerne uno solo perderebbe informazione.

    Il confronto è 60 contro 10 e non 60 contro 4 perché sotto la decina la
    correzione di Bessel (il diviso n-1 invece che n) sposta la deviazione in
    modo visibile: a n=4 verrebbe 0.92 invece di 0.81, e il test fallirebbe per
    un motivo che non c'entra niente con quello che vuole dimostrare.
    """
    tante = aggrega_giornaliero(_righe([("2026-08-07", [-0.9, 0.7] * 30)]))[0]
    poche = aggrega_giornaliero(_righe([("2026-08-07", [-0.9, 0.7] * 5)]))[0]

    assert tante["dev"] == pytest.approx(poche["dev"], abs=0.05), \
        "il disaccordo fra le notizie non dipende da quante ne sono uscite"
    assert tante["errore"] < poche["errore"] / 2, \
        "con sei volte più notizie la media si conosce molto meglio"


def test_una_giornata_puo_avere_media_precisa_e_notizie_in_totale_disaccordo():
    """
    È il 7 agosto vero su NVDA: 61 notizie, media +0.210, errore 0.061, dev
    0.476, punteggi da -0.9 a +0.8.

    Le due cose valgono INSIEME, e con la sola media non si vedeva nessuna
    delle due. Qui si ricostruisce quella forma: tanti articoli, molto divisi.
    """
    giorno = aggrega_giornaliero(_righe([
        ("2026-08-07", [-0.9, 0.7, 0.4, 0.0, 0.8, -0.4, 0.2, 0.1] * 8),
    ]))[0]

    assert giorno["n"] > 40
    assert giorno["dev"] > 0.4, "le notizie di quel giorno erano davvero divise"
    assert giorno["errore"] < 0.1, "eppure la media era conosciuta bene"


# ── I casi limite, che sono quelli in cui si mente più facilmente ──────────
def test_una_notizia_sola_non_e_daccordo_con_nessuno():
    """
    Con una notizia la deviazione standard non esiste. Metterci zero direbbe
    "tutte le fonti concordano", che da una fonte sola non si può sapere.
    """
    out = aggrega_giornaliero(_righe([("2026-08-07", [0.5])]))[0]
    assert out["n"] == 1
    assert out["dev"] is None
    assert out["errore"] is None


def test_un_giorno_senza_notizie_resta_vuoto_e_non_diventa_zero():
    """
    Uno zero è un giudizio ("neutro"), l'assenza di notizie non lo è. Il buco
    fra il 7 e il 9 deve restare un buco.
    """
    out = aggrega_giornaliero(_righe([("2026-08-07", [0.4]), ("2026-08-09", [0.2])]))
    vuoto = [r for r in out if r["date"] == "2026-08-08"]
    assert len(vuoto) == 1
    assert vuoto[0]["sentiment"] is None
    assert vuoto[0]["n"] == 0


def test_niente_nan_nel_payload():
    """
    NaN non è JSON valido: passa il serializzatore di FastAPI e arriva al
    browser come token non parsabile. Va convertito in None a monte.
    """
    out = aggrega_giornaliero(_righe([
        ("2026-08-07", [0.5]),            # dev NaN, una notizia sola
        ("2026-08-09", [0.1, 0.2, 0.3]),
    ]))
    for riga in out:
        for k, v in riga.items():
            assert v is None or v == v, f"{k} è NaN nella riga {riga['date']}"
