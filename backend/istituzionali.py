"""
istituzionali.py — Le fonti regolatorie: Fed, BCE, ESMA, SEC.

PERCHÉ, E PERCHÉ SOLO QUESTE

Per le criptovalute un annuncio di un regolatore sposta il mercato più di
cento articoli di cronaca. E soprattutto queste fonti risolvono il problema
che il 7 agosto 2026 è costato 32.675 righe cancellate: sono atti pubblici o
hanno una licenza di riuso scritta, quindi non c'è niente da indovinare.

LE LICENZE, LETTE DAI TESTI ORIGINALI IL 10 AGOSTO 2026

Non da riassunti né da blog: dalle pagine legali dei siti. È la stessa
disciplina che avrebbe evitato il pasticcio di NewsAPI, dove ci si era fidati
di una sintesi trovata altrove.

  FED (federalreserve.gov/disclaimer.htm)
    "Unless otherwise indicated, information on Board's website is in the
     public domain and may be copied and distributed without permission.
     Please cite to the Board as the source of the information."
    Vietato: usare sigilli e logo, e il "framing" del sito dentro il nostro.

  BCE (ecb.europa.eu/services/disclaimer)
    "users of this website may make free use of the information obtained
     directly from it" a tre condizioni: citare la BCE come fonte; se il
     materiale finisce in qualcosa di VENDUTO, dire al compratore che è
     ottenibile gratis; e se lo si MODIFICA, dichiararlo esplicitamente.
    Fuori: i Working Papers e gli Occasional Papers firmati da autori, che
    richiedono autorizzazione scritta. Per questo leggiamo solo i comunicati.

  ESMA (esma.europa.eu/about-esma/legal-notice-and-data-protection)
    "Reproduction of all information on this site is authorised... provided
     the source is acknowledged". Se il materiale viene trasformato, va
     aggiunta una frase precisa, che sta in DISCLAIMER qui sotto.
    Vietato il logo.

  SEC EDGAR — atti pubblici USA, pubblico dominio. Già usata da sec_source.py.

CHI È RIMASTO FUORI, E PERCHÉ

  BANCA D'ITALIA — NO, e lo dice a chiare lettere (bancaditalia.it/footer/copyright):
    "La stampa e il salvataggio dei contenuti di questo sito sono consentiti
     per solo uso personale, con esclusione di ogni utilizzo per fini di lucro
     o per trarne qualsivoglia utilità economica... neppure è consentita la
     riproduzione di questo sito o di parti di esso su altri siti Internet o
     su qualunque sistema informativo pubblico o privato, senza preventiva
     autorizzazione scritta della Banca."
    Cheruvo è esattamente "un altro sito Internet". Senza autorizzazione
    scritta non si tocca.
    Unica eccezione: i loro open data su dati.gov.it, rilasciati in CC-BY 4.0
    e quindi riutilizzabili anche a fini commerciali citando la fonte. Sono
    dati statistici, non comunicati: un'altra cosa, ma legale.

  CONSOB — forse, e "forse" non basta (consob.it/web/consob/informazioni-legali):
    "È consentita la consultazione, la stampa, il download e il riutilizzo dei
     contenuti per finalità di studio, ricerca, informazione e documentazione,
     con obbligo di citarne la fonte."
    Il permesso c'è ma è legato a delle FINALITÀ, e fra quelle non compare
    l'uso commerciale. Oggi Cheruvo è gratuito e sta comodamente dentro
    "informazione"; il giorno in cui tornasse un piano a pagamento, non è
    ovvio. Aggiungerla adesso vorrebbe dire costruire su una frase che va
    interpretata, ed è precisamente il modo in cui a luglio sono entrate in
    archivio 32.675 righe da cancellare.
    Chiesto chiarimento scritto il 10 agosto 2026. Fino alla risposta, fuori.

LA CONSEGUENZA CHE CAMBIA IL CODICE

Calcolare un punteggio di sentiment su un comunicato È una modifica. Sia la
BCE sia ESMA chiedono che una modifica venga dichiarata, e ESMA detta pure il
testo. GDELT non chiede niente del genere, quindi finora il problema non si
era mai posto.

Per questo ogni riga porta `score_source='istituzionale'` e la fonte esatta in
`source`: servono a mostrare la nota di licenza SOLO dove è dovuta, invece di
appiccicarla a tutto il sito.

COSA NON FACCIAMO

Non attacchiamo il macro a tutte le monete. Una decisione sui tassi riguarda
tutto e niente: metterla su venti ticker gonfierebbe i conteggi e falserebbe
le medie, che è esattamente il difetto che abbiamo passato tre giorni a
togliere. Entra solo ciò che nomina un asset seguito oppure parla
esplicitamente di cripto: MiCA, stablecoin, cripto-attività. Il resto è
contesto per un essere umano, non un punteggio.

    python backend/istituzionali.py            # mostra cosa entrerebbe
    python backend/istituzionali.py --salva    # scrive davvero
"""
import argparse
import logging
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger("istituzionali")

# Il testo che ESMA impone a chi trasforma il loro materiale, e che vale come
# formula anche per la BCE ("se lo modifichi, dichiaralo").
DISCLAIMER = (
    "Elaborazione Cheruvo su materiale scaricato dal sito dell'autorità. "
    "L'autorità non avalla questa pubblicazione e non è responsabile di "
    "eventuali violazioni di diritti o danni a terzi."
)

FONTI = {
    "Federal Reserve": {
        "rss": "https://www.federalreserve.gov/feeds/press_all.xml",
        "licenza": "pubblico dominio (opera del governo USA)",
        "attribuzione": "Federal Reserve Board",
        "serve_disclaimer": False,   # pubblico dominio: basta citare la fonte
    },
    "BCE": {
        "rss": "https://www.ecb.europa.eu/rss/press.html",
        "licenza": "riuso libero con citazione della fonte",
        "attribuzione": "Banca centrale europea",
        "serve_disclaimer": True,
    },
    "ESMA": {
        "rss": "https://www.esma.europa.eu/rss.xml",
        "licenza": "riproduzione autorizzata con citazione della fonte",
        "attribuzione": "ESMA",
        "serve_disclaimer": True,
    },
}

# Parole che rendono un comunicato pertinente alle criptovalute anche quando
# non nomina una moneta precisa. MiCA e' il regolamento europeo sulle
# cripto-attivita': un suo aggiornamento riguarda l'intero settore.
CRIPTO = re.compile(
    r"\b(crypto|cripto|cripto-?attivit\w+|crypto-?asset\w*|stablecoin\w*|"
    r"mica|bitcoin|digital\s+euro|euro\s+digitale|cbdc|"
    r"distributed\s+ledger|dlt|tokeni[sz]\w+)\b", re.I)

# I comunicati che non c'entrano niente, per non riempire l'archivio di
# nomine, concorsi e calendari.
RUMORE = re.compile(
    r"\b(vacancy|vacancies|recruitment|procurement|appointment\s+of|"
    r"calendar|agenda|holiday|speech\s+by|obituary|"
    r"personnel|staff\s+changes)\b", re.I)


def _pertinente(titolo: str, termini: dict) -> list[str]:
    """
    A quali asset si riferisce questo comunicato.

    Restituisce l'elenco dei ticker nominati; se non ne nomina nessuno ma
    parla di cripto in generale, restituisce le monete principali, perche' un
    intervento su MiCA le riguarda davvero tutte. Se non e' ne' l'uno ne'
    l'altro, elenco vuoto e la riga non entra.
    """
    if RUMORE.search(titolo):
        return []

    from gdelt_grezzo import MAIUSCOLI
    trovati = [tk for tk, term in termini.items()
               if re.search(r"\b" + re.escape(term) + r"\b", titolo,
                            0 if term in MAIUSCOLI else re.I)]
    if trovati:
        return trovati

    if CRIPTO.search(titolo):
        # Solo le monete con abbastanza notizie da reggere una media: su una
        # alt-coin sottile un singolo comunicato sposterebbe tutto il punteggio.
        return ["BTC-USD", "ETH-USD"]
    return []


def leggi(nome: str, giorni: int = 3) -> list[dict]:
    """I comunicati recenti di una fonte, gia' filtrati per pertinenza."""
    import feedparser
    from gdelt_source import TERMINE_QUERY

    fonte = FONTI[nome]
    d = feedparser.parse(fonte["rss"])
    voci = len(getattr(d, "entries", None) or [])

    # Uno zero deve dire QUALE zero è.
    #
    # I primi tre giri hanno stampato "0 comunicati pertinenti" per tutte e tre
    # le fonti, e da quella riga non si capiva niente: poteva voler dire che i
    # feed avevano cinquanta comunicati e nessuno parlava di cripto, oppure che
    # i feed non stavano arrivando affatto. Sono due situazioni opposte, una si
    # aspetta e l'altra si aggiusta.
    #
    # Il controllo di prima non bastava: guardava `bozo`, che feedparser alza
    # sugli XML malformati, ma un feed spostato che risponde 404 con una pagina
    # HTML valida non è malformato. È solo vuoto, e passava in silenzio.
    if not voci:
        logger.warning("  %-18s NESSUNA VOCE dal feed (%s). Da controllare: %s",
                       nome,
                       str(getattr(d, "bozo_exception", "")) [:60] or "nessun errore segnalato",
                       fonte["rss"])
        return []

    limite = datetime.now(timezone.utc).timestamp() - giorni * 86400
    fuori = []
    letti = 0     # quanti comunicati cadono nella finestra, prima del filtro
    for e in d.entries:
        titolo = (getattr(e, "title", "") or "").strip()
        if not titolo:
            continue

        quando = getattr(e, "published_parsed", None) or getattr(e, "updated_parsed", None)
        if quando:
            import calendar
            ts = calendar.timegm(quando)
            if ts < limite:
                continue
            data = datetime.fromtimestamp(ts, timezone.utc).isoformat()
        else:
            data = datetime.now(timezone.utc).isoformat()

        letti += 1
        for tk in _pertinente(titolo, TERMINE_QUERY):
            fuori.append({
                "ticker": tk,
                "source": f"{fonte['attribuzione']}",
                "title": titolo[:480],
                "summary": "",
                "published_date": data,
                "url": getattr(e, "link", "") or "",
                # Nessun punteggio inventato: 0 e' "non lo so", e la
                # riclassificazione la fara' Groq come per le righe vader.
                "sentiment": 0.0,
                "score_source": "istituzionale",
                "lingua": "eng",
            })

    logger.info("  %-18s %3d voci nel feed, %3d negli ultimi %d giorni, %3d pertinenti",
                nome, voci, letti, giorni, len(fuori))
    if letti and not fuori:
        # Il caso normale, ma va detto che è normale: queste tre fonti
        # pubblicano soprattutto nomine, calendari e vigilanza bancaria, e la
        # cripto passa di lì poche volte al mese. Uno zero qui non è un guasto.
        logger.info("       nessuno di questi parla di cripto o di un asset seguito")
    return fuori


def raccogli(giorni: int = 3, salva: bool = False) -> int:
    from collections import Counter

    tutte: list[dict] = []
    for nome in FONTI:
        # Il conteggio lo stampa `leggi`, che è l'unico posto in cui si sa
        # quante voci sono arrivate prima del filtro.
        tutte.extend(leggi(nome, giorni))

    if not tutte:
        logger.info("Niente di pertinente negli ultimi %d giorni.", giorni)
        return 0

    per_ticker: dict = {}
    for r in tutte:
        per_ticker.setdefault(r["ticker"], []).append(r)

    print("\n" + "=" * 72)
    print("  COSA ENTREREBBE" if not salva else "  COSA E' ENTRATO")
    print("=" * 72 + "\n")
    for r in tutte:
        print(f"  [{r['ticker']:<9}] {r['source']:<24} {r['title'][:60]}")

    fonti = Counter(r["source"] for r in tutte)
    print(f"\n  totale: {len(tutte)} righe, {len(per_ticker)} titoli")
    print("  per fonte: " + ", ".join(f"{k} {v}" for k, v in fonti.items()))

    if not salva:
        print("\n  Niente e' stato scritto. Per scrivere davvero:")
        print("    python backend/istituzionali.py --salva\n")
        return 0

    from quick_fetch import save_news
    salvate = 0
    for tk, righe in per_ticker.items():
        try:
            salvate += save_news(tk, righe)
        except Exception as e:
            logger.error("  %s: errore in salvataggio: %s", tk, e)
    logger.info("Salvate %d righe nuove.", salvate)
    return salvate


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    except ImportError:
        pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--giorni", type=int, default=3,
                    help="quanti giorni indietro leggere (default 3)")
    ap.add_argument("--salva", action="store_true",
                    help="scrive davvero in archivio")
    args = ap.parse_args()
    sys.exit(0 if raccogli(args.giorni, args.salva) >= 0 else 1)
