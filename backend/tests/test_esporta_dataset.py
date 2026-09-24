"""
Test dell'esportazione del dataset.

Due cose da proteggere, e la prima e' legale e non tecnica.

La query deve prendere SOLO le righe GDELT. Le righe istituzionali (BCE, ESMA)
portano una licenza che chiede di dichiarare le modifiche, e un punteggio di
sentiment e' una modifica; Alpha Vantage e' un'autorizzazione al nostro uso e
non una licenza di ridistribuzione. Impacchettarle sotto una citazione GDELT
direbbe una cosa falsa sulla loro licenza, e sarebbe la stessa scorciatoia che
a luglio e' costata NewsAPI.

La seconda e' che il periodo di raccolta venga dichiarato riga per riga. Fino
al 16 agosto 2026 il filtro riconosceva i guadagni e non le perdite, quindi
quel sentiment e' spostato verso l'alto per costruzione. Chi scarica deve
poterlo vedere senza leggere il changelog.
"""
import csv
from datetime import date

import esporta_dataset as ed


# ── Il periodo di raccolta ────────────────────────────────────────────────
def test_i_tre_regimi_di_raccolta():
    assert ed.periodo(date(2026, 8, 1)) == "pre-riforma"
    assert ed.periodo(date(2026, 8, 7)) == "filtro-asimmetrico"
    assert ed.periodo(date(2026, 8, 15)) == "filtro-asimmetrico"
    assert ed.periodo(date(2026, 8, 16)) == "stabile"
    assert ed.periodo(date(2026, 9, 19)) == "stabile"


def test_i_confini_sono_quelli_del_resto_del_progetto():
    """
    Le due date non sono scelte qui: sono le stesse che usano
    verifica_segnale.py e anomalie.py. Spostarne una sola vorrebbe dire avere
    due verita' diverse sullo stesso archivio.
    """
    from verifica_segnale import DA_QUANDO
    assert ed.REGOLE_CAMBIATE == DA_QUANDO
    assert ed.FILTRO_CORRETTO > ed.REGOLE_CAMBIATE


# ── La licenza ────────────────────────────────────────────────────────────
def test_la_query_prende_solo_gdelt():
    """
    Se qualcuno allarga questo filtro, il dataset esce con dentro righe la cui
    licenza dice altro. Il test guarda il testo della query di proposito: e'
    l'unico punto in cui la regola e' scritta.
    """
    import inspect
    sql = inspect.getsource(ed.righe)
    assert "source LIKE 'GDELT%%'" in sql
    for vietata in ("istituzionale", "Alpha Vantage", "SEC EDGAR"):
        assert vietata not in sql, vietata


def test_la_citazione_contiene_nome_e_link():
    """
    I termini GDELT chiedono due cose legate da una congiunzione: la citazione
    E il link. Averne una sola e' meta' obbligo, ed e' il difetto che il 19
    settembre 2026 e' stato trovato in fondo all'app.
    """
    assert "GDELT Project" in ed.CITAZIONE
    assert "https://www.gdeltproject.org/" in ed.CITAZIONE


# ── Il file ───────────────────────────────────────────────────────────────
def _finte(monkeypatch, righe):
    monkeypatch.setattr(ed, "righe", lambda limite=None: iter(righe))


def _riga(ticker="BTC-USD", giorno="2026-09-01", sentiment="0.2500"):
    return {
        "ticker": ticker,
        "data_pubblicazione": f"{giorno}T10:00:00+00:00",
        "fonte": "GDELT · reuters.com",
        "lingua": "eng",
        "titolo": "Bitcoin rises, with a comma, and \"quotes\"",
        "url": "https://example.com/a",
        "sentiment": sentiment,
        "origine_punteggio": "llm",
        "periodo_raccolta": ed.periodo(date.fromisoformat(giorno)),
    }


def test_il_csv_sopravvive_a_virgole_e_virgolette_nei_titoli(tmp_path,
                                                             monkeypatch):
    """
    Meta' dell'archivio sono titoli di giornale veri, pieni di virgole e
    virgolette. Un CSV scritto a mano li spezzerebbe in colonne fantasma.
    """
    _finte(monkeypatch, [_riga()])
    f = tmp_path / "d.csv"
    ed.esporta(str(f))

    with open(f, encoding="utf-8", newline="") as fh:
        lette = list(csv.DictReader(fh))
    assert len(lette) == 1
    assert lette[0]["titolo"] == 'Bitcoin rises, with a comma, and "quotes"'
    assert lette[0]["ticker"] == "BTC-USD"


def test_il_riepilogo_conta_i_regimi_separatamente(tmp_path, monkeypatch):
    _finte(monkeypatch, [
        _riga(giorno="2026-08-01"),
        _riga(giorno="2026-08-10"),
        _riga(giorno="2026-09-01"),
        _riga(giorno="2026-09-02", ticker="ETH-USD"),
    ])
    r = ed.esporta(str(tmp_path / "d.csv"))
    assert r["righe"] == 4
    assert r["ticker"] == 2
    assert r["periodi"] == {"pre-riforma": 1, "filtro-asimmetrico": 1,
                            "stabile": 2}
    assert r["dal"] == "2026-08-01"
    assert r["al"] == "2026-09-02"


def test_un_archivio_vuoto_non_esplode(tmp_path, monkeypatch):
    _finte(monkeypatch, [])
    r = ed.esporta(str(tmp_path / "d.csv"))
    assert r["righe"] == 0
    assert r["dal"] is None


def test_le_colonne_del_file_sono_quelle_dichiarate(tmp_path, monkeypatch):
    _finte(monkeypatch, [_riga()])
    f = tmp_path / "d.csv"
    ed.esporta(str(f))
    with open(f, encoding="utf-8", newline="") as fh:
        intestazione = next(csv.reader(fh))
    assert tuple(intestazione) == ed.COLONNE
    # Il riassunto generato dal modello non esce: e' testo derivato, pesa, e
    # non serve a nessuno per rifare il conto.
    assert "summary" not in intestazione
    assert "riassunto" not in intestazione
