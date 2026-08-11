"""
giornaliero.py — Da elenco di notizie a una riga per giorno, con l'incertezza.

PERCHÉ STA IN UN FILE SUO E NON DENTRO main.py

Ci è stato, per mezz'ora, e ha rotto tredici test. Non per un difetto di
calcolo: `tests/test_auth.py` importa `main` DENTRO un `patch("database.get_pool")`,
così l'app nasce con il database finto. Un file di test che importa `main` al
primo rigo lo fa entrare nella cache dei moduli prima che quel patch esista, e
da quel momento l'app vera prova a connettersi a Supabase durante lo startup.

La regola che ne esce vale oltre questo caso: una funzione pura non va tenuta
nel file che possiede l'applicazione, altrimenti per provarla bisogna tirarsi
dietro FastAPI, il pool di connessioni e l'ordine di importazione.

LA MEDIA DEL GIORNO NON VIAGGIA PIÙ DA SOLA

L'11 agosto 2026 un utente ha chiesto perché un articolo su NVDA valesse -0.9.
Andando a guardare, lo stesso giorno l'archivio conteneva anche un +0.7 sullo
stesso identico fatto (Musk che compra chip Nvidia), letto da un giornale
diverso. La media del 7 agosto usciva +0.2098 e il conflitto spariva senza
lasciare traccia.

Servono DUE numeri accanto alla media, e dicono cose diverse:

    errore  = quanto bene conosciamo la media       (dev / radice di n)
    dev     = quanto le notizie sono in disaccordo  (deviazione standard)

Sul 7 agosto NVDA: 61 notizie, media +0.210, errore 0.061, dev 0.476, con i
singoli punteggi da -0.9 a +0.8. Cioè la media era conosciuta bene E le notizie
erano in totale disaccordo, tutte e due le cose insieme. Con un numero solo non
si poteva dire.

PERCHÉ NON C'È UN FLAG "GIORNO CONTRADDITTORIO"

È stato provato e misurato prima di scartarlo. Su 72 giorni-ticker con almeno
due notizie si accendeva nel 77,8% dei casi a soglia 0.3, nel 58,3% a soglia
0.5 e nel 22,2% a soglia 0.7. Il disaccordo è la norma, non l'eccezione: la
deviazione mediana di un giorno è 0.371, più larga della media tipica. Un
semaforo acceso sei giorni su dieci è arredamento. Il numero grezzo dice di più
e non mente.
"""


def aggrega_giornaliero(df) -> list[dict]:
    """
    Una riga per giorno di calendario, con media, conteggio, disaccordo, errore.

    `df` deve avere le colonne `published_date` (datetime) e `sentiment`.
    """
    giornaliero = (
        df.set_index("published_date")["sentiment"]
        .resample("D")
        .agg(["mean", "count", "std"])
        .reset_index()
    )
    giornaliero.columns = ["date", "sentiment", "n", "dev"]
    giornaliero["date"] = giornaliero["date"].dt.strftime("%Y-%m-%d")

    # std di pandas ha ddof=1, quindi con una notizia sola è NaN. È giusto così:
    # una notizia non è in disaccordo con nessuno, ma non è nemmeno una misura
    # di dispersione, e mettere zero direbbe "sono tutti d'accordo".
    giornaliero["errore"] = giornaliero["dev"] / giornaliero["n"] ** 0.5

    # Giorni SENZA news → null, non 0: uno zero è un giudizio ("neutro"),
    # l'assenza di notizie non lo è. Il frontend salta i null (barre grigie,
    # esclusi da media, MA7, giorni neutri e correlazione). NaN → None perché
    # NaN non è JSON valido e arriverebbe al browser come token non parsabile.
    _mask = giornaliero["sentiment"].notna()
    giornaliero["sentiment"] = giornaliero["sentiment"].round(4).astype(object).where(_mask, None)
    giornaliero["n"] = giornaliero["n"].astype(int)
    for col in ("dev", "errore"):
        giornaliero[col] = (giornaliero[col].round(4).astype(object)
                            .where(giornaliero[col].notna(), None))

    return giornaliero.to_dict(orient="records")
