"""
anomalie.py — Quanto è strana oggi una moneta, rispetto a se stessa.

PERCHÉ ESISTE

Fino al 7 agosto 2026 il prodotto mostrava un LIVELLO: "BTC −0,08". Un livello
non è un'informazione, perché non dice se quel numero è normale. L'utente lo
legge e non può farci niente.

Lo stesso difetto stava nell'alert via email, che scattava su
`ABS(AVG(sentiment)) > 0.2`: una soglia fissa. Scriveva per una moneta con tre
articoli sopra 0,2 e restava zitto il giorno in cui il volume di notizie su
Bitcoin triplicava. Avvisava quando il numero era alto, mai quando era
CAMBIATO.

Qui si misura invece lo scarto dalla normalità della moneta stessa. "Il
sentiment su SOL sta due deviazioni sotto la sua norma delle ultime quattro
settimane, col triplo delle notizie del solito" è un'affermazione SULLE
NOTIZIE, che possiamo dimostrare, non sul PREZZO, che non possiamo. È utile e
vera nello stesso momento, e non richiede di aspettare il verdetto di
`verifica_segnale.py`.

TRE SCELTE STATISTICHE, E IL MOTIVO

1. Mediana e MAD, non media e deviazione standard.
   Con quattro settimane di dati, un solo giorno di picco passato gonfia la
   deviazione standard abbastanza da nascondere tutti i picchi futuri: il
   rilevatore si acceca da solo proprio dopo aver visto la cosa che doveva
   rilevare. La mediana e lo scarto assoluto mediano non hanno quel problema.
   Il fattore 1,4826 riporta il MAD sulla scala di una deviazione standard,
   così le soglie restano leggibili come "due sigma".

2. Un pavimento di Poisson sul volume.
   Se una moneta ha esattamente 8 articoli per venti giorni di fila, il MAD è
   zero e qualunque scostamento diventerebbe infinito. Ma un conteggio che vale
   in media 8 oscilla naturalmente di ±√8, cioè ±2,8, anche se non succede
   niente. Quel √mediana è il minimo di rumore che un conteggio ha per natura,
   e usarlo come pavimento evita di gridare al picco per un +1.

3. Si confronta la QUOTA, non il conteggio nudo.
   Il sabato escono meno notizie su tutto. Senza correzione ogni sabato
   sembrerebbe un crollo di interesse per ogni moneta, e ogni lunedì un boom.
   Confrontare la quota di attenzione (articoli della moneta / articoli di
   quel giorno) toglie di mezzo l'effetto del giorno della settimana senza
   dover modellare niente.

QUANDO NON SI SA

L'archivio riparte dal 6 agosto 2026, e il 7 agosto le regole di raccolta sono
cambiate parecchio. Qualunque normalità calcolata adesso descriverebbe le
nostre modifiche, non il mercato. Sotto `MINIMO_GIORNI` il modulo NON stima
niente e dichiara di stare ancora imparando: è la stessa disciplina di
`verifica_segnale.py`, che sa dire "non lo so".

    python backend/anomalie.py            # stampa cosa vede oggi
"""
import logging
import math
import os
import sys
from datetime import date, datetime, timezone

logger = logging.getLogger(__name__)

FINESTRA_ORE = 24        # cosa chiamiamo "oggi"
BASELINE_GIORNI = 28     # la normalità: le quattro settimane precedenti
MINIMO_GIORNI = 14       # sotto questo si dice "non lo so"

# Il giorno in cui le regole di raccolta sono cambiate, e prima del quale i
# dati NON sono confrontabili con quelli di oggi.
#
# Questa riga è nata da un errore vero, trovato guardando la prima risposta in
# produzione. Il modulo diceva "normale" per Bitcoin ed Ethereum, e sembrava
# giusto: hanno più di quattordici giorni di storico, grazie alla
# ricostruzione da GDELT. Solo che quello storico è stato raccolto con le
# regole VECCHIE, prima che il filtro di contesto tagliasse il 72% del volume
# e prima che un articolo potesse valere per più monete.
#
# Confrontare oggi con quei giorni vuol dire misurare le nostre modifiche e
# chiamarle mercato. Il paragone sulla quota di attenzione attutisce il
# problema (se cala tutto, le quote restano), ma non lo cancella: il taglio ha
# colpito le azioni molto più delle monete, quindi la quota delle monete è
# salita per una ragione che non ha niente a che fare con le notizie.
#
# `MINIMO_GIORNI` da solo non bastava, perché conta i giorni disponibili e non
# sa che il primo agosto e il sette agosto misurano cose diverse. Con questa
# data il rilevatore tace fino al 21 agosto 2026 e poi comincia a parlare su
# dati omogenei, che è esattamente quello che avevo promesso e che il codice
# non faceva.
DA_QUANDO = date(2026, 8, 7)
MINIMO_MEDIANA = 2.0     # una moneta con meno di 2 articoli al giorno tipici
                         # non ha una normalità da cui scostarsi
FATTORE_MAD = 1.4826     # porta il MAD sulla scala di una deviazione standard

# Oltre quante deviazioni si chiama anomalia.
#
# Questo numero è stato MISURATO, non scelto. La prima versione stava a 2σ,
# che suona ragionevole e non lo è: simulando giornate in cui non succede
# niente (conteggi di Poisson puri, tono rumore gaussiano) produceva
# **34 avvisi falsi a settimana** su quaranta monete. Cinque al giorno di
# nulla. Un rilevatore così non viene più letto dopo tre giorni, ed è il modo
# più efficiente di rendere inutile una funzione utile.
#
# Due sono i motivi per cui 2σ è troppo poco qui. Ogni moneta porta DUE prove
# indipendenti (volume e tono), e le prove sono quaranta al giorno: a forza di
# guardare, il caso produce da solo qualcosa di apparentemente raro. In più il
# MAD stimato su ventotto punti è esso stesso rumoroso, quindi la soglia vera
# è più larga di quella nominale.
#
# La misura, con 3.000 giornate simulate per riga:
#
#     soglia   falsi/settimana su 40 monete
#     2,0σ           34,0
#     2,5σ           12,7
#     3,0σ            6,2
#     4,0σ            0,9      ← scelta
#     5,0σ            0,1
#
# A 4σ passa meno di un falso allarme a settimana, e resta abbastanza
# sensibile da servire:
#
#     volume di una moneta media (15 notizie/giorno): ×2,5 rilevato l'83%
#       delle volte, ×3 il 97%, ×4 sempre
#     volume di Bitcoin (80 notizie/giorno): ×2 rilevato sempre
#     tono: uno stacco di 0,7 rilevato il 71% delle volte, di 1,0 il 98%
#
# Cioè: i raddoppi piccoli sfuggono, i fatti veri no. È il compromesso giusto
# per una cosa che finisce in una email: meglio perdere un evento tiepido che
# spendere la fiducia di chi legge.
#
# Se un giorno le monete diventano cento invece di quaranta, questa soglia va
# rialzata, perché il numero di prove giornaliere cresce con loro.
SOGLIA_Z = 4.0


def mediana(valori: list[float]) -> float:
    if not valori:
        return 0.0
    v = sorted(valori)
    n = len(v)
    meta = n // 2
    return v[meta] if n % 2 else (v[meta - 1] + v[meta]) / 2


def mad(valori: list[float]) -> float:
    """Scarto assoluto mediano, già riportato sulla scala di una sigma."""
    if not valori:
        return 0.0
    m = mediana(valori)
    return FATTORE_MAD * mediana([abs(v - m) for v in valori])


def scarto(oggi: float, storico: list[float], pavimento: float = 0.0):
    """
    Di quante deviazioni oggi si stacca dalla normalità.

    Restituisce None quando la dispersione è indistinguibile da zero e non
    c'è un pavimento: senza dispersione ogni scostamento sarebbe infinito, e
    un infinito in classifica è un numero inventato con l'aria di una misura.
    """
    if not storico:
        return None
    tipico = mediana(storico)
    dispersione = max(mad(storico), pavimento)
    if dispersione <= 0:
        return None
    return (oggi - tipico) / dispersione


def _giorni_per_ticker(pool) -> tuple[dict, dict, dict]:
    """
    Tre dizionari: conteggi giornalieri, toni giornalieri, totale del giorno.

    Una query sola invece di una per moneta. Con quaranta monete e quattro
    settimane sarebbero milleduecento interrogazioni per disegnare una
    schermata, su un database che sta sul piano gratuito.
    """
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT ticker,
                   DATE(published_date) AS giorno,
                   COUNT(*)             AS n,
                   AVG(sentiment)       AS tono
            FROM news
            WHERE published_date >= NOW() - INTERVAL '{int(BASELINE_GIORNI) + 2} days'
            GROUP BY ticker, DATE(published_date)
            ORDER BY giorno
        """)
        righe = cur.fetchall()
        cur.close()
    finally:
        pool.putconn(conn)

    conteggi: dict = {}
    toni: dict = {}
    totale_giorno: dict = {}
    for ticker, giorno, n, tono in righe:
        conteggi.setdefault(ticker, {})[giorno] = int(n)
        toni.setdefault(ticker, {})[giorno] = float(tono if tono is not None else 0)
        totale_giorno[giorno] = totale_giorno.get(giorno, 0) + int(n)
    return conteggi, toni, totale_giorno


def _per_ticker(ticker: str, conteggi: dict, toni: dict,
                totale_giorno: dict, oggi) -> dict:
    # I giorni prima del cambio di regole non contano: vedi DA_QUANDO.
    giorni = sorted(g for g in conteggi if g < oggi and g >= DA_QUANDO)
    disponibili = len(giorni)

    n_oggi = conteggi.get(oggi, 0)
    tono_oggi = toni.get(oggi)
    tot_oggi = totale_giorno.get(oggi, 0)

    base = {
        "ticker": ticker,
        "notizie_oggi": n_oggi,
        "sentiment_oggi": round(tono_oggi, 3) if tono_oggi is not None else None,
        "giorni_di_storico": disponibili,
    }

    if disponibili < MINIMO_GIORNI:
        # Non è un errore, è una risposta: stiamo ancora imparando com'è
        # fatta la normalità di questa moneta.
        return {**base, "stato": "in_apprendimento",
                "giorni_mancanti": MINIMO_GIORNI - disponibili,
                "z_volume": None, "z_tono": None,
                "notizie_tipiche": None, "sentiment_tipico": None}

    # Quota di attenzione invece del conteggio nudo: toglie di mezzo il
    # sabato, quando escono meno notizie su tutto.
    quote = [conteggi[g] / totale_giorno[g] for g in giorni if totale_giorno.get(g)]
    quota_oggi = n_oggi / tot_oggi if tot_oggi else 0.0

    storico_conteggi = [conteggi[g] for g in giorni]
    mediana_conteggi = mediana(storico_conteggi)

    if mediana_conteggi < MINIMO_MEDIANA:
        return {**base, "stato": "troppo_poche",
                "z_volume": None, "z_tono": None,
                "notizie_tipiche": round(mediana_conteggi, 1),
                "sentiment_tipico": None}

    # Il pavimento di Poisson vive sulla scala dei conteggi, quindi va
    # convertito in quota prima di confrontarlo con la dispersione delle quote.
    pavimento_conteggi = math.sqrt(max(mediana_conteggi, 1.0))
    pavimento_quota = (pavimento_conteggi / mediana_conteggi) * mediana(quote) if quote else 0.0

    z_vol = scarto(quota_oggi, quote, pavimento_quota)
    storico_toni = [toni[g] for g in giorni if g in toni]
    z_tono = scarto(tono_oggi, storico_toni) if tono_oggi is not None else None

    anomala = ((z_vol is not None and abs(z_vol) >= SOGLIA_Z)
               or (z_tono is not None and abs(z_tono) >= SOGLIA_Z))

    return {**base,
            "stato": "anomalia" if anomala else "normale",
            "z_volume": round(z_vol, 2) if z_vol is not None else None,
            "z_tono": round(z_tono, 2) if z_tono is not None else None,
            "notizie_tipiche": round(mediana_conteggi, 1),
            "sentiment_tipico": round(mediana(storico_toni), 3) if storico_toni else None}


def calcola(pool=None) -> list[dict]:
    """
    Una riga per moneta, ordinate per quanto sono strane oggi.

    Le monete "in apprendimento" restano nell'elenco e non vengono nascoste:
    sapere che di una moneta non sappiamo ancora dire niente è un'informazione,
    e nasconderla farebbe sembrare l'archivio più maturo di quello che è.
    """
    if pool is None:
        from database import get_pool
        pool = get_pool()

    conteggi, toni, totale_giorno = _giorni_per_ticker(pool)
    if not totale_giorno:
        return []

    oggi = max(totale_giorno)
    fuori = [_per_ticker(t, conteggi.get(t, {}), toni.get(t, {}),
                         totale_giorno, oggi)
             for t in sorted(conteggi)]

    def forza(r):
        return max(abs(r["z_volume"] or 0), abs(r["z_tono"] or 0))

    fuori.sort(key=forza, reverse=True)
    return fuori


def solo_anomalie(righe: list[dict]) -> list[dict]:
    """Le sole righe che meritano un avviso. È il filtro che usa l'email."""
    return [r for r in righe if r["stato"] == "anomalia"]


def _descrivi(r: dict) -> str:
    if r["stato"] == "in_apprendimento":
        return (f"{r['ticker']:<11} sto ancora imparando la sua normalità "
                f"(mancano {r['giorni_mancanti']} giorni)")
    if r["stato"] == "troppo_poche":
        return (f"{r['ticker']:<11} troppe poche notizie per avere una "
                f"normalità ({r['notizie_tipiche']} al giorno)")
    pezzi = [f"{r['ticker']:<11} {r['notizie_oggi']:>3} notizie "
             f"(tipiche {r['notizie_tipiche']})"]
    if r["z_volume"] is not None:
        pezzi.append(f"volume {r['z_volume']:+.1f}σ")
    if r["z_tono"] is not None:
        pezzi.append(f"tono {r['z_tono']:+.1f}σ")
    if r["stato"] == "anomalia":
        pezzi.append("← ANOMALIA")
    return "  ".join(pezzi)


def main() -> int:
    righe = calcola()
    if not righe:
        print("Nessun dato: l'archivio è vuoto.")
        return 0

    print("=" * 72)
    print(f"  ANOMALIE — {datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC")
    print("=" * 72)
    print(f"\n  Confronto: ultime {FINESTRA_ORE} ore contro i {BASELINE_GIORNI}")
    print(f"  giorni precedenti. Servono almeno {MINIMO_GIORNI} giorni di")
    print(f"  storico per dire qualcosa, e una soglia di {SOGLIA_Z}σ per")
    print("  chiamarla anomalia.\n")

    anomale = solo_anomalie(righe)
    apprendimento = [r for r in righe if r["stato"] == "in_apprendimento"]

    for r in righe:
        print("  " + _descrivi(r))

    print("\n" + "─" * 72)
    print(f"  monete guardate: {len(righe)}")
    print(f"  anomalie oggi: {len(anomale)}")
    if apprendimento:
        manca = max(r["giorni_mancanti"] for r in apprendimento)
        print(f"  ancora in apprendimento: {len(apprendimento)} "
              f"(la più indietro fra {manca} giorni)")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    except ImportError:
        pass
    sys.exit(main())
