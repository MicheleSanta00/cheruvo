"""
misura_sbilanciamento.py — Le notizie che il filtro vecchio buttava erano
piu' negative delle altre?

LA DOMANDA, E PERCHE' IL CONTEGGIO NON BASTA

Il 15 agosto 2026 e' saltato fuori che CONTESTO faceva passare gli utili e
bocciava le perdite: c'erano "gewinn", "beneficios", "ganancias", "lucro",
"utile netto", e nessuna parola di perdita in nessuna lingua.

    PASSA   SAP meldet Gewinn im zweiten Quartal
    BOCCIA  SAP meldet Verlust im zweiten Quartal

Aggiunte le parole mancanti, rilanciando `--modo contesto` sulle stesse 24
ore le righe ammesse sono passate da 336 a 407. Ma quel +5,6% (tolto un
articolo su AMD ripreso da mezzo mondo) dice QUANTE righe in piu' entrano,
non se erano piu' negative. Se le notizie perse erano negative quanto le
altre, l'archivio storico e' solo piu' piccolo. Se erano piu' negative,
l'archivio e' anche spinto in alto, e allora il backfill serve davvero.

COME SI MISURA

Due gruppi presi dalla STESSA finestra e punteggiati dallo STESSO valutatore,
cosi' l'unica cosa che cambia fra i due e' il filtro:

    A  le righe che il filtro vecchio ammetteva gia'
    B  le righe che entrano SOLO col vocabolario nuovo

Se la media di B sta sotto quella di A, quello che si buttava via era la
parte cattiva delle notizie. Le due medie arrivano con la loro banda al 95%,
e la differenza pure: se la banda della differenza comprende lo zero, questa
misura non ha deciso niente, e va detto invece di arrotondare a favore.

Il confronto con la media dell'archivio NON si fa: le righe in archivio sono
state punteggiate da modelli diversi in mesi diversi, e si finirebbe per
misurare il cambio di modello.

COSTA TOKEN

Punteggia `--quante` titoli per gruppo (60 di default, 120 in tutto) con lo
stesso `score_batch` della produzione. Sul piano gratuito di Groq e' poca
roba, ma non e' zero: il conto esatto viene stampato prima di partire.

NON SCRIVE NIENTE. Legge, punteggia in memoria, stampa.

    python backend/misura_sbilanciamento.py --ore 24
    python backend/misura_sbilanciamento.py --ore 6 --quante 25
"""
import argparse
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# IL VOCABOLARIO DI PRIMA, CONGELATO
#
# Questa e' la copia esatta di CONTESTO com'era fino al 15 agosto 2026, prima
# che ci entrassero le perdite. NON va tenuta allineata a quella vera: il suo
# lavoro e' proprio restare indietro, se no non c'e' piu' niente da
# confrontare. Se un domani si rifa' la stessa misura per un'altra aggiunta,
# si congela un'altra copia con un'altra data e si lascia questa dov'e'.
CONTESTO_PRIMA = re.compile(
    r"\b(crypto|cryptocurrenc\w*|token|coin|blockchain|defi|wallet|"
    r"stock|shares?|trading|traders?|price|nasdaq|earnings|"
    r"nyse|ftse|dax|investor\w*|dividend\w*|ipo|revenue|profit\w*|"
    r"quarterly|valuation|analysts?|etf\w*|futures|"
    r"markets|(?:stock|crypto|bear|bull|equity|financial|currency)\s+market|"
    r"market\s+(?:cap|close|open|rally|selloff|sell-off)|"
    r"downgrade\w*|upgrade[sd]?|rating|outperform|underperform|"
    r"overweight|underweight|price\s+target|target\s+price|"
    r"piazza\s+affari|seduta\s+(?:borsistica|di\s+borsa)|"
    r"capitalizzazion\w+|obbligazion\w+|riacquisto\s+di\s+azioni|buyback|"
    r"borsa|azion\w+|quotazion\w+|criptovalut\w+|"
    r"mercati|mercato\s+(?:azionario|crypto|obbligazionario|valutario)|"
    r"investitor\w+|trimestral\w+|ricavi|analist\w+|"
    r"declass\w+|promuov\w+|giudizio|rendiment\w+|utile\s+netto|"
    r"prezzo|titol\w+|投資|bourse|aktie\w*|"
    r"anleger\w*|analysten|b[öo]rse|kursziel|herabgestuft|hochgestuft|"
    r"quartalszahlen|umsatz|gewinn\w*|"
    r"bolsa|acciones|inversor\w+|cotizaci[óo]n|criptomoneda\w*|"
    r"mercados|beneficios|ganancias|rebaja\s+de\s+calificaci[óo]n|"
    r"a[çc][õo]es|investidor\w+|cripto\w*|lucro\w*|"
    r"actions?\s+(?:cot[ée]e?s?|du\s+groupe)|d[ée]gradation|rel[èe]vement|"
    r"analystes?|investisseur\w+|r[ée]sultats\s+trimestriels|"
    r"objectif\s+de\s+cours|cryptomonnaie\w*)\b", re.I)


# ══ La parte che si puo' provare senza rete ══════════════════════════════
def separa(titoli: list[str], termini: dict) -> tuple[list, list]:
    """
    Divide i titoli che parlano di un ticker seguito in due gruppi:
    quelli che il filtro vecchio ammetteva gia' e quelli che entrano solo
    adesso.

    Un titolo che nemmeno il filtro nuovo ammette non sta in nessuno dei due:
    non c'entra con questa domanda.
    """
    from gdelt_grezzo import CONTESTO, MAIUSCOLI, serve_contesto

    # Stessa costruzione di `conta_pertinenti`: confini di parola sempre, e
    # maiuscole rispettate per le sigle che sono anche parole comuni. Se un
    # domani quella cambia, questa va cambiata insieme, se no i due gruppi
    # non sono piu' fatti delle stesse righe.
    rx = {tk: re.compile(r"\b" + re.escape(term) + r"\b",
                         0 if term in MAIUSCOLI else re.I)
          for tk, term in termini.items()}

    prima, adesso = [], []
    for t in titoli:
        tk = next((tk for tk, p in rx.items() if p.search(t)), None)
        if tk is None:
            continue
        if not serve_contesto(tk, termini[tk]):
            continue          # niente contesto richiesto: il filtro non c'entra
        if CONTESTO_PRIMA.search(t):
            prima.append(t)
        elif CONTESTO.search(t):
            adesso.append(t)
    return prima, adesso


def media_con_banda(valori: list[float]) -> dict:
    """Media, dispersione e banda al 95%. Sotto i 5 valori non si pronuncia."""
    n = len(valori)
    if n < 5:
        return {"n": n, "media": None, "lo": None, "hi": None, "dev": None}
    media = sum(valori) / n
    dev = (sum((v - media) ** 2 for v in valori) / (n - 1)) ** 0.5
    errore = dev / n ** 0.5
    return {"n": n, "media": round(media, 3), "dev": round(dev, 3),
            "lo": round(media - 1.96 * errore, 3),
            "hi": round(media + 1.96 * errore, 3)}


def differenza(a: list[float], b: list[float]) -> dict:
    """
    Quanto sta sotto il gruppo B rispetto ad A, con la sua banda.

    Errore standard alla Welch, che non pretende che i due gruppi abbiano la
    stessa dispersione: non hanno motivo di averla.
    """
    if len(a) < 5 or len(b) < 5:
        return {"delta": None, "lo": None, "hi": None}
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    va = sum((v - ma) ** 2 for v in a) / (len(a) - 1)
    vb = sum((v - mb) ** 2 for v in b) / (len(b) - 1)
    errore = (va / len(a) + vb / len(b)) ** 0.5
    delta = mb - ma
    # I valori tondi servono a stamparli, quelli interi a decidere. Il primo
    # giro vero, il 16 agosto 2026, e' finito con la banda che arrivava a
    # -0.0004: arrotondata diventa "-0.000", e "0 <= -0.000" in Python e'
    # vero, quindi il verdetto usciva dal ramo sbagliato. Una decisione da un
    # giga di riscaricamento non puo' dipendere da come si arrotonda.
    return {"delta": round(delta, 3),
            "lo": round(delta - 1.96 * errore, 3),
            "hi": round(delta + 1.96 * errore, 3),
            "_delta": delta,
            "_lo": delta - 1.96 * errore,
            "_hi": delta + 1.96 * errore}


def verdetto(d: dict) -> str:
    """
    Cosa ha deciso la misura, detto in una riga.

    Ci sono quattro esiti e non tre, perche' il primo giro vero e' finito con
    la banda che sfiorava lo zero da sotto. Chiamarlo "confermato" per via del
    quarto decimale sarebbe la stessa cosa della soglia inventata a 0.6 che
    passava per 0.003, cioe' far dire alla misura quello che si sperava.

    Il limite e' relativo e non assoluto: se il bordo della banda dista dallo
    zero meno di un decimo dell'effetto che si sta misurando, quell'effetto
    non e' separato dallo zero in modo utile. E' una convenzione, come lo e'
    il 95%, ed e' scritta qui invece che nascosta in un numero.
    """
    if d["delta"] is None:
        return ("Troppi pochi titoli punteggiati per dire qualcosa. "
                "Rilancia con --ore piu' alto.")
    lo, hi, delta = d.get("_lo", d["lo"]), d.get("_hi", d["hi"]), d.get("_delta", d["delta"])
    if lo <= 0 <= hi:
        return ("NON DECIDE. La banda della differenza comprende lo zero: "
                "non si distingue uno sbilanciamento dal caso. Il backfill "
                "non ha una ragione misurata.")
    if min(abs(lo), abs(hi)) < abs(delta) / 10:
        return ("AL LIMITE. La banda esclude lo zero ma lo sfiora, quindi "
                "basterebbe un titolo in piu' o in meno per ribaltare il "
                "verdetto. Non e' una risposta: rilancia usando TUTTI i "
                "titoli disponibili invece di un campione (--quante 0).")
    if hi < 0:
        return ("SBILANCIAMENTO CONFERMATO. Le notizie che il filtro vecchio "
                "buttava erano piu' negative delle altre, quindi l'archivio "
                "storico e' spinto in alto e il backfill serve.")
    return ("Al contrario: le righe perse erano piu' POSITIVE delle altre. "
            "L'archivio storico e' spinto in basso, non in alto.")


# ══ La parte che ha bisogno di rete e di Groq ════════════════════════════
def _punteggia(titoli: list[str]) -> list[float]:
    """I punteggi dello stesso valutatore che gira in produzione."""
    from sentiment_groq import score_batch

    fuori = []
    blocchi = (len(titoli) + 19) // 20
    for i in range(0, len(titoli), 20):
        n = i // 20 + 1
        print(f"    blocco {n} di {blocchi}...", end=" ", flush=True)
        pezzo = [{"title": t, "summary": ""} for t in titoli[i:i + 20]]
        punti = score_batch(pezzo)
        if punti is None:
            print("Groq non ha risposto, lo salto.", flush=True)
            continue
        validi = [float(p) for p in punti if p is not None]
        fuori.extend(validi)
        print(f"{len(validi)} punteggi", flush=True)
    return fuori


def misura(ore: int, quante: int, seme: int = 11) -> int:
    from gdelt_grezzo import righe_della_finestra, titolo
    from gdelt_source import TERMINE_QUERY

    print("=" * 76)
    print("  LE NOTIZIE CHE IL FILTRO BUTTAVA ERANO PIU' NEGATIVE?")
    print("=" * 76)
    print(f"\n  {ore} ore di file, entrambi i feed, {len(TERMINE_QUERY)} titoli.")
    print(f"  Sto per scaricare circa {ore * 8} file da GDELT, "
          f"grosso modo {ore * 40} MB. Ci vogliono dei minuti.\n", flush=True)

    righe, ok, ko = righe_della_finestra(ore)
    if not righe:
        print("  Nessuna riga letta.")
        return 1
    print(f"  file letti: {ok} ({ko} non disponibili), righe: {len(righe)}\n")

    titoli = [t for t in (titolo(r) for r in righe) if t]
    prima, adesso = separa(titoli, TERMINE_QUERY)
    print(f"  ammesse gia' prima:      {len(prima)}")
    print(f"  entrano solo adesso:     {len(adesso)}")

    if len(adesso) < 5:
        print("\n  Troppo poche per misurare. Serve una finestra piu' lunga.")
        return 1

    rnd = random.Random(seme)
    tetto = quante if quante > 0 else max(len(prima), len(adesso))
    a = rnd.sample(prima, min(tetto, len(prima)))
    b = rnd.sample(adesso, min(tetto, len(adesso)))
    print(f"\n  Da punteggiare: {len(a)} + {len(b)} = {len(a) + len(b)} titoli.")
    if len(a) < len(prima) or len(b) < len(adesso):
        print(f"  (ne sono disponibili {len(prima)} + {len(adesso)}: "
              f"con --quante 0 si usano tutti e la banda si stringe)")
    print("  Stesso modello della produzione. Non viene scritta nessuna riga.\n")

    print("  gruppo A, ammesse gia' prima:", flush=True)
    va = _punteggia(a)
    print("  gruppo B, entrano solo adesso:", flush=True)
    vb = _punteggia(b)
    print()
    ma, mb = media_con_banda(va), media_con_banda(vb)

    print("  gruppo                      n    media      banda 95%")
    print("  " + "-" * 60)
    for nome, m in (("ammesse gia' prima", ma), ("entrano solo adesso", mb)):
        if m["media"] is None:
            print(f"  {nome:24} {m['n']:4}    troppo poche")
        else:
            print(f"  {nome:24} {m['n']:4}   {m['media']:+.3f}   "
                  f"da {m['lo']:+.3f} a {m['hi']:+.3f}")

    d = differenza(va, vb)
    print()
    if d["delta"] is not None:
        print(f"  differenza (adesso meno prima): {d['delta']:+.3f}, "
              f"banda da {d['lo']:+.3f} a {d['hi']:+.3f}")
    print()
    print("=" * 76)
    for riga in _a_capo(verdetto(d), 72):
        print(f"  {riga}")
    print("=" * 76)
    print("\n  Nessuna riga e' stata scritta.\n")
    return 0


def _a_capo(testo: str, largo: int) -> list[str]:
    righe, corrente = [], ""
    for parola in testo.split():
        if len(corrente) + len(parola) + 1 > largo:
            righe.append(corrente)
            corrente = parola
        else:
            corrente = f"{corrente} {parola}".strip()
    if corrente:
        righe.append(corrente)
    return righe


if __name__ == "__main__":
    import logging

    # SENZA QUESTA RIGA SEMBRA BLOCCATO
    #
    # `leggi_gkg` racconta quello che scarica con logger.info, e il livello
    # predefinito e' WARNING: senza configurare il logging, il programma
    # scarica 192 file per circa un giga in silenzio assoluto, per parecchi
    # minuti. La prima volta che e' stato lanciato e' sembrato piantato, e non
    # lo era: era muto. `gdelt_grezzo` la stessa riga ce l'ha da sempre.
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    except ImportError:
        pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ore", type=int, default=24,
                    help="quante ore di file leggere (default 24)")
    ap.add_argument("--quante", type=int, default=60,
                    help="titoli da punteggiare per gruppo (default 60)")
    args = ap.parse_args()
    sys.exit(misura(args.ore, args.quante))
