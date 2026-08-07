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
from datetime import datetime, timedelta, timezone

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

# Colonne che GDELT ricava dal TESTO INTEGRALE e che oggi non leggiamo.
# Servono a `misura_colonne`, che conta quanto volume porterebbero. Non sono
# usate dalla raccolta: prima si misura, poi eventualmente si adottano.
COL_TEMI = 7            # V1THEMES, codici separati da ";"
COL_ORGANIZZAZIONI = 13  # V1ORGANIZATIONS, nomi separati da ";"
COL_NOMI = 23           # V2.1ALLNAMES, "Nome,posizione;Nome,posizione;"

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


def quarti_dora_indietro(ore: int) -> list[str]:
    """
    I timestamp dei file da scaricare, dal più recente al più vecchio.

    GDELT pubblica ai minuti 00, 15, 30 e 45 di ogni ora. Si parte da un
    quarto d'ora fa e non da adesso, perché il file dell'istante corrente
    spesso non è ancora stato pubblicato e darebbe un 404.

    Sta qui e non nel raccoglitore perché serve a tutti e due, e due copie
    della stessa aritmetica sui fusi orari è il genere di cosa che diverge
    senza che nessuno se ne accorga.
    """
    adesso = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    adesso -= timedelta(minutes=adesso.minute % 15 + 15)
    return [(adesso - timedelta(minutes=15 * i)).strftime("%Y%m%d%H%M%S")
            for i in range(ore * 4)]


def righe_della_finestra(ore: int,
                         quale_file: str | None = None) -> tuple[list, int, int]:
    """
    Tutte le righe pubblicate nelle ultime `ore`, da entrambi i feed.

    Sostituisce la lettura di `lastupdate.txt`, che ha un difetto scoperto il
    7 agosto 2026: l'elenco annuncia il file tradotto qualche istante prima
    che sia davvero sul server, e chi lo legge in quel momento prende un 404.
    Due misure di fila sono uscite senza il feed tradotto per questo motivo,
    cioè senza la stampa europea, che è metà del campione e la metà che ci
    interessa di più.

    I timestamp calcolati non hanno quel problema: se un file manca si passa
    al successivo, ed è quello che il raccoglitore fa da sempre (nel run delle
    24 ore ne ha letti 188 su 192).
    """
    stamp = [quale_file] if quale_file else quarti_dora_indietro(ore)
    righe: list[list[str]] = []
    ok = ko = 0
    for ts in stamp:
        for suffisso in ("", "translation."):
            try:
                righe.extend(leggi_gkg(f"{BASE}/{ts}.{suffisso}gkg.csv.zip"))
                ok += 1
            except Exception:
                ko += 1
    return righe, ok, ko


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
        print("\n  esempio di riga letta:")
        print(f"    dominio: {esempio[COL_DOMINIO][:45]}")
        print(f"    titolo:  {titolo(esempio)[:70]}")
        print(f"    tono:    {tono(esempio)}")
        print(f"    lingua:  {lingua(esempio)}")


# Quindici dei nostri termini sono ANCHE parole comuni: Avalanche, Polygon,
# Cosmos, Stellar, Optimism, NEAR, Solana, Cardano, Aptos, Shiba fra le monete,
# e Apple, Amazon, Meta, Shell, GE fra i titoli. Su un archivio mondiale che
# raccoglie tutto, "Stocks near record highs" diventerebbe una notizia su NEAR
# e "avalanche kills three" una notizia su AVAX.
#
# Gli ultimi quattro sono stati aggiunti il 7 agosto 2026 e sono meno evidenti
# degli altri: Solana Beach e Aptos sono due località della California,
# Cardano è un cognome italiano diffuso (e un comune in provincia di Varese),
# Shiba è una razza di cane. Sono monete già sottili, quindi il filtro qui
# toglie più di quanto tolga altrove: meglio zero righe che due righe su un
# matematico del Cinquecento.
#
# Sull'API il problema quasi non si vedeva, perché la query era già ristretta
# a un contesto finanziario. Sui file grezzi, che contengono meteo, sport e
# cronaca del mondo intero, diventa il rischio principale: gonfierebbe i
# conteggi con roba che non c'entra, facendo sembrare il cambio conveniente
# quando non lo è.
AMBIGUI = {"Avalanche", "Polygon", "Cosmos", "Stellar", "Optimism", "NEAR",
           "Solana", "Cardano", "Aptos", "Shiba",
           "Apple", "Amazon", "Meta", "Shell", "GE"}

# Due termini sono sigle scritte SEMPRE in maiuscolo quando indicano la cosa
# giusta: la moneta si chiama "NEAR", la preposizione inglese si scrive "near".
# Per questi il confronto tiene conto delle maiuscole, ed è l'unico modo di
# separarli: "Stocks near record highs as traders wait" contiene "Stocks" e
# "traders", quindi supera il filtro di contesto qui sotto pur non parlando
# affatto della moneta.
MAIUSCOLI = {"NEAR", "GE", "XRP"}

# Il titolo deve contenere anche una parola di contesto finanziario.
# L'elenco resta corto di proposito: allargarlo troppo rimette dentro il rumore
# che serviva a togliere.
CONTESTO = re.compile(
    r"\b(crypto|cryptocurrenc\w*|token|coin|blockchain|defi|wallet|"
    r"stock|shares?|market|trading|traders?|price|nasdaq|earnings|"
    r"nyse|ftse|dax|investor\w*|dividend\w*|ipo|revenue|profit\w*|"
    r"quarterly|valuation|analysts?|"
    r"borsa|azion\w+|mercat\w+|quotazion\w+|criptovalut\w+|"
    r"investitor\w+|trimestral\w+|ricavi|analist\w+|"
    r"prezzo|titol\w+|投資|bourse|aktie\w*)\b", re.I)


def serve_contesto(ticker: str, termine: str) -> bool:
    """
    Se per questo titolo il contesto finanziario è obbligatorio.

    Due casi diversi che finiscono nella stessa regola.

    I termini in AMBIGUI sono parole comuni travestite: "avalanche", "near",
    "shiba". Senza contesto entrerebbe la cronaca.

    I nomi delle AZIENDE lo sono in un modo meno evidente e più costoso.
    "Google" e "Microsoft" non sono parole comuni, ma compaiono ogni giorno
    in centinaia di titoli che non parlano affatto del titolo azionario:
    aggiornamenti di prodotto, disservizi, recensioni, cause legali. Nella
    raccolta del 7 agosto 2026 GOOGL e MSFT da soli facevano 816 righe su
    1.541, cioè il 53% di tutto, e finivano dritte nella media del sentiment.

    Le MONETE invece no, e non è una svista: il nome della moneta è già esso
    stesso un termine di mercato. "Bitcoin crolla" è una notizia finanziaria
    per costruzione, mentre "Google presenta il nuovo Pixel" non lo è.
    Chiedere il contesto anche a Bitcoin taglierebbe metà della copertura
    cripto senza togliere un solo falso positivo.

    Il costo di questa regola va detto: "Eni sigla un accordo in Libia" è
    una notizia societaria vera e da oggi resta fuori. È una perdita
    accettabile finché l'alternativa è calcolare il sentiment di Google sui
    titoli di Google Maps.
    """
    if termine in AMBIGUI:
        return True
    return not (ticker or "").upper().endswith("-USD")


def conta_pertinenti(righe: list[list[str]], termini: dict,
                     rigoroso: bool = True) -> tuple[Counter, Counter, list]:
    """
    Quanti articoli parlano davvero delle nostre monete.

    Il criterio è lo stesso del resto del progetto: il termine deve comparire
    nel TITOLO. Cercarlo nell'URL o nel corpo porterebbe dentro ogni pezzo che
    nomina Bitcoin di sfuggita in fondo, che è rumore travestito da copertura.

    Con `rigoroso`, i termini che passano da `serve_contesto` esigono anche una
    parola di contesto finanziario nel titolo. Il conteggio senza è utile solo
    per misurare quanto rumore produrrebbe la versione ingenua.

    Un articolo può contare per più titoli: se ne nomina due, riguarda due.
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
        # Niente `break`: un articolo che nomina due asset conta per entrambi.
        # Prima ci si fermava al primo che combaciava, e siccome nel dizionario
        # le azioni vengono prima delle monete, "Microsoft mette Bitcoin in
        # tesoreria" diventava una notizia MSFT e Bitcoin la perdeva. Un modo
        # silenzioso di sottostimare proprio la parte che ci interessa.
        primo = True
        for tk, pattern in rx.items():
            if not pattern.search(t):
                continue
            if rigoroso and serve_contesto(tk, termini[tk]) and not CONTESTO.search(t):
                continue
            per_ticker[tk] += 1
            # La lingua conta l'ARTICOLO, non le sue assegnazioni: altrimenti
            # un pezzo che nomina tre monete varrebbe tre articoli inglesi.
            if primo:
                per_lingua[lingua(r)] += 1
                if len(esempi) < 8:
                    esempi.append((tk, lingua(r), tono(r), t[:64],
                                   r[COL_DOMINIO][:28]))
                primo = False
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
    print("\n  Oggi, con l'API, Bitcoin raccoglie circa 4 articoli al giorno.")
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


# ══════════════════════════════════════════════════════════════════════════
#  QUANTO VOLUME C'È NELLE COLONNE CHE NON LEGGIAMO
# ══════════════════════════════════════════════════════════════════════════
#
# Oggi un articolo entra in archivio solo se il nome dell'asset compare nel
# TITOLO. È una regola prudente e costosa: "Il Nasdaq chiude in rosso", che poi
# parla di Nvidia per tre paragrafi, per noi non esiste.
#
# GDELT però pubblica per ogni articolo anche i temi, le organizzazioni e tutti
# i nomi propri, estratti dal testo integrale. Il volume in più sta lì.
#
# Sta lì anche il modo più rapido di rovinare l'archivio, perché "nomina
# Bitcoin" non è "parla di Bitcoin". Questa funzione non adotta niente: conta
# quanti articoli in PIÙ porterebbe ogni colonna e stampa i titoli, così la
# decisione si prende leggendo esempi veri invece che immaginandoli.


def _voci(campo: str, con_posizione: bool = False) -> list[str]:
    """
    Spacchetta un campo a lista di GDELT.

    ALLNAMES scrive "Nome,4523" e la posizione va tolta; THEMES e
    ORGANIZATIONS scrivono la voce e basta. Entrambi chiudono con un ";"
    finale che produce una voce vuota.
    """
    fuori = []
    for v in (campo or "").split(";"):
        v = v.strip()
        if not v:
            continue
        if con_posizione and "," in v:
            v = v.rsplit(",", 1)[0].strip()
        if v:
            fuori.append(v)
    return fuori


def _compare_in(voci: list[str], termine: str) -> bool:
    """Confronto a parola intera, con le stesse regole del titolo."""
    flag = 0 if termine in MAIUSCOLI else re.I
    rx = re.compile(r"\b" + re.escape(termine) + r"\b", flag)
    return any(rx.search(v) for v in voci)


def misura_colonne(quale_file: str | None, ore: int = 6) -> int:
    sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
    from gdelt_source import TERMINE_QUERY

    print("=" * 72)
    print("  QUANTO PORTEREBBERO LE COLONNE CHE OGGI IGNORIAMO")
    print("=" * 72)

    colonne = (("TEMI", COL_TEMI, False),
               ("ORGANIZZAZIONI", COL_ORGANIZZAZIONI, False),
               ("NOMI PROPRI", COL_NOMI, True))

    righe_tot = 0
    con_titolo = 0
    presenti = Counter()
    gia_nel_titolo = 0
    nuovi = Counter()          # per colonna
    nuovi_ticker = {n: Counter() for n, _, _ in colonne}
    esempi = {n: [] for n, _, _ in colonne}
    temi_visti = Counter()

    print(f"\n  Leggo {ore} ore di file da entrambi i feed.\n")
    righe, file_ok, file_ko = righe_della_finestra(ore, quale_file)
    righe_tot = len(righe)

    for r in righe:
        t = titolo(r)
        if t:
            con_titolo += 1
        for nome, idx, con_pos in colonne:
            if len(r) > idx and (r[idx] or "").strip():
                presenti[nome] += 1

        # Chi entrerebbe già oggi, con la regola del titolo.
        dal_titolo = set()
        if t:
            for tk, term in TERMINE_QUERY.items():
                flag = 0 if term in MAIUSCOLI else re.I
                if not re.search(r"\b" + re.escape(term) + r"\b", t, flag):
                    continue
                if serve_contesto(tk, term) and not CONTESTO.search(t):
                    continue
                dal_titolo.add(tk)
        if dal_titolo:
            gia_nel_titolo += 1

        for nome, idx, con_pos in colonne:
            if len(r) <= idx:
                continue
            voci = _voci(r[idx], con_pos)
            if not voci:
                continue
            trovati = {tk for tk, term in TERMINE_QUERY.items()
                       if _compare_in(voci, term)}
            extra = trovati - dal_titolo
            if not extra:
                continue
            nuovi[nome] += 1
            for tk in extra:
                nuovi_ticker[nome][tk] += 1
            if len(esempi[nome]) < 6:
                esempi[nome].append((sorted(extra), t[:78] or "(senza titolo)"))
            # I temi di un articolo che nomina una cripta: servono a
            # scegliere un filtro di contesto fatto di codici veri e non
            # inventati a memoria.
            if nome == "NOMI PROPRI" and any(tk.endswith("-USD") for tk in extra):
                if len(r) > COL_TEMI:
                    temi_visti.update(_voci(r[COL_TEMI]))

    if not righe_tot:
        print("\n  Nessuna riga letta: non c'è niente da misurare.")
        return 1

    print("\n" + "=" * 72)
    print("  COSA C'È DAVVERO NEI FILE")
    print("=" * 72)
    print(f"\n  file letti: {file_ok} ({file_ko} non disponibili)")
    print(f"  righe totali: {righe_tot}")
    print(f"  con un titolo leggibile: {con_titolo} ({con_titolo / righe_tot:.0%})")
    for nome, _, _ in colonne:
        print(f"  con {nome.lower():<16} {presenti[nome]:>6} "
              f"({presenti[nome] / righe_tot:.0%})")
    print(f"\n  articoli che entrano OGGI (regola del titolo): {gia_nel_titolo}")

    print("\n" + "=" * 72)
    print("  QUANTI ARTICOLI IN PIÙ, PER COLONNA")
    print("=" * 72)
    print("\n  Sono articoli che oggi NON entrano e che entrerebbero se")
    print("  guardassimo anche quella colonna. Il moltiplicatore è rispetto")
    print("  ai {} di adesso.\n".format(gia_nel_titolo))
    for nome, _, _ in colonne:
        n = nuovi[nome]
        molt = f"×{1 + n / gia_nel_titolo:.1f}" if gia_nel_titolo else "n/d"
        print(f"  {nome:<16} +{n:<6} ({molt} il volume attuale)")

    for nome, _, _ in colonne:
        if not esempi[nome]:
            continue
        print(f"\n── Esempi da {nome} " + "─" * max(2, 44 - len(nome)))
        print("  Da leggere chiedendosi una cosa sola: questo articolo PARLA")
        print("  dell'asset, o lo nomina di sfuggita?\n")
        for tks, ti in esempi[nome]:
            print(f"    [{','.join(tks):<22}] {ti}")
        print("\n  i titoli che guadagnerebbero di più:")
        for tk, n in nuovi_ticker[nome].most_common(8):
            print(f"    {tk:<11} +{n}")

    if temi_visti:
        print("\n" + "=" * 72)
        print("  TEMI PIÙ FREQUENTI SUGLI ARTICOLI CHE NOMINANO UNA CRIPTO")
        print("=" * 72)
        print("\n  Se un giorno adottiamo queste colonne, il filtro di contesto")
        print("  non potrà più essere fatto di parole nel titolo. Questi sono i")
        print("  codici veri da cui partire, letti dai file e non ricordati.\n")
        for tema, n in temi_visti.most_common(20):
            print(f"    {n:>5}  {tema}")

    print("\n" + "=" * 72)
    print("  Nessuna riga è stata scritta. Questo strumento misura e basta.")
    print("=" * 72)
    return 0


# ══════════════════════════════════════════════════════════════════════════
#  QUANTO PORTEREBBE CERCARE ANCHE LE SIGLE
# ══════════════════════════════════════════════════════════════════════════
#
# Oggi cerchiamo "Bitcoin" e non "BTC", "Nvidia" e non "NVDA". La stampa
# specializzata però scrive spessissimo la sigla, e quei titoli oggi ci
# sfuggono per intero.
#
# A differenza delle colonne estratte dal testo, questa strada resta nel
# TITOLO, cioè non rinuncia alla precisione che il filtro di contesto ci ha
# appena fatto guadagnare. Il rischio è un altro e va misurato per sigla, non
# in blocco: "BTC" in un titolo è praticamente sempre Bitcoin, "LINK" non è
# quasi mai Chainlink, e "ISP" è il fornitore di connettività molto più spesso
# di Intesa Sanpaolo.
#
# Per questo la misura NON produce un sì o un no complessivo: produce una riga
# per sigla, con quante ne porterebbe e quante di quelle hanno una parola di
# mercato nel titolo. L'elenco delle sigle da adottare si scrive a mano
# leggendo quella tabella, non si deduce.


def sigla_di(ticker: str) -> str:
    """La sigla nuda: BTC-USD -> BTC, RACE.MI -> RACE, NVDA -> NVDA."""
    return (ticker or "").upper().split("-")[0].split(".")[0]


def misura_sigle(quale_file: str | None, ore: int = 6) -> int:
    sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
    from gdelt_source import TERMINE_QUERY

    print("=" * 72)
    print("  QUANTO PORTEREBBE CERCARE ANCHE LE SIGLE NEL TITOLO")
    print("=" * 72)

    # Le sigle che coincidono col termine che già cerchiamo non aggiungono
    # niente: per Eni, Enel, ASML, LVMH, SAP, AMD, XRP e NEAR la sigla È il
    # nome. Misurarle gonfierebbe il risultato con zeri travestiti.
    sigle = {}
    for tk, term in TERMINE_QUERY.items():
        s = sigla_di(tk)
        if s.lower() != term.lower():
            sigle[tk] = s
    saltate = len(TERMINE_QUERY) - len(sigle)

    print(f"\n  sigle da misurare: {len(sigle)}")
    print(f"  saltate perché la sigla è già il termine cercato: {saltate}")

    righe_tot = 0
    oggi_tot = 0
    extra = Counter()           # per sigla, totale
    extra_contesto = Counter()  # per sigla, con parola di mercato nel titolo
    esempi = {}

    rx_sigla = {tk: re.compile(r"\b" + re.escape(s) + r"\b")  # SEMPRE maiuscole
                for tk, s in sigle.items()}

    print(f"\n  Leggo {ore} ore di file da entrambi i feed.\n")
    righe, file_ok, file_ko = righe_della_finestra(ore, quale_file)
    righe_tot = len(righe)

    for r in righe:
        t = titolo(r)
        if not t:
            continue
        contesto = bool(CONTESTO.search(t))

        oggi = set()
        for tk, term in TERMINE_QUERY.items():
            flag = 0 if term in MAIUSCOLI else re.I
            if not re.search(r"\b" + re.escape(term) + r"\b", t, flag):
                continue
            if serve_contesto(tk, term) and not contesto:
                continue
            oggi.add(tk)
        if oggi:
            oggi_tot += 1

        for tk, pattern in rx_sigla.items():
            if tk in oggi or not pattern.search(t):
                continue
            s = sigle[tk]
            extra[s] += 1
            if contesto:
                extra_contesto[s] += 1
            esempi.setdefault(s, [])
            if len(esempi[s]) < 3:
                esempi[s].append((contesto, t[:76]))

    if not righe_tot:
        print("\n  Nessuna riga letta: non c'è niente da misurare.")
        return 1

    print("\n" + "=" * 72)
    print("  LA TABELLA DA CUI SI DECIDE")
    print("=" * 72)
    print(f"\n  file letti: {file_ok} ({file_ko} non disponibili)")
    print(f"  righe lette: {righe_tot}")
    print(f"  articoli che entrano oggi: {oggi_tot}\n")
    print(f"  {'sigla':<8}{'in più':>8}{'con mercato':>13}{'senza':>8}   giudizio")
    print("  " + "─" * 68)

    for s, n in extra.most_common():
        con = extra_contesto[s]
        senza = n - con
        # Il giudizio è un promemoria, non un verdetto: dice solo dove
        # guardare per primo. La decisione si prende leggendo gli esempi.
        if con == 0:
            g = "nessuna di mercato, quasi certo rumore"
        elif con / n >= 0.5:
            g = "promettente, leggi gli esempi"
        else:
            g = "da tenere solo col contesto obbligatorio"
        print(f"  {s:<8}{n:>8}{con:>13}{senza:>8}   {g}")

    if not extra:
        # Zero non vuol dire "non esiste". Con nessun caso osservato su n
        # prove, il limite superiore al 95% sta intorno a 3/n: è la regola
        # del tre, e serve a non trasformare un campione piccolo in un
        # verdetto. Senza questa riga, un file da mille titoli basterebbe a
        # chiudere per sempre una strada che magari valeva.
        tetto = 3 / righe_tot
        print("  nessuna sigla ha portato niente in questo campione\n")
        print(f"  Attenzione a come si legge questo zero. Su {righe_tot} titoli,")
        print(f"  il limite superiore al 95% è {tetto:.3%}, cioè fino a circa")
        print(f"  {int(tetto * 336000)} articoli al giorno sui 336.000 che GDELT pubblica.")
        print("  Un campione più grande può ancora ribaltare il risultato.")

    print("\n" + "=" * 72)
    print("  GLI ESEMPI")
    print("=" * 72)
    print("\n  [M] = il titolo contiene una parola di mercato\n")
    for s, n in extra.most_common():
        print(f"  {s} (+{n})")
        for contesto, ti in esempi.get(s, []):
            print(f"    {'[M]' if contesto else '[ ]'} {ti}")
        print()

    print("=" * 72)
    print("  Nessuna riga è stata scritta. Questo strumento misura e basta.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", default=None,
                    help="timestamp preciso, es. 20260806180000. "
                         "Senza, prende l'ultimo pubblicato.")
    ap.add_argument("--modo", choices=("resa", "colonne", "sigle"),
                    default="resa",
                    help="resa: quanto rende un file. colonne: quanto "
                         "porterebbero temi, organizzazioni e nomi propri. "
                         "sigle: quanto porterebbe cercare BTC oltre a Bitcoin.")
    ap.add_argument("--colonne", action="store_true",
                    help="scorciatoia per --modo colonne")
    ap.add_argument("--ore", type=int, default=6,
                    help="quante ore di file leggere (default 6, cioè 48 "
                         "file). Un file solo non basta per misurare una cosa "
                         "rara: serve solo a vedere se il codice gira.")
    args = ap.parse_args()

    modo = "colonne" if args.colonne else args.modo
    if modo == "colonne":
        sys.exit(misura_colonne(args.file, args.ore))
    if modo == "sigle":
        sys.exit(misura_sigle(args.file, args.ore))
    sys.exit(misura(args.file))
