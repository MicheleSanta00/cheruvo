"""
payload.py — Da DataFrame a JSON, senza sorprese.

PERCHE' STA IN UN FILE SUO

Per lo stesso motivo di giornaliero.py, e la lezione e' stata imparata due
volte nello stesso giorno: una funzione pura non va tenuta dentro main.py.
`tests/test_auth.py` importa `main` DENTRO un patch("database.get_pool"), e un
file di test che importa `main` al primo rigo lo fa entrare nella cache dei
moduli prima che quel patch esista. Tredici test finiscono per aprire una
connessione vera a Supabase durante lo startup.
"""


def righe_per_json(df) -> list[dict]:
    """
    Da DataFrame a lista di dizionari serializzabili: senza NaN e senza le
    colonne di lavoro.

    IL GUASTO DEL 15 AGOSTO 2026

    `get_news` fa `SELECT *` e passa tutto al serializzatore. Ha funzionato
    finché le colonne erano quelle previste. Poi `calibra.py` ha aggiunto
    `sentiment_2` e `sentiment_3` alla tabella per confrontare i due
    valutatori: colonne REAL, quindi NULL sulle righe senza secondo parere,
    quindi **NaN** una volta lette da pandas.

    NaN non è JSON valido. La risposta andava in errore, e siccome l'errore non
    porta con sé le intestazioni CORS il browser non vedeva un 500 ma un
    "Failed to fetch", cioè un guasto di rete. Nella watchlist i titoli fuori
    classifica restavano con un trattino al posto del punteggio, e da lì non
    c'era modo di risalire alla causa.

    Due protezioni invece di una, perché i difetti sono diversi:

      1. le colonne di LAVORO non escono dall'API. Servono a misurare, non a
         chi guarda il sito, e una colonna aggiunta domani per un esperimento
         non deve poter rompere una pagina.
      2. qualunque NaN residuo diventa None. Vale anche per le colonne
         previste: `sentiment` può essere NULL su una riga vecchia.
    """
    import numpy as np

    DA_NON_ESPORRE = ("sentiment_2", "sentiment_3",
                      "score_source_2", "score_source_3")
    d = df.drop(columns=[c for c in DA_NON_ESPORRE if c in df.columns])
    return d.replace({np.nan: None}).to_dict(orient="records")
