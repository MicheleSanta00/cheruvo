"""
test_database_leggi.py — La lettura che non passa da pd.read_sql.

pandas avvisava a ogni chiamata che una connessione psycopg2 e' un DBAPI2
"not tested". Funzionava, ma e' supporto dichiarato non testato: puo' sparire
in una versione maggiore, e quando sparisce non avvisa piu', solleva. I due
endpoint che ci passano sono /api/news e /api/sentiment.

Qui si protegge che il rimpiazzo si comporti come prima, colonne comprese.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("DATABASE_URL", "postgresql://fake:fake@localhost/fake")

import warnings
from unittest.mock import MagicMock, patch

import pandas as pd

import database


def _conn(righe, colonne):
    conn, cur = MagicMock(), MagicMock()
    cur.fetchall.return_value = righe
    cur.description = [(c,) for c in colonne]
    conn.cursor.return_value = cur
    return conn, cur


COLONNE = ["id", "ticker", "title", "sentiment", "published_date"]


def test_torna_un_dataframe_con_le_colonne_giuste():
    conn, _ = _conn([(1, "NVDA", "Titolo", 0.4, "2026-08-18")], COLONNE)
    with patch("database._get_connection", return_value=conn), \
         patch("database._release_connection"):
        df = database._leggi("SELECT * FROM news WHERE ticker = %s", ("NVDA",))

    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == COLONNE
    assert df.iloc[0]["ticker"] == "NVDA"
    assert df.iloc[0]["sentiment"] == 0.4


def test_un_risultato_vuoto_tiene_le_colonne():
    """
    Il caso che romperebbe tutto in silenzio: `get_all_data` fa `df.empty` e
    chi chiama legge le colonne. Un DataFrame vuoto SENZA colonne non solleva
    subito, solleva piu' avanti e altrove.
    """
    conn, _ = _conn([], COLONNE)
    with patch("database._get_connection", return_value=conn), \
         patch("database._release_connection"):
        df = database._leggi("SELECT * FROM news WHERE ticker = %s", ("XXX",))

    assert df.empty
    assert list(df.columns) == COLONNE


def test_non_avvisa_piu_niente():
    conn, _ = _conn([(1, "NVDA", "Titolo", 0.4, "2026-08-18")], COLONNE)
    with patch("database._get_connection", return_value=conn), \
         patch("database._release_connection"):
        with warnings.catch_warnings(record=True) as visti:
            warnings.simplefilter("always")
            database._leggi("SELECT 1", ())
    pandas_warn = [w for w in visti if "DBAPI2" in str(w.message)]
    assert not pandas_warn, [str(w.message) for w in pandas_warn]


def test_i_parametri_passano_al_driver_non_alla_stringa():
    """
    L'interpolazione la fa psycopg2. Se un giorno qualcuno la facesse con una
    f-string, il ticker arriverebbe dentro l'SQL.
    """
    conn, cur = _conn([], COLONNE)
    with patch("database._get_connection", return_value=conn), \
         patch("database._release_connection"):
        database._leggi("SELECT * FROM news WHERE ticker = %s", ("NVDA",))

    sql, params = cur.execute.call_args[0]
    assert "%s" in sql and "NVDA" not in sql
    assert params == ("NVDA",)


def test_la_connessione_torna_al_pool_anche_se_la_query_esplode():
    """
    Il pool ne ha da 2 a 10. Una connessione non restituita per ogni errore e
    il backend muore dopo dieci errori, che e' gia' successo in agosto 2026
    per un altro motivo.
    """
    conn, cur = _conn([], COLONNE)
    cur.execute.side_effect = RuntimeError("query rotta")
    rilasciata = MagicMock()
    with patch("database._get_connection", return_value=conn), \
         patch("database._release_connection", rilasciata):
        try:
            database._leggi("SELECT 1", ())
        except RuntimeError:
            pass
    assert rilasciata.called, "la connessione non e' tornata al pool"
    assert cur.close.called, "il cursore e' rimasto aperto"


def test_get_data_e_get_all_data_passano_di_qui():
    import inspect
    for fn in (database.SuperNewsAnalyzer.get_data,
               database.SuperNewsAnalyzer.get_all_data):
        sorgente = inspect.getsource(fn)
        assert "_leggi(" in sorgente, fn.__name__
        assert "read_sql" not in sorgente, (
            f"{fn.__name__} e' tornata a pd.read_sql: l'avviso torna con lei")
