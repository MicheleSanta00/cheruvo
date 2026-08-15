"""
etichetta.py — Cinquanta titoli punteggiati da un essere umano.

PERCHE' SERVE, E PERCHE' NON SI PUO' EVITARE

L'11 agosto 2026 un utente su Reddit ha chiesto come vengono etichettate le
notizie. La risposta era: non vengono etichettate. Non esiste nessun insieme
annotato contro cui dire se un punteggio e' giusto.

Da li' sono stati messi a confronto i due valutatori che ci sono in casa, il
modello Groq e il tono lessicale di GDELT. Su 188 notizie distinte concordano
sul verso il 36% delle volte. Poi sono stati confrontati due prompt diversi, e
divergono anche loro. Tutte e due le volte la risposta e' stata "non sono
d'accordo e non so chi ha ragione".

Nessun altro confronto automatico lo risolvera': girano in tondo. Serve un
arbitro fuori dal sistema, e l'unico disponibile e' una persona.

COSA SBLOCCA

  1. quale prompt adottare, quello in produzione o quello bilanciato
  2. se FinBERT valga la pena come terzo valutatore
  3. cosa rispondere sul labelling, con un numero invece che con "non ce l'ho"

COME E' FATTO IL CAMPIONE

Non a caso puro. Cinquanta titoli presi a caso su un archivio dove la meta'
delle notizie e' neutra darebbero venticinque "0" e pochissimo altro: si
misurerebbe soprattutto la noia. Il campione e' stratificato:

  20  su cui i due valutatori LITIGANO di piu' (sono i casi che decidono)
  20  presi a caso fra tutti gli altri (servono a non misurare solo gli estremi)
  10  su cui i due sono gia' d'accordo (servono a vedere se l'accordo e' giusto
      o se sbagliano insieme, che e' il modo in cui questa misura puo' mentire)

L'ordine e' mescolato e i punteggi delle macchine NON si vedono: sapere cosa ha
detto il modello prima di rispondere e' il modo piu' rapido di fargli dire
quello che voleva sentirsi dire.

    python backend/etichetta.py            # prepara e comincia
    python backend/etichetta.py --riprendi # continua dove avevi lasciato
    python backend/etichetta.py --rapporto # chi ti somiglia di piu'
"""
import argparse
import json
import logging
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger("etichetta")

ARCHIVIO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "etichette.json")

QUANTI_LITIGIOSI = 20
QUANTI_A_CASO = 20
QUANTI_CONCORDI = 10

# Titoli tenuti da parte per rimpiazzare quelli che chi etichetta non sa
# leggere. Meta' dell'archivio arriva dal feed tradotto di GDELT, che restituisce
# il titolo nella lingua del giornale: turco, ungherese, russo, greco. Chiedere
# un giudizio su "Bitcoin'de haftalik kayip yuzde 3'u asti" vorrebbe dire
# raccogliere un numero inventato, che e' peggio di nessun numero.
QUANTI_DI_RISERVA = 40

ISTRUZIONI = """
================================================================================
  COME PUNTEGGIARE
================================================================================

  Scrivi un numero da -1 a +1, poi invio.

  La domanda e' UNA sola: se avessi quel titolo in portafoglio, questa notizia
  e' una buona o una cattiva notizia per te?

     +1     splendida, cambia le carte in tavola
    +0.5    buona, un fatto concreto
     0      non dice niente sulla direzione, oppure non parla di affari
    -0.5    brutta, un fatto concreto
     -1     disastro

  Regole della casa, per restare coerente con te stesso:

    - parti da 0 e allontanati solo se il titolo ti da' un motivo
    - se sei incerto, la risposta e' vicino a 0
    - oltre 0.5 serve un fatto materiale scritto NEL titolo
    - non immaginare quello che non c'e' scritto
    - un titolo che e' una domanda ("minaccia o opportunita'?") vale 0
    - cronaca non finanziaria (spettacolo, sport, vicende personali) vale 0

  Comandi:
    [invio]  salta questo titolo
    x        non lo so leggere (lingua che non conosci) -> te ne do un altro
    s        indietro di uno
    q        salva ed esci

================================================================================
"""


def _campione(righe: list[tuple], seme: int = 11) -> list[tuple]:
    """
    Stratificato: i litigiosi, un po' a caso, e qualche concorde.

    Vedi la nota in cima al file. Il seme e' fisso cosi' il campione e'
    ricostruibile: se un domani si rifa' la misura con altri prompt, si vuole
    che siano gli STESSI titoli.
    """
    con_due = [r for r in righe if r[3] is not None]
    if not con_due:
        return []

    per_scarto = sorted(con_due, key=lambda r: -abs(float(r[2]) - float(r[3])))
    litigiosi = per_scarto[:QUANTI_LITIGIOSI]
    concordi = per_scarto[-QUANTI_CONCORDI:]

    presi = {id(r) for r in litigiosi} | {id(r) for r in concordi}
    resto = [r for r in con_due if id(r) not in presi]

    rnd = random.Random(seme)
    a_caso = rnd.sample(resto, min(QUANTI_A_CASO, len(resto)))

    fuori = litigiosi + concordi + a_caso
    rnd.shuffle(fuori)

    # La riserva: stessa provenienza, stesso mescolamento, tenuta da parte.
    presi.update(id(r) for r in a_caso)
    avanzo = [r for r in con_due if id(r) not in presi]
    riserva = rnd.sample(avanzo, min(QUANTI_DI_RISERVA, len(avanzo)))
    return fuori + riserva


def prepara() -> list[dict]:
    """Sceglie i titoli e li salva, senza i punteggi delle macchine in vista."""
    from calibra import coppie_complete, _senza_doppioni

    righe = _senza_doppioni(coppie_complete())
    scelte = _campione(righe)
    if not scelte:
        print("\n  Nessuna notizia ha ancora due pareri automatici.")
        print("  Prima:  python backend/calibra.py --campione 300 --scrivi\n")
        return []

    attivi = QUANTI_LITIGIOSI + QUANTI_A_CASO + QUANTI_CONCORDI
    lavoro = [{"ticker": r[0], "titolo": r[1],
               "gdelt": float(r[2]), "modello": float(r[3]),
               "umano": None,
               "illeggibile": False,
               "riserva": i >= attivi}
              for i, r in enumerate(scelte)]
    with open(ARCHIVIO, "w", encoding="utf-8") as f:
        json.dump(lavoro, f, ensure_ascii=False, indent=1)
    return lavoro


def carica() -> list[dict]:
    if not os.path.exists(ARCHIVIO):
        return []
    with open(ARCHIVIO, encoding="utf-8") as f:
        return json.load(f)


def salva(lavoro: list[dict]) -> None:
    with open(ARCHIVIO, "w", encoding="utf-8") as f:
        json.dump(lavoro, f, ensure_ascii=False, indent=1)


def _promuovi_dalla_riserva(lavoro: list[dict]) -> bool:
    """
    Fa entrare un titolo di riserva al posto di uno illeggibile.

    Senza questo, ogni titolo in una lingua che non si conosce rimpicciolisce
    il campione. Meta' dell'archivio viene dal feed tradotto di GDELT, che
    restituisce il titolo nella lingua del giornale, quindi non e' un caso
    raro: e' un pezzo strutturale della raccolta.
    """
    for v in lavoro:
        if v.get("riserva") and v["umano"] is None and not v.get("illeggibile"):
            v["riserva"] = False
            return True
    return False


def _obiettivo(lavoro: list[dict]) -> int:
    """Quanti titoli sono in gioco adesso (riserva esclusa)."""
    return sum(1 for v in lavoro if not v.get("riserva"))


def sessione(lavoro: list[dict]) -> None:
    """Un titolo alla volta. I punteggi delle macchine restano nascosti."""
    print(ISTRUZIONI)
    i = 0
    while i < len(lavoro):
        v = lavoro[i]
        if v["umano"] is not None or v.get("illeggibile") or v.get("riserva"):
            i += 1
            continue

        fatti = sum(1 for x in lavoro if x["umano"] is not None)
        print(f"\n  [{fatti}/{_obiettivo(lavoro)}]  {v['ticker']}")
        print(f"  {v['titolo']}")
        try:
            risposta = input("  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if risposta == "q":
            break
        if risposta == "s":
            j = i - 1
            while j >= 0 and lavoro[j]["umano"] is None:
                j -= 1
            if j >= 0:
                lavoro[j]["umano"] = None
                i = j
            continue
        if risposta == "":
            i += 1
            continue
        if risposta == "x":
            v["illeggibile"] = True
            if not _promuovi_dalla_riserva(lavoro):
                print("  (riserva finita: il campione si restringe di uno)")
            salva(lavoro)
            i += 1
            continue

        try:
            n = float(risposta.replace(",", "."))
        except ValueError:
            print("  Non e' un numero. Da -1 a +1.")
            continue
        if not -1 <= n <= 1:
            print("  Fuori scala: da -1 a +1.")
            continue

        v["umano"] = n
        salva(lavoro)
        i += 1

    salva(lavoro)
    fatti = sum(1 for x in lavoro if x["umano"] is not None)
    saltati = sum(1 for x in lavoro if x.get("illeggibile"))
    print(f"\n  Salvato: {fatti} su {_obiettivo(lavoro)} etichettati.")
    if saltati:
        print(f"  {saltati} scartati perche' in una lingua che non leggi.")
    if fatti < _obiettivo(lavoro):
        print("  Riprendi quando vuoi:  python backend/etichetta.py --riprendi\n")
    else:
        print("  Adesso i numeri:  python backend/etichetta.py --rapporto\n")


def rapporto() -> int:
    """Chi ti somiglia di piu', e di quanto."""
    from verifica_segnale import pearson, spearman

    tutto = carica()
    lavoro = [v for v in tutto if v["umano"] is not None]
    illeggibili = sum(1 for v in tutto if v.get("illeggibile"))
    n = len(lavoro)
    print("\n" + "=" * 74)
    print("  I VALUTATORI AUTOMATICI CONTRO DI TE")
    print("=" * 74 + "\n")
    if n < 20:
        print(f"  Solo {n} titoli etichettati, ne servono almeno 20.\n")
        return 1

    umano = [v["umano"] for v in lavoro]
    macchine = {"modello Groq": [v["modello"] for v in lavoro],
                "tono GDELT": [v["gdelt"] for v in lavoro]}

    def verso(x):
        return 1 if x > 0.1 else (-1 if x < -0.1 else 0)

    print(f"  titoli etichettati a mano: {n}")
    if illeggibili:
        # Va detto perche' e' una distorsione, non un dettaglio: i titoli
        # scartati sono quelli in lingue che chi etichetta non legge, e sono
        # proprio quelli su cui il modello se la cava peggio. Il numero che
        # esce da qui vale per le lingue che sai leggere, non per l'archivio.
        print(f"  scartati perche' in lingue non leggibili: {illeggibili}")
        print("  ATTENZIONE: il risultato vale per le lingue che leggi. Quelle")
        print("  scartate sono probabilmente le peggiori per il modello.")
    print()
    print(f"  {'':<16}{'Pearson':>9}{'ranghi':>9}{'stesso verso':>14}"
          f"{'scarto medio':>14}")
    for nome, v in macchine.items():
        r = pearson(umano, v)
        rs = spearman(umano, v)
        acc = 100 * sum(1 for a, b in zip(umano, v) if verso(a) == verso(b)) / n
        mae = sum(abs(a - b) for a, b in zip(umano, v)) / n
        print(f"  {nome:<16}{r:>+9.3f}{rs:>+9.3f}{acc:>13.0f}%{mae:>14.3f}")

    print(f"\n  {'la tua media':<16}{sum(umano) / n:>+9.3f}")
    for nome, v in macchine.items():
        print(f"  {'media ' + nome:<16}{sum(v) / n:>+9.3f}")

    print("\n" + "=" * 74)
    print("  DOVE SI ALLONTANANO DI PIU' DA TE")
    print("=" * 74 + "\n")
    peggiori = sorted(lavoro, key=lambda v: -abs(v["umano"] - v["modello"]))[:10]
    for v in peggiori:
        print(f"  [{v['ticker']:<9}] tu {v['umano']:+.2f}  modello {v['modello']:+.2f}"
              f"  gdelt {v['gdelt']:+.2f}   {v['titolo'][:52]}")

    print("\n" + "=" * 74)
    print("  COME SI LEGGE")
    print("=" * 74)
    print("\n  Lo scarto medio e' il numero piu' onesto: quanto in media il")
    print("  valutatore si allontana da te, sulla stessa scala dei punteggi.")
    print("\n  ATTENZIONE: questa e' UNA persona, non la verita'. Misura quanto")
    print("  una macchina somiglia a te, non quanto ha ragione. Se un giorno")
    print("  etichetta anche qualcun altro gli stessi titoli, il confronto fra")
    print("  voi due dice quanto e' soggettiva la domanda, ed e' un dato che")
    print("  vale quanto tutto il resto.\n")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    except ImportError:
        pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--riprendi", action="store_true",
                    help="continua dal punto in cui avevi lasciato")
    ap.add_argument("--rapporto", action="store_true",
                    help="i numeri su quello che hai gia' etichettato")
    args = ap.parse_args()

    if args.rapporto:
        sys.exit(rapporto())

    lavoro = carica() if args.riprendi else (carica() or prepara())
    if not lavoro:
        sys.exit(1)
    sessione(lavoro)
