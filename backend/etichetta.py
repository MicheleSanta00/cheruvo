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
    python backend/etichetta.py --rifai    # riscegli i titoli, tieni i giudizi
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


def _parole(titolo: str) -> set:
    """Le parole di un titolo, senza quelle che ci sono in tutti."""
    import re
    VUOTE = {"il","lo","la","i","gli","le","di","a","da","in","con","su","per",
             "the","of","to","and","in","for","on","at","as","is","are","with",
             "after","from","by","its","has","have","will","that","this","a","an",
             "e","ed","che","non","si","al","del","della","dei","delle","un","una"}
    t = re.sub(r"[^\w\s]", " ", (titolo or "").lower())
    return {p for p in t.split() if len(p) > 2 and p not in VUOTE}


_ANNO = __import__("re").compile(r"^(19|20)\d\d$")


def _cifre(titolo: str) -> set:
    """
    Le cifre citate nel titolo, esclusi gli anni.

    Una cifra in un titolo e' quasi sempre il fatto: "15 miliardi", "400.000
    veicoli", "il 3%". Due giornali che raccontano la stessa cosa la ripetono
    identica anche quando riscrivono tutto il resto, ed e' l'unica traccia che
    sopravvive alla riscrittura.

    Gli anni no: "Nvidia alza le stime 2026" e "Nvidia annuncia il riacquisto
    2026" condividono il 2026 e sono due fatti diversi. Un anno dice quando,
    non cosa.
    """
    import re
    fuori = set()
    for grezzo in re.findall(r"\d[\d.,]*", titolo or ""):
        n = grezzo.rstrip(".,").replace(".", "").replace(",", "")
        if n and not _ANNO.match(n):
            fuori.add(n.lstrip("0") or "0")
    return fuori


def _stessa_notizia(a: str, b: str, soglia: float = 0.6) -> bool:
    """
    Due titoli raccontano lo stesso fatto anche se scritti diverso?

    `_chiave_titolo` di calibra riconosce solo le copie IDENTICHE, quindi
    "Intel targets $15 billion stock sale after rally" e "Intel seeks $15
    billion as turnaround boosts shares" per lui sono due notizie. Per chi
    etichetta sono la stessa cosa vista due volte, e dopo la quinta variante
    smette di dare giudizi e comincia a copiare quello di prima.

    Ci sono due modi di accorgersene, e servono tutti e due.

    IL PRIMO, per le riscritture pigre. Se gli insiemi di parole si
    sovrappongono per piu' del 60% del piu' corto dei due, e' lo stesso fatto.
    Servono pero' anche almeno quattro parole in comune, non solo la
    proporzione: su due titoli corti bastano tre parole condivise per superare
    il 60% e finire fusi anche parlando di cose diverse. "Eni annuncia accordo
    in Libia" e "Eni annuncia accordo in Egitto" hanno quattro parole su cinque
    uguali ed e' giusto fonderli, "Eni taglia" e "Eni sale" no.

    IL SECONDO, per le riscritture vere, ed e' quello che serviva qui. I due
    titoli su Intel condividono soltanto "intel" e "billion": due parole su
    sei, il 33%, molto sotto qualunque soglia sensata. La prima versione di
    questa funzione NON li riconosceva, pur citandoli come motivo per
    esistere. Quello che condividono davvero e' la CIFRA, 15 miliardi, e la
    cifra sopravvive alla riscrittura perche' e' il fatto. Quindi: stessa cifra
    piu' almeno un'altra parola in comune (di solito il nome della societa')
    vuol dire stesso fatto.

    Non e' esatto, ma sbagliare tenendo fuori una notizia buona costa meno che
    chiedere cinque volte lo stesso giudizio: ce ne sono altre trecento in
    archivio, di pazienza di chi etichetta ce n'e' una sola.
    """
    pa, pb = _parole(a), _parole(b)
    if not pa or not pb:
        return False
    comuni = len(pa & pb)
    if comuni >= 4 and comuni / min(len(pa), len(pb)) >= soglia:
        return True

    if not comuni:
        return False
    condivise = _cifre(a) & _cifre(b)
    # Una cifra vale come impronta solo se e' GROSSA o se ha accanto la parola
    # di grandezza. Le percentuali a una o due cifre non distinguono niente:
    # "Apple sale del 3% a Wall Street" e "Tesla scende del 3% a Wall Street"
    # condividono il 3 e due parole, e sono due fatti diversi. Il 3 di "15
    # miliardi" invece e' il fatto, e "400000" da solo non lo dice nessun
    # altro.
    GRANDEZZE = {"billion", "million", "trillion", "miliardi", "milioni",
                 "miliardo", "milione", "mld", "mln"}
    return any(len(n) >= 3 for n in condivise) or bool(
        condivise and GRANDEZZE & pa & pb)


def _varia(righe: list[tuple], quante: int, max_per_ticker: int = 3) -> list[tuple]:
    """
    Prende `quante` righe evitando di ripetere lo stesso fatto e lo stesso
    titolo azionario.

    Il tetto per ticker serve perche' i casi su cui i due valutatori litigano
    di piu' tendono a essere tutti lo stesso evento: nel campione dell'11
    agosto 2026 dodici disaccordi su dodici erano l'aumento di capitale di
    Intel, in dodici riscritture diverse.
    """
    from collections import Counter
    presi, conta = [], Counter()
    for r in righe:
        if len(presi) >= quante:
            break
        if conta[r[0]] >= max_per_ticker:
            continue
        if any(_stessa_notizia(r[1], p[1]) for p in presi):
            continue
        presi.append(r)
        conta[r[0]] += 1
    return presi


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

    # Ogni gruppo passa da `_varia`: niente stesso fatto raccontato due volte,
    # e non piu' di tre righe per titolo azionario. Senza, i venti litigiosi
    # sarebbero venti versioni dell'aumento di capitale di Intel.
    litigiosi = _varia(per_scarto, QUANTI_LITIGIOSI)
    concordi = _varia(list(reversed(per_scarto)), QUANTI_CONCORDI)

    presi = {id(r) for r in litigiosi} | {id(r) for r in concordi}
    resto = [r for r in con_due if id(r) not in presi]

    rnd = random.Random(seme)
    rnd.shuffle(resto)
    a_caso = _varia(resto, QUANTI_A_CASO)

    fuori = litigiosi + concordi + a_caso
    # Anche fra i tre gruppi non deve ricomparire lo stesso fatto.
    fuori = _varia(fuori, len(fuori))
    rnd.shuffle(fuori)

    presi.update(id(r) for r in a_caso)
    avanzo = [r for r in con_due if id(r) not in presi
              and not any(_stessa_notizia(r[1], p[1]) for p in fuori)]
    riserva = _varia(avanzo, QUANTI_DI_RISERVA)
    return fuori + riserva


def _giudizi_gia_dati(lavoro: list[dict]) -> dict:
    """
    I giudizi umani gia' espressi, indicizzati per titolo normalizzato.

    Servono a poter RIFARE il campione senza buttare via il lavoro fatto. Il
    campione del 15 agosto 2026 era venuto male, 25 righe per 15 titoli
    distinti, e a quel punto la scelta era fra tenersi un campione difettoso o
    ributtare via diciannove giudizi. Nessuna delle due.

    La chiave e' quella di `calibra`, cosi' un titolo ripescato domani da
    un'altra testata con la stessa identica riga ritrova il suo giudizio.
    """
    from calibra import _chiave_titolo
    fuori = {}
    for v in lavoro:
        if v.get("umano") is not None or v.get("illeggibile"):
            fuori[_chiave_titolo(v["titolo"])] = (v.get("umano"),
                                                  bool(v.get("illeggibile")))
    return fuori


def prepara() -> list[dict]:
    """Sceglie i titoli e li salva, senza i punteggi delle macchine in vista."""
    from calibra import coppie_complete, _senza_doppioni, _chiave_titolo

    righe = _senza_doppioni(coppie_complete())
    scelte = _campione(righe)
    if not scelte:
        print("\n  Nessuna notizia ha ancora due pareri automatici.")
        print("  Prima:  python backend/calibra.py --campione 300 --scrivi\n")
        return []

    # Quello che era gia' stato deciso resta deciso. Il vecchio file viene
    # messo da parte invece che sovrascritto: se questa ricucitura sbaglia
    # qualcosa, i giudizi sono ancora li'.
    vecchi = _giudizi_gia_dati(carica())
    if vecchi:
        os.replace(ARCHIVIO, ARCHIVIO + ".precedente")

    attivi = QUANTI_LITIGIOSI + QUANTI_A_CASO + QUANTI_CONCORDI
    lavoro = []
    for i, r in enumerate(scelte):
        umano, illeggibile = vecchi.get(_chiave_titolo(r[1]), (None, False))
        lavoro.append({"ticker": r[0], "titolo": r[1],
                       "gdelt": float(r[2]), "modello": float(r[3]),
                       "umano": umano,
                       "illeggibile": illeggibile,
                       "riserva": i >= attivi})
    with open(ARCHIVIO, "w", encoding="utf-8") as f:
        json.dump(lavoro, f, ensure_ascii=False, indent=1)

    if vecchi:
        recuperati = sum(1 for v in lavoro if v["umano"] is not None)
        print(f"\n  Campione rifatto. Giudizi ripresi dal file precedente: "
              f"{recuperati} su {len(vecchi)}.")
        print(f"  Il vecchio file e' in {os.path.basename(ARCHIVIO)}.precedente\n")
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
    ap.add_argument("--rifai", action="store_true",
                    help="riscegli i titoli tenendo i giudizi gia' dati")
    ap.add_argument("--rapporto", action="store_true",
                    help="i numeri su quello che hai gia' etichettato")
    args = ap.parse_args()

    if args.rapporto:
        sys.exit(rapporto())

    # Senza --rifai il file esistente vince sempre: un campione a meta' non
    # si ributta via per sbaglio, ci sono dentro delle ore di qualcuno.
    lavoro = prepara() if args.rifai else (carica() or prepara())
    if not lavoro:
        sys.exit(1)
    sessione(lavoro)
