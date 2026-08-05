"""
verifica_segnale.py — Il sentiment di oggi dice qualcosa sul prezzo di domani?

Questa è la domanda da cui dipende cosa è Cheruvo. Se la risposta è no, il
prodotto è un aggregatore di stampa, che è una cosa onesta e vendibile ma va
raccontata così. Se è sì, è l'unica cosa sul mercato che pubblica quel segnale
e nove euro al mese diventano difendibili.

Non basta calcolare una correlazione. Con novanta giorni di dati si trova
quasi sempre qualcosa, se la si cerca abbastanza: è il motivo per cui la
maggior parte dei backtest amatoriali "funziona" e poi in produzione no.
Quindi qui dentro ci sono più difese contro l'auto-inganno che matematica.

LE DIFESE, e perché ognuna serve.

1. Test di permutazione invece della formula.
   Mescolo i punteggi di sentiment migliaia di volte, distruggendo qualsiasi
   legame con le date, e guardo quanto spesso il caso da solo produce un
   risultato buono quanto il nostro. Non assume che i rendimenti siano
   distribuiti normalmente, cosa che le criptovalute non fanno.

2. Nessuna soglia ottimizzata.
   Provare venti soglie e tenere la migliore garantisce di trovarne una che
   funziona sul passato e su nient'altro. Le soglie qui sono fissate prima di
   guardare i dati, e vengono stampate TUTTE, anche quelle che perdono.

3. Il giorno stesso come controllo.
   La correlazione fra sentiment di oggi e rendimento di OGGI dovrebbe essere
   positiva, perché i giornalisti raccontano il movimento appena avvenuto.
   Se il risultato su domani somiglia a quello su oggi, non abbiamo trovato
   una previsione: abbiamo trovato una fuga di informazione nei tempi.

4. Confronto con compra-e-tieni.
   "La strategia ha guadagnato" non vuol dire niente in un mercato che è
   salito. La domanda è se ha fatto meglio di stare fermo.

5. Correzione per i confronti multipli.
   Provo tre orizzonti (domani, dopodomani, fra una settimana). Provandone
   tre, la probabilità di trovarne uno "significativo" per caso triplica.
   La soglia viene corretta di conseguenza.

Uso:
    python backend/verifica_segnale.py --ticker BTC-USD --giorni 90
"""
import argparse
import logging
import os
import random
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import get_pool  # noqa: E402

logger = logging.getLogger("verifica")

# Fonti di cui abbiamo diritto d'uso: il test gira solo su queste, perché sono
# le uniche che sopravvivranno alla pulizia. Verificare il segnale su dati che
# stiamo per cancellare darebbe un risultato che non possiamo riprodurre.
PREFISSI_LECITI = ("GDELT", "SEC EDGAR", "Alpha Vantage")

# Fissate PRIMA di guardare i dati, e riportate tutte.
SOGLIE = (0.0, 0.1, 0.2)
ORIZZONTI = (1, 2, 7)
GIRI_PERMUTAZIONE = 10000
MINIMO_GIORNI = 30       # sotto questo non si dice niente, si dice che non si sa
MINIMO_NOTIZIE = 5       # un giorno con meno notizie è rumore, non un dato


# ── Statistica, senza dipendenze esterne ──────────────────────────────────
def _ranghi(v: list[float]) -> list[float]:
    """Ranghi con media sui pari merito, per Spearman."""
    ordinati = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(ordinati):
        j = i
        while j + 1 < len(ordinati) and v[ordinati[j + 1]] == v[ordinati[i]]:
            j += 1
        medio = (i + j) / 2 + 1
        for k in range(i, j + 1):
            r[ordinati[k]] = medio
        i = j + 1
    return r


def pearson(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n < 3:
        return 0.0
    mx, my = sum(x) / n, sum(y) / n
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    dx = sum((a - mx) ** 2 for a in x) ** 0.5
    dy = sum((b - my) ** 2 for b in y) ** 0.5
    return num / (dx * dy) if dx and dy else 0.0


def spearman(x: list[float], y: list[float]) -> float:
    """
    Spearman e non Pearson: sui rendimenti crypto un singolo giorno da +18%
    trascina Pearson da solo. Lavorando sui ranghi, quel giorno conta come
    "il più alto" e non come "diciotto volte gli altri".
    """
    return pearson(_ranghi(x), _ranghi(y))


def permutazione(x: list[float], y: list[float], giri: int = GIRI_PERMUTAZIONE) -> float:
    """
    Probabilità che il caso, da solo, produca un legame forte quanto il nostro.

    Mescolo x mille e mille volte: così ogni punteggio di sentiment finisce su
    un giorno a caso e qualunque legame vero sparisce. Se anche il caos
    produce spesso quello che abbiamo trovato, non abbiamo trovato niente.
    """
    vero = abs(spearman(x, y))
    mescolato = list(x)
    almeno_quanto = 0
    for _ in range(giri):
        random.shuffle(mescolato)
        if abs(spearman(mescolato, y)) >= vero:
            almeno_quanto += 1
    # +1 al numeratore e al denominatore: senza, con zero superamenti si
    # riporterebbe p = 0, cioè "impossibile per caso", che nessun test
    # empirico può affermare.
    return (almeno_quanto + 1) / (giri + 1)


# ── Dati ──────────────────────────────────────────────────────────────────
def serie_sentiment(ticker: str, giorni: int) -> dict[date, tuple[float, int]]:
    """Media giornaliera del sentiment, solo dalle fonti che possiamo usare."""
    condizione = " OR ".join(
        f"source LIKE '{p} %' OR source = '{p}'" for p in PREFISSI_LECITI)
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT published_date::date AS giorno,
                   AVG(sentiment)::float AS media,
                   COUNT(*)              AS quante
            FROM news
            WHERE ticker = %s
              -- NON "INTERVAL '%s days'": psycopg2 sostituisce anche dentro
              -- le stringhe quotate e produrrebbe INTERVAL ''90' days',
              -- cioè un errore di sintassi al primo giro.
              AND published_date >= NOW() - (%s * INTERVAL '1 day')
              AND sentiment IS NOT NULL
              AND ({condizione})
            GROUP BY giorno
            ORDER BY giorno
        """, (ticker, giorni))
        righe = cur.fetchall()
        cur.close()
    finally:
        pool.putconn(conn)
    return {r[0]: (r[1], r[2]) for r in righe}


def serie_prezzi(ticker: str, giorni: int) -> dict[date, float]:
    import yfinance as yf
    storico = yf.Ticker(ticker).history(period=f"{giorni + 15}d")
    return {i.date(): float(r["Close"]) for i, r in storico.iterrows()}


def allinea(sent: dict, prezzi: dict, orizzonte: int
            ) -> tuple[list[float], list[float]]:
    """
    Accoppia il sentiment del giorno T col rendimento fra la chiusura di T e
    quella di T+orizzonte.

    Il rendimento parte dalla chiusura di T, non dall'apertura: al momento in
    cui vediamo il sentiment di oggi, la giornata di oggi è già andata. Farlo
    partire prima significherebbe scommettere su un movimento già avvenuto,
    che è il modo classico di produrre un backtest brillante e inutile.
    """
    xs, ys = [], []
    for giorno, (media, quante) in sorted(sent.items()):
        if quante < MINIMO_NOTIZIE:
            continue
        dopo = giorno + timedelta(days=orizzonte)
        if giorno not in prezzi or dopo not in prezzi:
            continue
        p0, p1 = prezzi[giorno], prezzi[dopo]
        if not p0:
            continue
        xs.append(media)
        ys.append((p1 - p0) / p0)
    return xs, ys


def confronto_strategia(xs, ys, soglia):
    """
    Rendimento cumulato comprando solo dopo un sentiment sopra soglia, contro
    quello di chi resta investito e basta.
    """
    dentro = [y for x, y in zip(xs, ys) if x > soglia]
    tutti = ys
    def cum(serie):
        montante = 1.0
        for r in serie:
            montante *= (1 + r)
        return montante - 1
    return {
        "giorni_dentro": len(dentro),
        "rendimento_strategia": cum(dentro),
        "rendimento_sempre": cum(tutti),
        "media_dentro": sum(dentro) / len(dentro) if dentro else 0.0,
        "media_fuori": (sum(y for x, y in zip(xs, ys) if x <= soglia) /
                        max(1, len(tutti) - len(dentro))),
    }


# ── Il verdetto ───────────────────────────────────────────────────────────
def analizza(ticker: str, giorni: int) -> int:
    print()
    print("=" * 70)
    print(f"  IL SENTIMENT ANTICIPA IL PREZZO?  —  {ticker}, ultimi {giorni} giorni")
    print("=" * 70)

    sent = serie_sentiment(ticker, giorni)
    if not sent:
        print("\nNessuna notizia da fonti lecite per questo titolo. Non c'è")
        print("niente da verificare: prima serve il backfill da GDELT.")
        return 1

    prezzi = serie_prezzi(ticker, giorni)
    usabili = {g: v for g, v in sent.items() if v[1] >= MINIMO_NOTIZIE}
    print(f"\nGiorni con notizie:            {len(sent)}")
    print(f"Giorni con almeno {MINIMO_NOTIZIE} notizie:  {len(usabili)}")
    print(f"Notizie totali (fonti lecite): {sum(v[1] for v in sent.values())}")

    if len(usabili) < MINIMO_GIORNI:
        print()
        print(f"FERMO QUI. Servono almeno {MINIMO_GIORNI} giorni utilizzabili e ce ne")
        print(f"sono {len(usabili)}. Con meno, qualunque risultato sarebbe indistinguibile")
        print("dal caso: non è che il segnale non c'è, è che non si può sapere.")
        print("Rilancia dopo aver ricostruito più storico.")
        return 2

    # Il controllo: sul giorno STESSO ci aspettiamo un legame, perché i
    # giornali raccontano il movimento appena avvenuto.
    x0, y0 = allinea(sent, prezzi, 0)
    rho0 = spearman(x0, y0) if len(x0) >= 3 else 0.0
    print(f"\nControllo sul giorno stesso:   rho = {rho0:+.3f}  su {len(x0)} giorni")
    print("  (qui un legame POSITIVO è atteso e non prova niente: è la stampa")
    print("   che racconta quello che il prezzo ha già fatto)")

    # Soglia corretta per il numero di orizzonti provati.
    soglia_p = 0.05 / len(ORIZZONTI)
    print(f"\nProvo {len(ORIZZONTI)} orizzonti, quindi la soglia di significatività")
    print(f"scende da 0,050 a {soglia_p:.3f}: provandone tre, trovarne uno")
    print("per caso è tre volte più facile.")

    risultati = []
    for h in ORIZZONTI:
        xs, ys = allinea(sent, prezzi, h)
        if len(xs) < MINIMO_GIORNI:
            print(f"\n── T+{h}: solo {len(xs)} giorni allineati, salto")
            continue
        rho = spearman(xs, ys)
        p = permutazione(xs, ys)
        vinto = p < soglia_p
        risultati.append((h, rho, p, vinto, len(xs)))

        print(f"\n── T+{h} giorni  ({len(xs)} osservazioni)")
        print(f"   correlazione di rango  rho = {rho:+.3f}")
        print(f"   probabilità che sia caso   p = {p:.4f}   "
              f"{'SOTTO la soglia' if vinto else 'sopra la soglia: compatibile col caso'}")

        for s in SOGLIE:
            c = confronto_strategia(xs, ys, s)
            if c["giorni_dentro"] < 5:
                print(f"   soglia {s:+.1f}: solo {c['giorni_dentro']} giorni, non commentabile")
                continue
            print(f"   soglia {s:+.1f}: dentro {c['giorni_dentro']:>3} giorni  |  "
                  f"strategia {c['rendimento_strategia']:+7.1%}  contro  "
                  f"compra-e-tieni {c['rendimento_sempre']:+7.1%}")

    print("\n" + "=" * 70)
    print("  VERDETTO")
    print("=" * 70)
    vincenti = [r for r in risultati if r[3]]
    if not risultati:
        print("\nDati insufficienti su tutti gli orizzonti.")
        return 2
    if not vincenti:
        print("\nNESSUN SEGNALE DIMOSTRABILE.")
        print("\nSu tutti gli orizzonti provati, quello che si osserva è compatibile")
        print("con il caso. Questo NON dimostra che il segnale non esista: con")
        print(f"{risultati[0][4]} giorni si vedono solo effetti grossi. Dimostra che")
        print("oggi non hai le prove per affermarlo, e quindi non puoi venderlo")
        print("come tale.")
        print("\nLa strada onesta è raccontare Cheruvo per quello che fa davvero:")
        print("leggere la stampa al posto tuo e dirti che aria tira, senza")
        print("promettere che anticipi il prezzo.")
        return 0
    print("\nQUALCOSA C'È, e va guardato con sospetto prima che con entusiasmo.")
    for h, rho, p, _, n in vincenti:
        print(f"\n  T+{h}: rho = {rho:+.3f}, p = {p:.4f} su {n} giorni")
    if abs(rho0) > 0.15 and any(abs(r[1]) > 0.15 for r in vincenti):
        print("\n  ATTENZIONE: anche il controllo sul giorno stesso è forte.")
        print("  Prima di crederci va escluso che sia una fuga nei tempi, cioè")
        print("  notizie datate al giorno T che in realtà escono a mercato già")
        print("  mosso.")
    print("\n  Prima di scriverlo sul sito: rifallo fra un mese sui dati nuovi.")
    print("  Un risultato che regge su dati mai visti vale, uno trovato")
    print("  guardando il passato è un'ipotesi.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ticker", default="BTC-USD")
    ap.add_argument("--giorni", type=int, default=90)
    args = ap.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    except ImportError:
        pass

    random.seed(20260805)   # riproducibile: due giri danno lo stesso p
    sys.exit(analizza(args.ticker, args.giorni))
