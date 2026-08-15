"""
Test della serializzazione: niente NaN, niente colonne di lavoro.

IL GUASTO DEL 15 AGOSTO 2026

`get_news` faceva `SELECT *` e passava tutto al serializzatore. Ha funzionato
finché le colonne erano quelle previste. Poi `calibra.py` ha aggiunto
`sentiment_2` e `sentiment_3` alla tabella di produzione per confrontare i due
valutatori: colonne REAL, quindi NULL sulle righe senza secondo parere, quindi
NaN una volta lette da pandas.

NaN non e' JSON valido. La risposta andava in errore, e siccome l'errore non
porta con se' le intestazioni CORS il browser mostrava "Failed to fetch", cioe'
un guasto di rete. Nella watchlist i titoli fuori classifica restavano con un
trattino, e da li' non c'era modo di risalire alla causa.

Il difetto vero non e' stato aggiungere due colonne: e' che l'API esponeva
tutto quello che c'era nella tabella, quindi qualunque colonna aggiunta per un
esperimento poteva rompere una pagina.
"""
import numpy as np
import pandas as pd

from payload import righe_per_json


def _df(**extra):
    base = {"id": [1, 2], "ticker": ["BTC-USD"] * 2,
            "title": ["uno", "due"], "sentiment": [0.4, 0.2]}
    base.update(extra)
    return pd.DataFrame(base)


def test_le_colonne_di_lavoro_non_escono_dall_api():
    righe = righe_per_json(_df(sentiment_2=[0.3, None],
                                sentiment_3=[None, None],
                                score_source_2=["llm2", None],
                                score_source_3=[None, None]))
    for r in righe:
        for c in ("sentiment_2", "sentiment_3", "score_source_2", "score_source_3"):
            assert c not in r, f"{c} e' finita nella risposta"


def test_nessun_nan_sopravvive():
    """
    NaN passa il serializzatore di FastAPI e arriva al browser come token non
    parsabile, oppure fa fallire la risposta. In tutti e due i casi la pagina
    si rompe senza dire perche'.
    """
    righe = righe_per_json(_df(sentiment=[0.4, np.nan],
                                lingua=[None, "tur"],
                                relevance_score=[np.nan, 1.0]))
    for r in righe:
        for k, v in r.items():
            assert v is None or v == v, f"{k} e' NaN"


def test_i_valori_veri_restano_intatti():
    """La protezione non deve svuotare le colonne buone."""
    righe = righe_per_json(_df(lingua=["tur", "rus"]))
    assert righe[0]["sentiment"] == 0.4
    assert righe[1]["lingua"] == "rus"


def test_una_colonna_di_lavoro_che_non_c_e_non_fa_saltare_niente():
    """
    Serve sugli ambienti dove `calibra.py` non e' mai stato lanciato: la
    tabella non ha quelle colonne e la funzione deve passare oltre.
    """
    righe = righe_per_json(_df())
    assert len(righe) == 2 and righe[0]["ticker"] == "BTC-USD"


def test_il_risultato_e_davvero_serializzabile():
    """La prova finale: se json.dumps passa, il browser riceve qualcosa."""
    import json
    righe = righe_per_json(_df(sentiment_2=[np.nan, np.nan],
                                lingua=[None, None],
                                summary=[None, "x"]))
    json.dumps(righe)   # deve non sollevare
