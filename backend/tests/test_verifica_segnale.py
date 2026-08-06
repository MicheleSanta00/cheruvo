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
def test_la_query_sopravvive_alla_sostituzione_dei_parametri():
    """
    Il test che avrebbe risparmiato due giri falliti in produzione.

    Contare le occorrenze di "%s" non basta, ed è l'errore che ho fatto la
    prima volta. psycopg2 non cerca "%s": applica la sostituzione in stile
    printf su TUTTO il testo, e quindi ogni singolo simbolo di percentuale
    conta. Il pattern `LIKE 'GDELT %'` ne contiene uno, e quello bastava a
    far esplodere la query con "tuple index out of range" pur essendoci
    esattamente due "%s".

    Qui riproduco la sostituzione vera. Se il testo contiene una percentuale
    di troppo, questo scoppia esattamente come scoppiava il workflow.
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
    try:
        sql % tuple("x" for _ in params)
    except (TypeError, ValueError, IndexError) as e:
        raise AssertionError(
            f"la query non regge la sostituzione dei parametri ({e}). "
            f"Di solito è un simbolo di percentuale di troppo nel testo: "
            f"va passato come parametro o raddoppiato in '%%'.") from None


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

    sql, params = cur.execute.call_args[0]
    # I prefissi stanno nei PARAMETRI, non nel testo della query: cercarli
    # nella stringa darebbe un test che passa solo finché li si incolla lì,
    # cioè finché si tiene il bug del simbolo di percentuale.
    testo = " ".join(str(p) for p in params)
    for prefisso in ("GDELT", "SEC EDGAR", "Alpha Vantage"):
        assert prefisso in testo, f"{prefisso} non arriva alla query"
    assert "Google News" not in testo and "Google News" not in sql
    assert "Yahoo" not in testo and "Yahoo" not in sql


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


# ── I prezzi ──────────────────────────────────────────────────────────────
def test_i_prezzi_si_leggono_dall_indice_non_dalle_colonne():
    """
    _yahoo_chart chiude con df.set_index("date"): la data è l'INDICE, non una
    colonna. Cercarla fra le colonne non solleva nessun errore, restituisce
    semplicemente una serie vuota, e il verdetto diventa "nessun giorno
    allineato" per un motivo che non c'entra niente coi dati.
    """
    import pandas as pd
    import prices

    righe = [{"date": f"2026-08-{g:02d}", "Close": 100.0 + g} for g in range(1, 6)]
    df = pd.DataFrame(righe)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()

    with patch.object(prices, "get_prices", return_value=df):
        serie = v.serie_prezzi("BTC-USD", 90)

    assert len(serie) == 5
    assert serie[date(2026, 8, 3)] == 103.0


def test_chiede_un_periodo_che_yahoo_conosce():
    """
    Yahoo accetta solo un vocabolario chiuso di periodi. La prima versione
    chiedeva "105d", che non ne fa parte, e Yahoo rispondeva "possibly
    delisted; no price data found" su BITCOIN: un messaggio che manda a
    cercare il problema nel posto sbagliato.
    """
    import pandas as pd
    import prices

    validi = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"}
    visti = []

    def finto(ticker, periodo):
        visti.append(periodo)
        return pd.DataFrame()

    with patch.object(prices, "get_prices", side_effect=finto):
        for giorni in (7, 30, 90, 180, 365):
            v.serie_prezzi("BTC-USD", giorni)

    assert visti, "get_prices non è stato chiamato"
    for periodo in visti:
        assert periodo in validi, f"'{periodo}' non è un periodo che Yahoo accetta"


def test_il_periodo_copre_anche_l_orizzonte_piu_lungo():
    """
    Per il rendimento a T+7 servono sette giorni di prezzi OLTRE l'ultimo
    giorno di notizie. Un periodo esatto quanto i giorni chiesti lascerebbe
    senza prezzo proprio le osservazioni finali.
    """
    import pandas as pd
    import prices

    giorni_per_etichetta = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730}
    visti = []

    def finto(ticker, periodo):
        visti.append(periodo)
        return pd.DataFrame()

    with patch.object(prices, "get_prices", side_effect=finto):
        v.serie_prezzi("BTC-USD", 90)

    coperti = giorni_per_etichetta[visti[0]]
    assert coperti >= 90 + max(v.ORIZZONTI)
