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


def _rispetta_rate_limit():
    global _ultima_chiamata
    attesa = PAUSA_MINIMA - (time.time() - _ultima_chiamata)
    if attesa > 0:
        time.sleep(attesa)
    _ultima_chiamata = time.time()

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
    "UCG.MI": "UniCredit", "STM.MI": "STMicroelectronics", "RACE.MI": "Ferrari",
    "LVMH.PA": "LVMH", "SAP.DE": "SAP", "ASML.AS": "ASML", "SHEL.L": "Shell",
}

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


def fetch_gdelt(ticker: str, nome: str | None = None,
                max_items: int = 100, timespan: str = "4d") -> list[dict]:
    """
    News recenti su un ticker da GDELT, già filtrate per lingua e pertinenza.
    Ritorna una lista di dict pronti per il salvataggio (stesso schema delle
    altre fonti). Non solleva eccezioni: in caso di errore ritorna lista vuota.
    """
    news: list[dict] = []
    try:
        # Ticker fuori mappa e senza nome fornito: risolvilo una volta sola,
        # così query e parole chiave usano lo stesso nome.
        if ticker.upper() not in TERMINE_QUERY and not nome:
            nome = _nome_da_yfinance(ticker)
        termine = _termine_query(ticker, nome)
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
        varianti = [termine]
        if lingua_locale != "English":
            varianti.append(f"{termine} sourcelang:{lingua_locale.lower()}")

        articoli = []
        for q in varianti:
            _rispetta_rate_limit()
            resp = requests.get(GDELT_URL, params={
                "query": q,                   # UN token, MAI tra virgolette
                "mode": "artlist",
                "format": "json",
                "maxrecords": max_items,
                "timespan": timespan,
                "sort": "datedesc",
            }, timeout=15, headers={"User-Agent": _UA})
            resp.raise_for_status()

            # GDELT a volte risponde 200 con corpo vuoto (rate limit)
            testo = (resp.text or "").strip()
            if not testo:
                logger.warning("GDELT %s (query='%s'): risposta vuota "
                               "(probabile rate limit)", ticker, q)
                continue
            articoli.extend((resp.json() or {}).get("articles", []) or [])

        if not articoli:
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
            news.append({
                "source": f"GDELT · {a.get('domain', 'n/d')}",
                "title": titolo,
                "summary": "",   # GDELT non fornisce il sommario
                "published_date": _fmt_data(a.get("seendate", "")),
                "url": a.get("url", ""),
                "sentiment": _vader(titolo),
            })
        logger.info("GDELT %s (query='%s', %d interrogazioni, %d articoli grezzi): "
                    "%d tenute, %d scartate",
                    ticker, termine, len(varianti), len(articoli), len(news), scartati)
    except Exception as e:
        logger.error("GDELT %s error: %s", ticker, e)
    return news
