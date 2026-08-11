"""
gdelt_source.py — Fonte news GDELT, condivisa tra il fetch on-demand
(quick_fetch.py) e il cron (data/database.py).

Perché GDELT: è l'unica fonte news con licenza davvero libera anche per uso
commerciale. Dalla loro pagina dati: i dataset sono rilasciati per "unlimited
and unrestricted use for any academic, commercial, or governmental use of any
kind without fee", con diritto di ridistribuzione. Restiamo comunque su
titolo + link + attribuzione alla testata, senza copiare il testo integrale.

Note dai test dal vivo (importanti, non rimuovere):
  1. Le VIRGOLETTE nella query fanno tornare l'API vuota: niente frasi tra
     virgolette, si interroga con UN token distintivo (es. "Nvidia", "Enel").
  2. GDELT applica un RATE LIMIT stretto: chiamate ravvicinate vengono
     rifiutate con risposta vuota. Chi cicla più ticker DEVE mettere una pausa
     (vedi PAUSA_CONSIGLIATA) tra una chiamata e l'altra.
  3. La ricerca è su tutto il testo mondiale: torna anche rumore (altre
     aziende, lingue diverse). Per questo filtriamo per lingua e per presenza
     del nome nel titolo (_e_pertinente).
"""
import logging
import re
import time
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

_WSNORM = re.compile(r"\s+")

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
PAUSA_MINIMA = 5.0         # secondi tra due chiamate GDELT (rate limit)
_UA = "Cheruvo/1.0 (+https://cheruvo.com)"

# Autolimitatore: GDELT rifiuta chiamate ravvicinate rispondendo vuoto.
# Teniamo il timestamp dell'ultima chiamata a livello di modulo e, se serve,
# aspettiamo la differenza. Così QUALUNQUE chiamante (updater che cicla 12
# ticker, auto-fetch di più utenti) è protetto senza doverci pensare.
_ultima_chiamata = 0.0


# Pausa effettiva: parte da PAUSA_MINIMA e si allunga da sola ogni volta che
# GDELT risponde 429. Serve perché il nostro limitatore vale per UN processo,
# mentre a bussare siamo in due contemporaneamente: il backend su Render (fetch
# a richiesta dell'utente) e il cron su GitHub Actions. Nessuno dei due sa cosa
# sta facendo l'altro, quindi l'unico segnale reale è il rifiuto di GDELT.
_pausa_corrente = PAUSA_MINIMA
PAUSA_MASSIMA = 20.0          # tetto della pausa fra chiamate
ATTESA_MASSIMA_RIPROVA = 8.0  # tetto dell'attesa aggiuntiva su un 429


def _rispetta_rate_limit():
    global _ultima_chiamata
    attesa = _pausa_corrente - (time.time() - _ultima_chiamata)
    if attesa > 0:
        time.sleep(attesa)
    _ultima_chiamata = time.time()


def _rallenta():
    """Dopo un 429: raddoppia la pausa per il resto della vita del processo."""
    global _pausa_corrente
    _pausa_corrente = min(_pausa_corrente * 2, PAUSA_MASSIMA)
    logger.warning("GDELT ha risposto 429: pausa portata a %.0fs", _pausa_corrente)


def _fmt_finestra(d: datetime) -> str:
    """GDELT vuole le date come YYYYMMDDHHMMSS, sempre in UTC."""
    return d.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S")


def _interroga(q: str, max_items: int, timespan: str, tentativi: int = 2,
               finestra: tuple[datetime, datetime] | None = None) -> list[dict]:
    """
    Una interrogazione a GDELT. Non solleva MAI: se va male ritorna [].
    Sul 429 aspetta e riprova, perché quel codice non significa "non ci sono
    notizie" ma "hai bussato troppo presto", e trattarlo come un errore
    definitivo faceva perdere il giro a quel ticker fino a sei ore dopo.

    `finestra` serve alla ricostruzione dello storico: al posto di "le ultime
    N ore" chiede un intervallo preciso fra due date. GDELT accetta i due
    modi ma non insieme, quindi o l'uno o l'altro.
    """
    for tentativo in range(tentativi):
        try:
            _rispetta_rate_limit()
            parametri = {
                "query": q,                   # UN token, MAI tra virgolette
                "mode": "artlist",
                "format": "json",
                "maxrecords": max_items,
                "sort": "datedesc",
            }
            if finestra:
                parametri["startdatetime"] = _fmt_finestra(finestra[0])
                parametri["enddatetime"] = _fmt_finestra(finestra[1])
            else:
                parametri["timespan"] = timespan
            resp = requests.get(GDELT_URL, params=parametri,
                                timeout=15, headers={"User-Agent": _UA})

            if resp.status_code == 429:
                _rallenta()
                if tentativo < tentativi - 1:
                    # Attesa CON UN TETTO. Prima era _pausa_corrente * (n+1),
                    # che con la pausa a 30 secondi diventava 30 e poi 60: due
                    # minuti buttati su un ticker solo. Con quaranta ticker il
                    # cron sforava i 12 minuti del workflow e veniva ucciso a
                    # metà, quindi non salvava NIENTE e non girava nemmeno il
                    # controllo di salute. Meglio saltare un ticker che perdere
                    # tutto il giro.
                    time.sleep(min(_pausa_corrente, ATTESA_MASSIMA_RIPROVA))
                    continue
                logger.warning("GDELT '%s': 429 anche dopo %d tentativi, salto",
                               q, tentativi)
                return []

            resp.raise_for_status()

            # GDELT a volte risponde 200 con corpo vuoto (altra faccia del
            # rate limit): non è un errore, ma non c'è nulla da leggere.
            testo = (resp.text or "").strip()
            if not testo:
                logger.warning("GDELT '%s': risposta vuota", q)
                return []
            return (resp.json() or {}).get("articles", []) or []

        except Exception as e:
            logger.warning("GDELT '%s' tentativo %d/%d fallito: %s",
                           q, tentativo + 1, tentativi, e)
            if tentativo < tentativi - 1:
                time.sleep(2)
    return []

# Lingua locale attesa per borsa, oltre all'inglese
_LINGUA_BORSA = {"MI": "Italian", "PA": "French", "DE": "German",
                 "AS": "Dutch", "MC": "Spanish", "L": "English"}

# Termine di ricerca migliore per i ticker seguiti: UN token distintivo, senza
# virgolette. Curato a mano perché è il 90% del traffico e la qualità dipende
# tutta da qui. Per i ticker fuori mappa si ripiega sul nome società.
TERMINE_QUERY = {
    "NVDA": "Nvidia", "AAPL": "Apple", "TSLA": "Tesla", "MSFT": "Microsoft",
    "GOOGL": "Google", "META": "Meta", "AMD": "AMD", "AMZN": "Amazon",
    "MU": "Micron", "INTC": "Intel", "GE": "GE",
    "ENI.MI": "Eni", "ENEL.MI": "Enel", "ISP.MI": "Intesa",
    "UCG.MI": "UniCredit", "STMMI.MI": "STMicroelectronics", "RACE.MI": "Ferrari",
    "LVMH.PA": "LVMH", "SAP.DE": "SAP", "ASML.AS": "ASML", "SHEL.L": "Shell",
    # Criptovalute. Misurato il 4 agosto 2026: la query "Bitcoin" su un solo
    # giorno rende 8 articoli di mercato veri su 15, contro 1 su 20 di "Eni".
    # È la stessa GDELT con la stessa licenza: cambia solo che la stampa
    # specializzata (CoinDesk e simili) è indicizzata bene, quella finanziaria
    # italiana no.
    "BTC-USD": "Bitcoin", "ETH-USD": "Ethereum", "SOL-USD": "Solana",
    "XRP-USD": "XRP", "ADA-USD": "Cardano", "DOGE-USD": "Dogecoin",
    "AVAX-USD": "Avalanche", "LINK-USD": "Chainlink", "DOT-USD": "Polkadot",
    "MATIC-USD": "Polygon", "LTC-USD": "Litecoin", "UNI-USD": "Uniswap",
    "ATOM-USD": "Cosmos", "XLM-USD": "Stellar", "NEAR-USD": "NEAR",
    "APT-USD": "Aptos", "ARB-USD": "Arbitrum", "OP-USD": "Optimism",
    "SHIB-USD": "Shiba", "BCH-USD": "Bitcoin Cash",
}


def e_crypto(ticker: str) -> bool:
    """Le crypto su Yahoo hanno il suffisso -USD (BTC-USD, ETH-USD)."""
    return (ticker or "").upper().endswith("-USD")

# Suffissi societari: inutili come parole chiave e fonte di falsi positivi
_SUFFISSI = {"inc", "corp", "corporation", "spa", "plc", "nv", "sa", "ag",
             "ltd", "limited", "group", "holding", "holdings", "company",
             "co", "the", "se", "&"}


_nomi_cache: dict[str, str | None] = {}


def _nome_da_yfinance(ticker: str) -> str | None:
    """
    Nome societario per i ticker fuori mappa (es. ADBE cercato dall'auto-fetch).
    Cache in memoria: una chiamata yfinance per ticker per processo.
    """
    if ticker in _nomi_cache:
        return _nomi_cache[ticker]
    nome = None
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info or {}
        nome = (info.get("longName") or info.get("shortName") or "").strip() or None
    except Exception as e:
        logger.info("GDELT: nome societario non risolto per %s (%s)", ticker, e)
    _nomi_cache[ticker] = nome
    return nome


def _termine_query(ticker: str, nome: str | None) -> str:
    """Il singolo token con cui interrogare GDELT."""
    t = ticker.upper()
    if t in TERMINE_QUERY:
        return TERMINE_QUERY[t]
    # Fuori mappa: primo token "lungo" del nome società, o il base del ticker
    nome = nome or _nome_da_yfinance(ticker)
    if nome:
        for p in nome.split():
            pulito = p.strip(",.'\"").replace(".", "")
            if len(pulito) > 3 and pulito.lower() not in _SUFFISSI:
                return pulito
    return ticker.split(".")[0]


def _parole_chiave(ticker: str, nome: str | None) -> list[str]:
    """
    Parole che un titolo pertinente dovrebbe contenere. I punti vengono tolti
    (così "S.p.A." -> "spa" e finisce tra i suffissi da scartare) e il confronto
    sarà su parola intera, per non far combaciare "eni" dentro "beni".
    """
    parole: list[str] = []
    fonte = f"{_termine_query(ticker, nome)} {nome or ''}"
    for p in fonte.split():
        p = p.strip(",.'\"").lower().replace(".", "")
        if p and p not in _SUFFISSI and len(p) > 2 and p not in parole:
            parole.append(p)
    base = ticker.split(".")[0].lower()
    if len(base) > 2 and base not in parole:
        parole.append(base)
    return parole or [base]


def _e_pertinente(titolo: str, chiavi: list[str]) -> bool:
    """Vero se il titolo contiene una delle chiavi come parola intera."""
    t = titolo.lower()
    return any(re.search(rf"\b{re.escape(k)}\b", t) for k in chiavi)


def _vader(titolo: str) -> float:
    """Score di ripiego sul titolo (il refine LLM lo sovrascrive più a valle)."""
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        s = SentimentIntensityAnalyzer().polarity_scores(titolo or "")["compound"]
        return round(max(-1.0, min(1.0, s)), 4)
    except Exception:
        return 0.0


def _fmt_data(seendate: str) -> str | None:
    # GDELT usa il formato "YYYYMMDDThhmmssZ"
    if not seendate or len(seendate) < 8:
        return None
    try:
        from dateutil import parser as dp
        return dp.parse(seendate).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        s = seendate
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]} 00:00:00"


def _da_articolo(a: dict) -> dict:
    """Traduce un articolo GDELT nello schema usato dal resto del progetto."""
    titolo = (a.get("title") or "").strip()
    return {
        "source": f"GDELT · {a.get('domain', 'n/d')}",
        "title": titolo,
        "summary": "",   # GDELT non fornisce il sommario
        "published_date": _fmt_data(a.get("seendate", "")),
        "url": a.get("url", ""),
        "sentiment": _vader(titolo),
    }


# ── Raccolta per MERCATO ──────────────────────────────────────────────────
#
# Il vincolo di GDELT non è quante notizie esistono, è quante volte puoi
# chiedere: fra una chiamata e l'altra serve una pausa, e chi sfora si prende
# un 429. Con una interrogazione per titolo, sei società italiane costavano
# dodici chiamate. Chiedendo invece "(Eni OR Enel OR Ferrari OR ...)" una volta
# sola e smistando gli articoli in locale, le stesse sei società ne costano due.
#
# Si applica SOLO alle borse non anglofone, che sono quelle dove la raccolta
# oggi non funziona. I titoli americani continuano ad avere la loro
# interrogazione dedicata, perché lì funziona già e ognuno merita per intero
# i 250 posti disponibili: NVDA da solo ne riempirebbe più di AMZN e MU messi
# insieme, e accorpandoli i più piccoli sparirebbero.
_cache_mercato: dict[tuple, tuple[float, list[dict]]] = {}
CACHE_MERCATO_S = 1800     # 30 minuti: il cron gira ogni 6 ore, il web molto più spesso
_or_supportato: bool | None = None   # None = non ancora scoperto


def _ticker_del_mercato(lingua: str) -> list[str]:
    """
    I ticker che appartengono a un mercato. Le criptovalute sono un mercato a
    sé: non hanno una borsa e scambiano ovunque, ma i loro nomi (Bitcoin,
    Ethereum, Solana) sono distintivi come pochi altri, quindi il
    raggruppamento con OR funziona su di loro meglio che su qualsiasi altra
    cosa. Venti monete costano due chiamate invece di venti.
    """
    if lingua == "Crypto":
        return [tk for tk in TERMINE_QUERY if e_crypto(tk)]
    return [tk for tk in TERMINE_QUERY
            if "." in tk and _LINGUA_BORSA.get(tk.split(".")[-1]) == lingua]


def _articoli_del_mercato(lingua: str, max_items: int, timespan: str,
                          finestra: tuple[datetime, datetime] | None = None) -> list[dict]:
    """
    Articoli grezzi per tutte le società di un mercato, con una interrogazione
    sola (o due: lingua locale e inglese). Il risultato resta in cache per
    mezz'ora, così i titoli successivi dello stesso mercato non ripagano il
    costo della chiamata.
    """
    global _or_supportato
    adesso = time.time()
    # La chiave comprende la finestra temporale, non solo il mercato. Senza,
    # la ricostruzione dello storico riempirebbe tutte le settimane con gli
    # articoli della prima: stessa lingua, stessa chiave, cache servita.
    chiave = (lingua, (_fmt_finestra(finestra[0]), _fmt_finestra(finestra[1]))
              if finestra else timespan)
    if chiave in _cache_mercato:
        quando, articoli = _cache_mercato[chiave]
        if adesso - quando < CACHE_MERCATO_S:
            return articoli

    tickers = _ticker_del_mercato(lingua)
    if not tickers:
        return []
    termini = sorted({TERMINE_QUERY[tk] for tk in tickers})
    gruppo = "(" + " OR ".join(termini) + ")"

    # Sulle crypto la lingua è una sola (inglese) e la seconda interrogazione
    # sarebbe identica alla prima: non si fa.
    interrogazioni = ([f"{gruppo} sourcelang:english"] if lingua == "Crypto"
                      else [f"{gruppo} sourcelang:{lingua.lower()}",
                            f"{gruppo} sourcelang:english"])
    articoli = []
    for q in interrogazioni:
        articoli.extend(_interroga(q, max_items, timespan, finestra=finestra))

    # Non ho potuto verificare da fuori se GDELT accetta l'OR fra parentesi:
    # ero io stesso finito sotto rate limit mentre lo provavo. Invece di
    # tirare a indovinare, il codice se ne accorge da solo al primo giro e lo
    # scrive nel log. Se non funziona si torna al metodo per titolo, che è
    # meno efficiente ma sicuro.
    if not articoli:
        if _or_supportato is None:
            logger.warning("GDELT mercato %s: la query raggruppata non ha reso "
                           "nulla. Torno al metodo per singolo titolo.", lingua)
        _or_supportato = False
        _cache_mercato[chiave] = (adesso, [])
        return []

    if _or_supportato is None:
        logger.info("GDELT: query raggruppate supportate, %d titoli con 2 chiamate",
                    len(tickers))
    _or_supportato = True
    logger.info("GDELT mercato %s (%d società, 2 interrogazioni): %d articoli grezzi",
                lingua, len(tickers), len(articoli))
    _cache_mercato[chiave] = (adesso, articoli)
    return articoli


def fetch_gdelt(ticker: str, nome: str | None = None,
                max_items: int = 250, timespan: str = "7d",
                finestra: tuple[datetime, datetime] | None = None,
                usa_paniere: bool = True) -> list[dict]:
    """
    News recenti su un ticker da GDELT, già filtrate per lingua e pertinenza.
    Ritorna una lista di dict pronti per il salvataggio (stesso schema delle
    altre fonti). Non solleva eccezioni: in caso di errore ritorna lista vuota.

    max_items 250 è il tetto consentito da GDELT e non costa chiamate in più.
    timespan 7 giorni invece di 4: sui titoli europei le notizie sono rare e
    una finestra stretta le perdeva soltanto. Il salvataggio scarta i doppioni,
    quindi allargare non produce righe ripetute.
    """
    news: list[dict] = []
    try:
        # Ticker fuori mappa e senza nome fornito: risolvilo una volta sola,
        # così query e parole chiave usano lo stesso nome.
        if ticker.upper() not in TERMINE_QUERY and not nome:
            nome = _nome_da_yfinance(ticker)
        termine = _termine_query(ticker, nome)

        # Se il nome societario non si è risolto, _termine_query ripiega sulla
        # sigla di borsa (EZJ.L -> "EZJ"). Cercare "EZJ" sui giornali non porta
        # a nulla: nessun articolo su easyJet la chiama così. Meglio non
        # sprecare una chiamata, visto che GDELT ce ne concede poche.
        base = ticker.split(".")[0].upper()
        if ticker.upper() not in TERMINE_QUERY and termine.upper() == base:
            logger.info("GDELT %s: nome societario non risolto, cercherei '%s' "
                        "che non compare nei giornali. Salto.", ticker, base)
            return []

        chiavi = _parole_chiave(ticker, nome)
        borsa = ticker.split(".")[-1] if "." in ticker else ""
        lingua_locale = _LINGUA_BORSA.get(borsa, "English")
        lingue = {"English", lingua_locale}

        # Per le borse non anglofone facciamo una seconda interrogazione
        # ristretta alla lingua locale.
        #
        # Perché: la query nuda cerca in tutto il mondo e per un nome corto
        # come "Eni" torna quasi solo rumore (verificato dal vivo: su 20
        # risultati, 1 solo parlava davvero della società, gli altri erano
        # articoli rumeni, arabi e nigeriani). Il filtro a valle li butta, ma
        # intanto hanno consumato tutti i 100 posti disponibili. Con
        # sourcelang: i 100 posti sono già tutti nella lingua giusta, e infatti
        # escono pezzi che la query nuda non restituiva mai.
        #
        # sourcelang: si scrive DA SOLO accanto al termine. Non funziona né
        # dentro parentesi né in OR con un'altra lingua (provato: risposta
        # vuota), da qui la seconda chiamata invece di una query sola.
        # Borsa non anglofona e società in mappa: prova prima il paniere del
        # mercato, che di solito è già stato scaricato per un altro titolo e
        # quindi non costa nessuna chiamata.
        articoli = []
        via = "titolo"
        mercato_di = ("Crypto" if e_crypto(ticker)
                      else lingua_locale if lingua_locale != "English" else None)
        # Il paniere di mercato fa risparmiare chiamate ma DILUISCE: le 250
        # posizioni che GDELT concede a una interrogazione vengono spartite fra
        # venti monete, e a Bitcoin ne restano una manciata. Misurato in
        # produzione: "250 articoli grezzi, 2 tenute, 248 scartate".
        #
        # Per il fetch quotidiano il compromesso conviene, perché venti monete
        # con due chiamate invece che con venti è l'unico modo di starci dentro.
        # Per ricostruire lo storico di UN titolo no: lì il risparmio non serve
        # a niente e la diluizione è esattamente il problema, perché produce
        # tanti giorni con due o tre notizie, cioè sotto la soglia oltre la
        # quale una media vale qualcosa.
        if usa_paniere and mercato_di and ticker.upper() in TERMINE_QUERY:
            articoli = _articoli_del_mercato(mercato_di, max_items, timespan, finestra)
            if articoli:
                via = "mercato"

        if not articoli:
            varianti = [termine]
            if lingua_locale != "English":
                varianti.append(f"{termine} sourcelang:{lingua_locale.lower()}")
            # Ogni interrogazione è indipendente: se la prima fallisce la
            # seconda ci prova lo stesso, e quello che è già arrivato resta.
            for q in varianti:
                articoli.extend(_interroga(q, max_items, timespan, finestra=finestra))

        if not articoli:
            logger.info("GDELT %s (query='%s'): nessun articolo", ticker, termine)
            return []

        scartati = 0
        titoli_visti: set[str] = set()
        for a in articoli:
            titolo = (a.get("title") or "").strip()
            if not titolo:
                continue
            if a.get("language") not in lingue:
                scartati += 1
                continue
            if not _e_pertinente(titolo, chiavi):
                scartati += 1
                continue
            # Dedup per TITOLO, non solo per URL: lo stesso pezzo sindacato
            # esce su decine di domini diversi (osservato: 10+ copie identiche
            # dai siti delle radio iHeart). Senza questo, una singola storia
            # peserebbe dieci volte nella media del sentiment.
            chiave_titolo = _WSNORM.sub(" ", titolo.lower()).strip()
            if chiave_titolo in titoli_visti:
                scartati += 1
                continue
            titoli_visti.add(chiave_titolo)
            news.append(_da_articolo(a))
        logger.info("GDELT %s (via %s, query='%s', %d articoli grezzi): "
                    "%d tenute, %d scartate",
                    ticker, via, termine, len(articoli), len(news), scartati)
    except Exception as e:
        logger.error("GDELT %s error: %s", ticker, e)
    return news
