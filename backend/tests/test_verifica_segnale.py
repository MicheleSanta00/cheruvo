"""
Test della verifica del segnale.

Il caso più importante qui dentro è l'ultimo: che su dati puramente casuali
il verdetto sia "nessun segnale". Un test che inventa segnali dove non ce ne
sono è peggio di nessun test, perché porterebbe a scrivere sul sito una cosa
non vera.
"""
import random
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import verifica_segnale as v


OGGI = date(2026, 8, 5)


# ── La query non deve rompersi sui segnaposto ─────────────────────────────
def test_la_query_ha_tanti_segnaposto_quanti_parametri():
    """
    psycopg2 conta i %s su TUTTO il testo della query, commenti inclusi. Il
    5 agosto 2026 un commento che spiegava un bug conteneva un %s: diventava
    un terzo segnaposto che nessuno passava, e la query moriva con
    "tuple index out of range" appena arrivata in produzione.
    """
    cur = MagicMock()
    cur.fetchall.return_value = []
    conn = MagicMock()
    conn.cursor.return_value = cur
    pool = MagicMock()
    pool.getconn.return_value = conn

    with patch.object(v, "get_pool", return_value=pool):
        v.serie_sentiment("BTC-USD", 90)

    sql, params = cur.execute.call_args[0]
    assert sql.count("%s") == len(params), (
        f"la query ha {sql.count('%s')} segnaposto ma riceve {len(params)} "
        f"parametri: in produzione fallirebbe subito")


def test_la_query_filtra_solo_le_fonti_lecite():
    """Verificare il segnale su righe che stiamo per cancellare non ha senso."""
    cur = MagicMock()
    cur.fetchall.return_value = []
    conn = MagicMock()
    conn.cursor.return_value = cur
    pool = MagicMock()
    pool.getconn.return_value = conn

    with patch.object(v, "get_pool", return_value=pool):
        v.serie_sentiment("BTC-USD", 90)

    sql = cur.execute.call_args[0][0]
    for prefisso in ("GDELT", "SEC EDGAR", "Alpha Vantage"):
        assert prefisso in sql
    assert "Google News" not in sql


# ── La statistica ─────────────────────────────────────────────────────────
def test_spearman_regge_le_relazioni_non_lineari():
    """
    È il motivo per cui non usiamo Pearson: sui rendimenti crypto un singolo
    giorno da +18% trascinerebbe il risultato da solo.
    """
    x = [1, 2, 3, 4, 5]
    y = [1, 4, 9, 16, 25]          # monotona ma curva
    # Con tolleranza e non ==: la somma di prodotti in virgola mobile
    # restituisce 0.9999999999999998, che è 1 per qualunque uso pratico ma
    # non per l'uguaglianza esatta.
    assert abs(v.spearman(x, y) - 1.0) < 1e-9
    assert v.pearson(x, y) < 0.99


def test_ranghi_con_pari_merito():
    assert v._ranghi([10, 20, 20, 30]) == [1.0, 2.5, 2.5, 4.0]


def test_la_probabilita_non_e_mai_zero():
    """
    Nessun test empirico può dire "impossibile per caso". Con lo zero al
    numeratore si riporterebbe p = 0, che è una affermazione più forte di
    quanto il metodo consenta.
    """
    random.seed(1)
    x = list(range(40))
    y = list(range(40))            # legame perfetto
    assert v.permutazione(x, y, giri=200) > 0


# ── L'allineamento non deve guardare nel futuro ───────────────────────────
def test_il_rendimento_parte_dalla_chiusura_del_giorno_del_sentiment():
    """
    Al momento in cui vediamo il sentiment di oggi, la giornata di oggi è già
    andata. Far partire il rendimento prima significherebbe scommettere su un
    movimento già avvenuto: è il modo classico di produrre un backtest
    brillante e inutile.
    """
    sent = {OGGI: (0.5, 10)}
    prezzi = {OGGI: 100.0, OGGI + timedelta(days=1): 110.0}
    xs, ys = v.allinea(sent, prezzi, 1)
    assert xs == [0.5]
    assert abs(ys[0] - 0.10) < 1e-9


def test_i_giorni_con_poche_notizie_vengono_scartati():
    """Una media su due articoli non è un dato, è un aneddoto."""
    sent = {OGGI: (0.9, 2)}
    prezzi = {OGGI: 100.0, OGGI + timedelta(days=1): 110.0}
    xs, _ = v.allinea(sent, prezzi, 1)
    assert xs == []


# ── Il verdetto ───────────────────────────────────────────────────────────
def _mondo(seme, legame=0.0, giorni=70):
    """Costruisce sentiment e prezzi con un legame noto (0 = nessuno)."""
    random.seed(seme)
    sent, prezzi, p = {}, {}, 100.0
    punteggi = [random.gauss(0, 0.3) for _ in range(giorni)]
    for i in range(giorni + 8):
        g = OGGI - timedelta(days=giorni - i)
        if i < giorni:
            sent[g] = (punteggi[i], 12)
            prezzi[g] = p
            p *= (1 + punteggi[i] * legame + random.gauss(0, 0.02))
        else:
            prezzi[g] = p
    return sent, prezzi


def _verdetto(sent, prezzi, capsys):
    with patch.object(v, "serie_sentiment", return_value=sent), \
         patch.object(v, "serie_prezzi", return_value=prezzi), \
         patch.object(v, "GIRI_PERMUTAZIONE", 400):
        v.analizza("BTC-USD", 90)
    return capsys.readouterr().out


def test_su_dati_casuali_dice_che_non_ce_segnale(capsys):
    """Il caso che conta di più: il test non deve inventare niente."""
    sent, prezzi = _mondo(seme=7, legame=0.0)
    out = _verdetto(sent, prezzi, capsys)
    assert "NESSUN SEGNALE DIMOSTRABILE" in out


def test_un_segnale_vero_lo_trova(capsys):
    """Se non trovasse nemmeno un legame forte iniettato, sarebbe inutile."""
    sent, prezzi = _mondo(seme=3, legame=0.06)
    out = _verdetto(sent, prezzi, capsys)
    assert "QUALCOSA C'È" in out


def test_con_pochi_giorni_si_rifiuta_di_rispondere(capsys):
    """
    "Non lo so" è una risposta legittima, e con dodici giorni è l'unica
    onesta. Il pericolo sarebbe dire "nessun segnale" facendolo sembrare una
    conclusione invece di una mancanza di dati.
    """
    sent = {OGGI - timedelta(days=i): (0.1, 10) for i in range(12)}
    prezzi = {OGGI - timedelta(days=i): 100.0 + i for i in range(30)}
    out = _verdetto(sent, prezzi, capsys)
    assert "FERMO QUI" in out
    assert "non si può sapere" in out


def test_il_verdetto_negativo_non_dice_che_il_segnale_non_esiste(capsys):
    """
    Differenza sottile e importante: "non ho prove" non è "ho la prova del
    contrario". Con settanta giorni si vedono solo effetti grossi.
    """
    sent, prezzi = _mondo(seme=11, legame=0.0)
    out = _verdetto(sent, prezzi, capsys)
    assert "NON dimostra che il segnale non esista" in out
