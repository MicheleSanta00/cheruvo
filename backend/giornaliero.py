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


def chiave_titolo(t) -> str:
    """
    Titolo ridotto all'osso, per riconoscere la stessa notizia ripresa altrove.

    Minuscole, via la punteggiatura, spazi normalizzati. Non riconosce le
    riscritture ("Intel punta a una vendita da 15 miliardi" resta diversa da
    "Intel targets $15 billion stock sale"), quindi i doppioni che trova sono
    un MINIMO: quelli veri sono almeno tanti.
    """
    import re
    if not isinstance(t, str):
        return ""
    t = re.sub(r"[^\w\s]", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()[:90]


def aggrega_giornaliero(df) -> list[dict]:
    """
    Una riga per giorno di calendario, con media, conteggio, disaccordo, errore.

    `df` deve avere le colonne `published_date` (datetime), `sentiment` e
    `title`.

    UNA NOTIZIA, UN VOTO

    L'11 agosto 2026, misurando un campione di 300 righe, 61 erano lo stesso
    lancio d'agenzia: "Intel targets $15 billion stock sale after rally",
    ripreso da sessantuno testate. Il 37% del campione erano riprese.

    `save_news` scarta i doppioni per (titolo, TESTATA), quindi la stessa
    notizia ripresa da sessantuno giornali entra sessantuno volte. È voluto:
    per l'attenzione sessantuno riprese sono un segnale vero, ed è esattamente
    quello che il rilevatore di anomalie deve vedere.

    Ma la MEDIA le contava come sessantuno giudizi indipendenti, e non lo sono:
    è un giudizio solo, moltiplicato da quanto la notizia è stata sindacata.
    Una giornata finiva colorata da quale lancio era stato ripreso di più.

    Quindi qui le riprese vengono FUSE prima della media: stesso giorno e
    stesso titolo diventano una voce sola, col punteggio medio fra le copie.
    Il conteggio delle riprese non si perde, viaggia in `riprese`, perché è il
    dato che serve a chi guarda l'attenzione invece del giudizio.
    """
    d = df.copy()
    d["_giorno"] = d["published_date"].dt.floor("D")
    d["_chiave"] = d["title"].map(chiave_titolo) if "title" in d.columns else ""

    # Una riga senza titolo utilizzabile non si può confrontare con niente:
    # resta una notizia a sé, invece di fondersi con tutte le altre senza
    # titolo e sparire.
    vuote = d["_chiave"] == ""
    d.loc[vuote, "_chiave"] = ["§" + str(i) for i in range(int(vuote.sum()))]

    distinte = (d.groupby(["_giorno", "_chiave"], as_index=False)
                 .agg(sentiment=("sentiment", "mean"),
                      copie=("sentiment", "size")))

    giornaliero = (
        distinte.set_index("_giorno")
        .resample("D")
        .agg(sentiment=("sentiment", "mean"),
             n=("sentiment", "count"),
             dev=("sentiment", "std"),
             copie=("copie", "sum"))
        .reset_index()
    )
    giornaliero.columns = ["date", "sentiment", "n", "dev", "copie"]
    giornaliero["date"] = giornaliero["date"].dt.strftime("%Y-%m-%d")

    # Quante righe erano riprese di una notizia già contata.
    giornaliero["riprese"] = (giornaliero["copie"] - giornaliero["n"]).astype(int)
    giornaliero = giornaliero.drop(columns=["copie"])

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
    giornaliero["riprese"] = giornaliero["riprese"].astype(int)
    for col in ("dev", "errore"):
        giornaliero[col] = (giornaliero[col].round(4).astype(object)
                            .where(giornaliero[col].notna(), None))

    return giornaliero.to_dict(orient="records")
