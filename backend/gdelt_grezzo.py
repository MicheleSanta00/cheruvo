"""
gdelt_grezzo.py — La porta di servizio di GDELT: i file pubblicati ogni 15 minuti.

PERCHÉ ESISTE

L'API che usiamo (`gdelt_source.py`) ha due muri che il 6 agosto 2026 ci hanno
bloccato per un giorno intero:

  1. Massimo 250 risultati per interrogazione. Con le venti monete raggruppate,
     a Bitcoin ne arrivavano due.
  2. Un rate limit severo, con una punizione che resta addosso all'indirizzo IP
     anche dopo che hai smesso di chiamare.

Gli stessi dati però GDELT li pubblica anche come FILE, uno ogni quarto d'ora,
su un server statico. Stessa licenza commerciale libera, ma:

  - nessun rate limit, perché sono file e non un servizio;
  - nessun tetto di 250, perché un file contiene tutto quello che GDELT ha
    visto in quei quindici minuti;
  - un feed separato per il resto del mondo tradotto, che è dove finisce la
    stampa italiana. L'API sul feed inglese rendeva 1 articolo utile su 20 per
    "Eni": non perché mancasse, ma perché stavamo cercando nel posto sbagliato.

In più il file GKG porta il TONO calcolato da GDELT sul testo integrale
dell'articolo. Noi oggi calcoliamo il sentiment su titolo più 120 caratteri:
avere un secondo punteggio, indipendente e misurato su tutto il pezzo, vale più
di qualunque aumento di volume.

QUESTO FILE NON SCRIVE NIENTE

È uno strumento di misura. Prima di costruire un ingeritore vero bisogna sapere
quanti articoli utili contiene davvero un file, e quella risposta non la si può
indovinare. Se un file da 15 minuti porta trenta pezzi su Bitcoin sono 2.880 al
giorno, contro i 4 di adesso. Se ne porta due, l'idea era sbagliata e lo si
scopre in mezz'ora invece che in due giorni.

    python backend/gdelt_grezzo.py              # misura l'ultimo file disponibile
    python backend/gdelt_grezzo.py --file 20260806180000
"""
import argparse
import csv
import io
import logging
import re
import sys
import zipfile
from collections import Counter

import requests

logger = logging.getLogger("gdelt-grezzo")

BASE = "http://data.gdeltproject.org/gdeltv2"
ULTIMO_EN = f"{BASE}/lastupdate.txt"
ULTIMO_TRAD = f"{BASE}/lastupdate-translation.txt"
_UA = {"User-Agent": "Cheruvo/1.0 (+https://cheruvo.com)"}

# Struttura del GKG 2.1: 27 colonne separate da tabulazione.
# Gli indici NON vengono dati per buoni: `descrivi_formato` stampa quello che
# trova davvero, così se GDELT cambia disposizione ce ne accorgiamo subito
# invece di leggere in silenzio la colonna sbagliata.
COL_DATA = 1        # V2.1DATE, YYYYMMDDHHMMSS
COL_DOMINIO = 3     # V2SOURCECOMMONNAME
COL_URL = 4         # V2DOCUMENTIDENTIFIER
COL_TONO = 15       # V1.5TONE: tono,positivo,negativo,polarita,...
COL_TRADUZIONE = 25  # V2.1TRANSLATIONINFO, es. "srclc:ita;eng:Moses"
COL_EXTRA = 26      # V2EXTRASXML, contiene <PAGE_TITLE>

_TITOLO_RX = re.compile(r"<PAGE_TITLE>(.*?)</PAGE_TITLE>", re.S)
_LINGUA_RX = re.compile(r"srclc:(\w+)")


def scarica_elenco(url: str) -> list[str]:
    """Le tre righe di lastupdate: export, mentions, gkg. A noi serve il gkg."""
    r = requests.get(url, timeout=60, headers=_UA)
    r.raise_for_status()
    return [riga.split()[-1] for riga in r.text.strip().splitlines() if riga.strip()]


def url_gkg(elenco: list[str]) -> str | None:
    for u in elenco:
        if "gkg" in u:
            return u
    return None


def leggi_gkg(url: str) -> list[list[str]]:
    """Scarica lo zip, lo apre in memoria e restituisce le righe."""
    r = requests.get(url, timeout=180, headers=_UA)
    r.raise_for_status()
    peso = len(r.content)
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        nome = z.namelist()[0]
        with z.open(nome) as f:
            testo = io.TextIOWrapper(f, encoding="utf-8", errors="replace")
            # Il GKG usa la tabulazione e NON quota i campi: con il lettore
            # standard di Python un apice dentro un titolo spezzerebbe la riga.
            righe = [r for r in csv.reader(testo, delimiter="\t", quoting=csv.QUOTE_NONE)]
    logger.info("  %s: %.1f MB compressi, %d righe", nome, peso / 1e6, len(righe))
    return righe


def titolo(riga: list[str]) -> str:
    if len(riga) <= COL_EXTRA:
        return ""
    m = _TITOLO_RX.search(riga[COL_EXTRA] or "")
    return (m.group(1).strip() if m else "")


def lingua(riga: list[str]) -> str:
    """Lingua originale, presente solo nel feed tradotto."""
    if len(riga) <= COL_TRADUZIONE:
        return "eng"
    m = _LINGUA_RX.search(riga[COL_TRADUZIONE] or "")
    return m.group(1) if m else "eng"


def tono(riga: list[str]) -> float | None:
    """
    Il tono di GDELT, calcolato sul testo INTEGRALE. Va da circa -100 a +100,
    ma nella pratica sta fra -20 e +20. Il nostro sentiment va da -1 a +1,
    quindi per confrontarli andrà riscalato, non usato così com'è.
    """
    if len(riga) <= COL_TONO:
        return None
    campo = (riga[COL_TONO] or "").split(",")
    try:
        return float(campo[0])
    except (ValueError, IndexError):
        return None


def descrivi_formato(righe: list[list[str]]) -> None:
    """
    Stampa cosa c'è davvero nel file, invece di fidarsi degli indici scritti
    qui sopra. Se GDELT cambiasse la disposizione delle colonne, un parser che
    dà per buoni gli indici leggerebbe il campo sbagliato SENZA errori: il
    conteggio uscirebbe zero e sembrerebbe che non ci siano notizie.
    """
    if not righe:
        print("  Il file è vuoto.")
        return
    larghezze = Counter(len(r) for r in righe)
    print(f"  colonne per riga (le tre più frequenti): {larghezze.most_common(3)}")
    con_titolo = sum(1 for r in righe if titolo(r))
    print(f"  righe con un titolo leggibile: {con_titolo} su {len(righe)} "
          f"({con_titolo / max(1, len(righe)):.0%})")
    esempio = next((r for r in righe if titolo(r)), None)
    if esempio:
        print(f"\n  esempio di riga letta:")
        print(f"    dominio: {esempio[COL_DOMINIO][:45]}")
        print(f"    titolo:  {titolo(esempio)[:70]}")
        print(f"    tono:    {tono(esempio)}")
        print(f"    lingua:  {lingua(esempio)}")


# Undici dei nostri termini sono ANCHE parole comuni: Avalanche, Polygon,
# Cosmos, Stellar, Optimism, NEAR fra le monete, e Apple, Amazon, Meta, Shell,
# GE fra i titoli. Su un archivio mondiale che raccoglie tutto, "Stocks near
# record highs" diventerebbe una notizia su NEAR e "avalanche kills three"
# una notizia su AVAX.
#
# Sull'API il problema quasi non si vedeva, perché la query era già ristretta
# a un contesto finanziario. Sui file grezzi, che contengono meteo, sport e
# cronaca del mondo intero, diventa il rischio principale: gonfierebbe i
# conteggi con roba che non c'entra, facendo sembrare il cambio conveniente
# quando non lo è.
AMBIGUI = {"Avalanche", "Polygon", "Cosmos", "Stellar", "Optimism", "NEAR",
           "Apple", "Amazon", "Meta", "Shell", "GE"}

# Due termini sono sigle scritte SEMPRE in maiuscolo quando indicano la cosa
# giusta: la moneta si chiama "NEAR", la preposizione inglese si scrive "near".
# Per questi il confronto tiene conto delle maiuscole, ed è l'unico modo di
# separarli: "Stocks near record highs as traders wait" contiene "Stocks" e
# "traders", quindi supera il filtro di contesto qui sotto pur non parlando
# affatto della moneta.
MAIUSCOLI = {"NEAR", "GE", "XRP"}

# Per quei termini il titolo deve contenere anche una parola di contesto.
# L'elenco è volutamente corto: allargarlo troppo rimetterebbe dentro il rumore.
CONTESTO = re.compile(
    r"\b(crypto|cryptocurrenc\w*|token|coin|blockchain|defi|wallet|"
    r"stock|shares?|market|trading|traders?|price|nasdaq|earnings|"
    r"borsa|azion\w+|mercat\w+|quotazion\w+|criptovalut\w+|"
    r"prezzo|titol\w+|投資|bourse|aktie)\b", re.I)


def conta_pertinenti(righe: list[list[str]], termini: dict,
                     rigoroso: bool = True) -> tuple[Counter, Counter, list]:
    """
    Quanti articoli parlano davvero delle nostre monete.

    Il criterio è lo stesso del resto del progetto: il termine deve comparire
    nel TITOLO. Cercarlo nell'URL o nel corpo porterebbe dentro ogni pezzo che
    nomina Bitcoin di sfuggita in fondo, che è rumore travestito da copertura.

    Con `rigoroso`, i termini ambigui esigono anche una parola di contesto
    finanziario. Il conteggio senza è utile solo per misurare quanto rumore
    produrrebbe la versione ingenua.
    """
    per_ticker = Counter()
    per_lingua = Counter()
    esempi = []

    # Confini di parola: senza, "XRP" prenderebbe "XRPL".
    # Le sigle in MAIUSCOLI si confrontano rispettando le maiuscole.
    rx = {tk: re.compile(r"\b" + re.escape(term) + r"\b",
                         0 if term in MAIUSCOLI else re.I)
          for tk, term in termini.items()}

    for r in righe:
        t = titolo(r)
        if not t:
            continue
        for tk, pattern in rx.items():
            if not pattern.search(t):
                continue
            if rigoroso and termini[tk] in AMBIGUI and not CONTESTO.search(t):
                continue
            per_ticker[tk] += 1
            per_lingua[lingua(r)] += 1
            if len(esempi) < 8:
                esempi.append((tk, lingua(r), tono(r), t[:64],
                               r[COL_DOMINIO][:28]))
            break
    return per_ticker, per_lingua, esempi


def misura(quale_file: str | None) -> int:
    sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
    from gdelt_source import TERMINE_QUERY, e_crypto

    crypto = {tk: t for tk, t in TERMINE_QUERY.items() if e_crypto(tk)}
    azioni = {tk: t for tk, t in TERMINE_QUERY.items() if not e_crypto(tk)}

    print("=" * 72)
    print("  QUANTO RENDE DAVVERO LA PORTA DI SERVIZIO DI GDELT")
    print("=" * 72)

    totali_crypto, totali_azioni, totali_lingua = Counter(), Counter(), Counter()
    righe_totali = 0

    for etichetta, elenco_url in (("INGLESE", ULTIMO_EN),
                                  ("RESTO DEL MONDO (tradotto)", ULTIMO_TRAD)):
        print(f"\n── Feed {etichetta} " + "─" * (48 - len(etichetta)))
        try:
            if quale_file:
                suffisso = "" if etichetta == "INGLESE" else "translation."
                url = f"{BASE}/{quale_file}.{suffisso}gkg.csv.zip"
            else:
                url = url_gkg(scarica_elenco(elenco_url))
            if not url:
                print("  Nessun file GKG nell'elenco.")
                continue
            print(f"  {url.split('/')[-1]}")
            righe = leggi_gkg(url)
        except Exception as e:
            print(f"  ERRORE: {e}")
            continue

        righe_totali += len(righe)
        descrivi_formato(righe)

        c, lc, esempi = conta_pertinenti(righe, crypto)
        a, la, _ = conta_pertinenti(righe, azioni)
        c_ing, _, _ = conta_pertinenti(righe, crypto, rigoroso=False)
        a_ing, _, _ = conta_pertinenti(righe, azioni, rigoroso=False)
        scartati = (sum(c_ing.values()) - sum(c.values())
                    + sum(a_ing.values()) - sum(a.values()))
        totali_crypto += c
        totali_azioni += a
        totali_lingua += lc + la

        print(f"\n  articoli sulle CRYPTO:  {sum(c.values()):>5}")
        print(f"  articoli sulle AZIONI:  {sum(a.values()):>5}")
        if scartati:
            print(f"  scartati come falsi:    {scartati:>5}   "
                  f"(\"Avalanche\", \"near\", \"Apple\" fuori contesto finanziario)")
        if esempi:
            print("\n  esempi:")
            for tk, lg, tn, ti, dom in esempi:
                print(f"    [{tk:<9}] [{lg}] tono {str(tn):>6}  {ti}  ({dom})")

    print("\n" + "=" * 72)
    print("  IL CONFRONTO CHE CONTA")
    print("=" * 72)

    tot_c = sum(totali_crypto.values())
    tot_a = sum(totali_azioni.values())
    print(f"\n  In UN file da 15 minuti: {tot_c} articoli crypto, {tot_a} su azioni")
    print(f"  Proiettato su un giorno (96 file): "
          f"{tot_c * 96} crypto, {tot_a * 96} azioni")
    print(f"\n  Oggi, con l'API, Bitcoin raccoglie circa 4 articoli al giorno.")
    btc = totali_crypto.get("BTC-USD", 0)
    print(f"  Qui Bitcoin da solo fa {btc} in 15 minuti = {btc * 96} al giorno.")

    if totali_crypto:
        print("\n  per moneta (in questi 15 minuti):")
        for tk, n in totali_crypto.most_common(10):
            print(f"    {tk:<11} {n}")

    if totali_lingua:
        print("\n  per lingua d'origine:")
        for lg, n in totali_lingua.most_common(8):
            nota = "  <-- la stampa italiana, quella che l'API non vedeva" if lg == "ita" else ""
            print(f"    {lg:<6} {n}{nota}")

    print("\n" + "=" * 72)
    if tot_c * 96 > 200:
        print("  VERDETTO: vale la pena costruirci l'ingeritore.")
        print(f"  Il salto è da ~4 a ~{btc * 96} articoli al giorno su Bitcoin,")
        print("  con la stessa licenza e senza rate limit.")
    else:
        print("  VERDETTO: il guadagno non giustifica il lavoro.")
        print("  Meglio restare sull'API e spendere il tempo altrove.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", default=None,
                    help="timestamp preciso, es. 20260806180000. "
                         "Senza, prende l'ultimo pubblicato.")
    args = ap.parse_args()
    sys.exit(misura(args.file))
