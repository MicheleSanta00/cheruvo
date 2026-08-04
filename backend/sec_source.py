"""
sec_source.py — Documenti ufficiali depositati alla SEC.

Perché esiste: è l'unica fonte su cui non serve chiedere il permesso a nessuno.
I documenti SEC sono atti pubblici del governo statunitense, quindi in pubblico
dominio, e l'ente stesso ne incoraggia il riuso. Nessuna licenza, nessuna email
da mandare, nessun rischio di vedersi revocare una chiave.

Cosa aggiunge davvero: fatti, non commenti. Un 8-K significa che è successo
qualcosa di rilevante (risultati, acquisizioni, cambi al vertice), un 10-Q sono
i conti trimestrali. Il valore per il sentiment è più modesto di un articolo
scritto da un giornalista, perché il linguaggio è burocratico, ma la
pertinenza è totale: riguarda sempre e solo quella società.

Vale solo per i titoli USA: le società europee non depositano alla SEC.

Regole della SEC da rispettare (sono nelle loro condizioni d'uso):
  - User-Agent con un contatto reale, altrimenti bloccano
  - massimo 10 richieste al secondo (qui stiamo largamente sotto)
"""
import logging
import re
import time

import requests

logger = logging.getLogger(__name__)

# La SEC richiede un contatto identificabile: senza, risponde 403.
UA = "Cheruvo/1.0 (michelesantacaterina08@gmail.com)"
ELENCO_TICKER = "https://www.sec.gov/files/company_tickers.json"
SOTTOMISSIONI = "https://data.sec.gov/submissions/CIK{cik}.json"

# Che cosa vale la pena leggere. Escludiamo i moduli di compravendita degli
# insider (3, 4, 5): sono decine al mese e direbbero poco sul sentiment.
MODULI = {
    "8-K":   ("Comunicazione rilevante", 0.0),
    "10-Q":  ("Risultati trimestrali", 0.0),
    "10-K":  ("Bilancio annuale", 0.0),
    "6-K":   ("Comunicazione (emittente estero)", 0.0),
    "20-F":  ("Bilancio annuale (emittente estero)", 0.0),
    "S-1":   ("Prospetto di offerta", 0.0),
    "DEF 14A": ("Avviso di assemblea", 0.0),
}

_cik_per_ticker: dict[str, str] | None = None
_ultima_chiamata = 0.0


def _rispetta_ritmo(minimo: float = 0.4):
    """La SEC tollera 10 richieste/secondo: qui restiamo molto sotto."""
    global _ultima_chiamata
    attesa = minimo - (time.time() - _ultima_chiamata)
    if attesa > 0:
        time.sleep(attesa)
    _ultima_chiamata = time.time()


def _carica_elenco() -> dict[str, str]:
    """
    Mappa ticker -> CIK (il codice con cui la SEC identifica una società).
    Scaricata una volta per processo: è un file di qualche centinaio di KB.
    """
    global _cik_per_ticker
    if _cik_per_ticker is not None:
        return _cik_per_ticker
    _cik_per_ticker = {}
    try:
        _rispetta_ritmo()
        r = requests.get(ELENCO_TICKER, headers={"User-Agent": UA}, timeout=20)
        r.raise_for_status()
        for voce in (r.json() or {}).values():
            t = str(voce.get("ticker", "")).upper()
            c = voce.get("cik_str")
            if t and c is not None:
                _cik_per_ticker[t] = str(c).zfill(10)
        logger.info("SEC: elenco società caricato (%d ticker)", len(_cik_per_ticker))
    except Exception as e:
        logger.warning("SEC: elenco società non disponibile (%s)", e)
    return _cik_per_ticker


def _data(s: str) -> str | None:
    return f"{s} 00:00:00" if re.match(r"^\d{4}-\d{2}-\d{2}$", s or "") else None


def fetch_sec(ticker: str, giorni: int = 30, massimo: int = 10) -> list[dict]:
    """
    Documenti recenti depositati da una società. Lista vuota (mai eccezioni)
    per i ticker non USA o quando la SEC non risponde.
    """
    t = (ticker or "").upper().strip()
    # I ticker con il punto sono borse europee (ENI.MI, SAP.DE): non c'entrano.
    # Quelli con -USD sono criptovalute: non depositano nulla alla SEC, e senza
    # questo controllo sprecheremmo una ricerca nell'elenco per ognuna.
    if "." in t or t.endswith("-USD"):
        return []

    cik = _carica_elenco().get(t)
    if not cik:
        return []

    news: list[dict] = []
    try:
        _rispetta_ritmo()
        r = requests.get(SOTTOMISSIONI.format(cik=cik),
                         headers={"User-Agent": UA}, timeout=20)
        r.raise_for_status()
        dati = r.json() or {}
        nome = dati.get("name") or t
        recenti = (dati.get("filings") or {}).get("recent") or {}

        forme = recenti.get("form") or []
        date = recenti.get("filingDate") or []
        accessi = recenti.get("accessionNumber") or []
        documenti = recenti.get("primaryDocument") or []
        descrizioni = recenti.get("primaryDocDescription") or []

        from datetime import datetime, timedelta
        limite = (datetime.now() - timedelta(days=giorni)).strftime("%Y-%m-%d")

        for i, modulo in enumerate(forme):
            if len(news) >= massimo:
                break
            if modulo not in MODULI:
                continue
            data_dep = date[i] if i < len(date) else ""
            if data_dep < limite:
                break   # la lista è ordinata dal più recente: oltre è vecchio

            etichetta = MODULI[modulo][0]
            descr = descrizioni[i] if i < len(descrizioni) else ""
            titolo = f"{nome}: {etichetta} ({modulo})"
            if descr and descr.lower() not in ("", "form " + modulo.lower()):
                titolo += f" — {descr}"

            # Link al documento vero, non a una pagina di ricerca generica
            acc = (accessi[i] if i < len(accessi) else "").replace("-", "")
            doc = documenti[i] if i < len(documenti) else ""
            url = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{doc}"
                   if acc and doc else
                   f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={modulo}")

            news.append({
                "source": "SEC EDGAR",
                "title": titolo,
                "summary": f"Documento {modulo} depositato il {data_dep}.",
                "published_date": _data(data_dep),
                "url": url,
                # Nessun punteggio qui: lo assegna il modello a valle, che
                # legge il titolo. Un deposito non è di per sé buono o cattivo.
                "sentiment": 0.0,
            })
        logger.info("SEC %s: %d documenti negli ultimi %d giorni", t, len(news), giorni)
    except Exception as e:
        logger.error("SEC %s error: %s", t, e)
    return news
