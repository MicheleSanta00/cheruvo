"""
calibra.py — I due valutatori messi a confronto sullo stesso articolo.

LA DOMANDA A CUI RISPONDE

L'11 agosto 2026 un utente su Reddit ha chiesto come vengono etichettate le
notizie. La risposta onesta era: non vengono etichettate. Non c'e' nessun
insieme annotato da un umano contro cui dire se un punteggio e' giusto, quindi
l'unica cosa misurabile e' se il punteggio serve a qualcosa, non se e' corretto.

Quella risposta e' vera ma incompleta, perche' in casa ci sono gia' DUE
valutatori indipendenti:

  Llama 3.3 70B     legge il TITOLO, restituisce da -1 a +1
  tono GDELT        calcolato da GDELT sul TESTO INTEGRALE, diviso 10

Sono costruiti in modo completamente diverso, guardano quantita' di testo
diverse e non si parlano. Il problema e' che non valutano mai lo stesso
articolo: le righe dei file grezzi tengono il tono GDELT, e sentiment_groq le
esclude apposta (`NOT IN ('llm2','av','gdelt')`), mentre le righe dell'API
prendono solo Llama. Zero sovrapposizione, quindi zero calibrazione possibile.

Questo script li fa sovrapporre di proposito su un campione.

COSA SCRIVE E COSA NON SCRIVE

Il secondo punteggio va in una colonna sua, `sentiment_2`. La colonna
`sentiment`, quella che l'app mostra, NON viene toccata: qui si misura, non si
corregge. Se un domani si decide che uno dei due e' meglio dell'altro, quella
sara' un'altra decisione, presa con questi numeri in mano.

COSA NON PUO' DIRE

L'accordo fra due valutatori non e' accuratezza. Se sbagliano tutti e due allo
stesso modo, l'accordo e' alto e la misura e' sbagliata lo stesso. Quello che
si ottiene e' piu' modesto e comunque utile: di quanto uno e' sistematicamente
piu' estremo dell'altro, e QUALI articoli li fanno litigare. Quei venti titoli,
letti a mano, valgono piu' di qualunque media.

    python backend/calibra.py                    # cosa farebbe
    python backend/calibra.py --campione 300 --scrivi
    python backend/calibra.py --rapporto         # i numeri, su cio' che c'e'
"""
import argparse
import logging
import os
import sys
from math import atanh, sqrt, tanh

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger("calibra")

LOTTO = 20          # come sentiment_groq: batch piccoli, meno rischi di JSON rotto
MIN_PER_RAPPORTO = 30


def prepara_colonne() -> None:
    """
    Le colonne dei pareri aggiuntivi. Additive: `sentiment` non si tocca.

      sentiment_2   Llama con il prompt di produzione
      sentiment_3   Llama con il prompt bilanciato, quello in prova
    """
    from database import get_pool
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        for col, tipo in (("sentiment_2", "REAL"), ("score_source_2", "TEXT"),
                          ("sentiment_3", "REAL"), ("score_source_3", "TEXT")):
            cur.execute(f"ALTER TABLE news ADD COLUMN IF NOT EXISTS {col} {tipo}")
        conn.commit()
    finally:
        pool.putconn(conn)


def da_rivalutare(quanti: int) -> list[tuple]:
    """
    Le righe che hanno già il primo parere di Llama e non ancora il secondo.

    Sono le STESSE righe del giro precedente, di proposito: confrontare due
    prompt su campioni diversi non direbbe niente, perché la differenza fra i
    due campioni si mescolerebbe alla differenza fra i due prompt.
    """
    from database import get_pool
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, ticker, title, sentiment
                 FROM news
                WHERE sentiment_2 IS NOT NULL AND sentiment_3 IS NULL
                ORDER BY published_date DESC
                LIMIT %s""", (quanti,))
        return cur.fetchall()
    finally:
        pool.putconn(conn)


def da_valutare(quanti: int) -> list[tuple]:
    """Righe che hanno il tono GDELT e non hanno ancora il secondo parere."""
    from database import get_pool
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, ticker, title, sentiment
                 FROM news
                WHERE score_source = 'gdelt'
                  AND sentiment_2 IS NULL
                  AND title IS NOT NULL AND length(trim(title)) > 10
                ORDER BY published_date DESC
                LIMIT %s""", (quanti,))
        return cur.fetchall()
    finally:
        pool.putconn(conn)


def valuta(righe: list[tuple], scrivi: bool = False,
           bilanciato: bool = False) -> int:
    """
    Fa punteggiare da Llama le righe passate. Restituisce quante ne ha scritte.

    Con `bilanciato=True` usa il prompt in prova e scrive in `sentiment_3`,
    così i due prompt restano confrontabili sulle stesse identiche righe.
    """
    from sentiment_groq import score_batch, PROMPT_BILANCIATO
    from database import get_pool

    colonna = "sentiment_3" if bilanciato else "sentiment_2"
    fonte = "score_source_3" if bilanciato else "score_source_2"
    etichetta = "llm2-bilanciato" if bilanciato else "llm2"
    prompt = PROMPT_BILANCIATO if bilanciato else None

    fatti = 0
    for i in range(0, len(righe), LOTTO):
        lotto = righe[i:i + LOTTO]
        punteggi = score_batch([{"title": r[2], "summary": ""} for r in lotto],
                               prompt=prompt)
        if punteggi is None:
            # Groq indisponibile: si smette, non si scrive niente di finto.
            logger.warning("Groq non risponde: mi fermo a %d righe.", fatti)
            break

        coppie = [(p, r[0]) for r, p in zip(lotto, punteggi) if p is not None]
        if not coppie:
            continue
        fatti += len(coppie)
        if not scrivi:
            continue

        pool = get_pool()
        conn = pool.getconn()
        try:
            cur = conn.cursor()
            cur.executemany(
                f"UPDATE news SET {colonna} = %s, {fonte} = '{etichetta}' "
                "WHERE id = %s", coppie)
            conn.commit()
        finally:
            pool.putconn(conn)
    return fatti


def coppie_complete() -> list[tuple]:
    """Le righe che hanno tutti e due i pareri, più il terzo se c'è."""
    from database import get_pool
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT ticker, title, sentiment, sentiment_2, sentiment_3
                 FROM news
                WHERE score_source = 'gdelt' AND sentiment_2 IS NOT NULL""")
        return cur.fetchall()
    finally:
        pool.putconn(conn)


def _chiave_titolo(t: str) -> str:
    """
    Titolo ridotto all'osso, per riconoscere la stessa notizia ripresa altrove.

    Minuscole, via la punteggiatura, spazi normalizzati. Non riconosce le
    riscritture ("Intel punta a una vendita da 15 miliardi" resta diversa da
    "Intel targets $15 billion stock sale"), quindi il conteggio che ne esce e'
    un MINIMO: i doppioni veri sono almeno quelli.
    """
    import re as _re
    t = _re.sub(r"[^\w\s]", " ", (t or "").lower())
    return _re.sub(r"\s+", " ", t).strip()[:90]


def _senza_doppioni(righe: list[tuple]) -> list[tuple]:
    """Una riga per notizia, tenendo la prima incontrata."""
    viste, fuori = set(), []
    for r in righe:
        k = _chiave_titolo(r[1])
        if k and k not in viste:
            viste.add(k)
            fuori.append(r)
    return fuori


def censimento_doppioni(righe: list[tuple]) -> None:
    """
    Quante delle righe sono la stessa notizia ripresa da testate diverse.

    PERCHE' CONTA, E NON SOLO QUI

    L'11 agosto 2026, guardando i disaccordi fra i due prompt, dodici casi su
    dodici erano lo stesso articolo: "Intel targets $15 billion stock sale
    after rally", ripreso nove volte. Nella lista precedente la banca centrale
    russa compariva nove volte.

    `save_news` scarta i doppioni per (titolo, testata), quindi la stessa
    notizia ripresa da venti giornali entra venti volte. E' voluto, perche' per
    l'attenzione venti riprese sono un segnale vero.

    Ma la MEDIA giornaliera del sentiment le conta come venti giudizi
    indipendenti, e non lo sono: e' un giudizio solo, moltiplicato da quanto la
    notizia e' stata sindacata. Una giornata puo' finire colorata da quale
    lancio d'agenzia e' stato ripreso di piu'.
    """
    n = len(righe)
    unici = len(_senza_doppioni(righe))
    if not n:
        return
    print(f"\n  righe: {n}, notizie distinte: {unici} "
          f"({100 * (n - unici) / n:.0f}% sono riprese)")

    from collections import Counter
    conta = Counter(_chiave_titolo(r[1]) for r in righe)
    peggiori = [(k, c) for k, c in conta.most_common(5) if c > 1]
    for k, c in peggiori:
        print(f"    {c:>3} volte   {k[:62]}")


def _confronto_prompt(righe: list[tuple]) -> None:
    """
    I due prompt sulle stesse righe.

    Il bersaglio non è l'accordo con GDELT, che si è appena scoperto essere il
    valutatore peggiore dei due: nove dei venti disaccordi peggiori erano la
    stessa notizia sulla banca centrale russa che ammette Bitcoin in borsa,
    palesemente positiva, con GDELT a -0.29 e Llama a +0.60.

    Il bersaglio è la media. Su trecento titoli finanziari presi a caso, la
    media di un valutatore onesto deve stare vicino allo zero: dire +0.25
    significa affermare che le notizie sono sistematicamente buone. Se il
    prompt bilanciato avvicina la media allo zero SENZA appiattire anche la
    dispersione, allora sta correggendo lo spostamento invece di spegnere il
    segnale, ed è la differenza che conta.
    """
    con_tre = [r for r in righe if r[4] is not None]
    if con_tre:
        censimento_doppioni(con_tre)
        # Da qui in poi si ragiona su UNA riga per notizia. Con le riprese
        # dentro, un solo lancio d'agenzia ripetuto nove volte pesa nove volte
        # su medie e correlazioni, e il confronto misura la sindacazione invece
        # dei due prompt.
        con_tre = _senza_doppioni(con_tre)
        print(f"  il confronto qui sotto gira su {len(con_tre)} notizie distinte\n")
    if not con_tre:
        print("\n  Il prompt bilanciato non è ancora stato provato su queste righe.")
        print("    python backend/calibra.py --rivaluta --scrivi\n")
        return

    n = len(con_tre)
    vecchio = [float(r[3]) for r in con_tre]
    nuovo = [float(r[4]) for r in con_tre]

    def riassunto(v):
        m = sum(v) / len(v)
        dev = (sum((x - m) ** 2 for x in v) / (len(v) - 1)) ** 0.5 if len(v) > 1 else 0.0
        neutri = sum(1 for x in v if abs(x) <= 0.1)
        return m, sum(abs(x) for x in v) / len(v), dev, 100 * neutri / len(v)

    m_v, a_v, d_v, z_v = riassunto(vecchio)
    m_n, a_n, d_n, z_n = riassunto(nuovo)
    tono = [float(r[2]) for r in con_tre]

    print("\n" + "=" * 74)
    print(f"  I DUE PROMPT SULLE STESSE {n} RIGHE")
    print("=" * 74 + "\n")
    print(f"  {'':<26}{'produzione':>13}{'bilanciato':>13}")
    print(f"  {'media':<26}{m_v:>+13.3f}{m_n:>+13.3f}   <- deve avvicinarsi a 0")
    print(f"  {'media assoluta':<26}{a_v:>13.3f}{a_n:>13.3f}")
    print(f"  {'deviazione standard':<26}{d_v:>13.3f}{d_n:>13.3f}")
    print(f"  {'quota fra -0.1 e +0.1':<26}{z_v:>12.0f}%{z_n:>12.0f}%")

    # La dispersione che cala NON basta a condannare il prompt nuovo, e non
    # basta ad assolverlo. Un prompt che dice le stesse cose su una scala piu'
    # stretta non ha perso niente: l'ordine degli articoli e' identico e a
    # cambiare e' solo il righello. Un prompt che ha smesso di distinguere,
    # invece, rimescola l'ordine.
    #
    # La differenza si vede SOLO nella correlazione dei ranghi fra i due, ed e'
    # per questo che la prima versione di questo confronto era mal fatta:
    # decideva con una soglia sulla deviazione standard scelta a occhio, e il
    # verdetto e' passato per tre millesimi.
    from verifica_segnale import spearman
    ranghi = spearman(vecchio, nuovo)

    def verso(v):
        return 1 if v > 0.1 else (-1 if v < -0.1 else 0)
    acc_v = 100 * sum(1 for a, b in zip(tono, vecchio) if verso(a) == verso(b)) / n
    acc_n = 100 * sum(1 for a, b in zip(tono, nuovo) if verso(a) == verso(b)) / n

    print(f"\n  ordine degli articoli conservato (Spearman)   {ranghi:+.3f}")
    print(f"  {'accordo sul verso col tono GDELT':<45}{acc_v:>5.0f}%  ->{acc_n:>5.0f}%")

    print()
    if abs(m_n) >= abs(m_v):
        print(f"  La media non si è avvicinata allo zero ({m_v:+.3f} -> {m_n:+.3f}).")
        print("  Il prompt nuovo non risolve il problema per cui era stato scritto.")
    elif ranghi >= 0.7:
        print(f"  Lo spostamento è sparito ({m_v:+.3f} -> {m_n:+.3f}) e l'ordine degli")
        print(f"  articoli è rimasto lo stesso (ranghi {ranghi:+.3f}): la scala si è")
        print("  stretta, il giudizio no. Il prompt bilanciato è migliore.")
    else:
        print(f"  Lo spostamento è sparito ({m_v:+.3f} -> {m_n:+.3f}) MA l'ordine degli")
        print(f"  articoli è cambiato (ranghi {ranghi:+.3f}): non è una ricalibrazione,")
        print("  è un giudizio diverso. Prima di adottarlo vanno letti i casi qui sotto.")
        print("\n  DOVE I DUE PROMPT SI CONTRADDICONO")
        contrari = [r for r in con_tre if verso(float(r[3])) != verso(float(r[4]))]
        for tk, titolo, _, v, nv in contrari[:12]:
            print(f"    [{tk:<9}] vecchio {float(v):+.2f}  nuovo {float(nv):+.2f}   {titolo[:52]}")
    print()


def rapporto() -> int:
    """I numeri, e i titoli su cui i due litigano di piu'."""
    from verifica_segnale import pearson, spearman

    righe = coppie_complete()
    n = len(righe)
    print("\n" + "=" * 74)
    print("  I DUE VALUTATORI SULLO STESSO ARTICOLO")
    print("=" * 74 + "\n")

    if n < MIN_PER_RAPPORTO:
        print(f"  Solo {n} articoli hanno tutti e due i pareri, ne servono "
              f"almeno {MIN_PER_RAPPORTO}.")
        print("  Falli valutare:  python backend/calibra.py --campione 300 --scrivi\n")
        return 1

    censimento_doppioni(righe)
    righe = _senza_doppioni(righe)
    n = len(righe)
    print(f"  i numeri qui sotto girano su {n} notizie distinte\n")
    if n < MIN_PER_RAPPORTO:
        print(f"  Meno di {MIN_PER_RAPPORTO} notizie distinte: troppo poco.\n")
        return 1

    gdelt = [float(r[2]) for r in righe]
    llm = [float(r[3]) for r in righe]

    r_p = pearson(gdelt, llm)
    r_s = spearman(gdelt, llm)

    # La banda al 95% sul coefficiente, con la stessa disciplina del frontend:
    # un r senza incertezza accanto e' esattamente il difetto tolto stamattina.
    se = 1 / sqrt(n - 3)
    z = atanh(max(-0.999999, min(0.999999, r_p)))
    lo, hi = tanh(z - 1.96 * se), tanh(z + 1.96 * se)

    med_g = sum(gdelt) / n
    med_l = sum(llm) / n
    est_g = sum(abs(v) for v in gdelt) / n
    est_l = sum(abs(v) for v in llm) / n

    def verso(v):
        return 1 if v > 0.1 else (-1 if v < -0.1 else 0)
    concordi = sum(1 for a, b in zip(gdelt, llm) if verso(a) == verso(b))

    print(f"  articoli valutati da entrambi     {n}")
    print(f"  correlazione (Pearson)            {r_p:+.3f}   banda {lo:+.3f} / {hi:+.3f}")
    print(f"  correlazione dei ranghi (Spearman){r_s:+.3f}")
    print(f"  concordi sul verso                {100 * concordi / n:.0f}%")
    print()
    print(f"  {'':<22}{'GDELT':>10}{'Llama':>10}")
    print(f"  {'media':<22}{med_g:>+10.3f}{med_l:>+10.3f}")
    print(f"  {'media in valore assoluto':<22}{est_g:>10.3f}{est_l:>10.3f}")
    if est_g:
        print(f"\n  Llama e' {est_l / est_g:.1f} volte piu' estremo del tono GDELT.")

    if lo <= 0 <= hi:
        print("\n  ATTENZIONE: la banda comprende lo zero. Su questi dati i due")
        print("  valutatori non sono distinguibili da due che tirano a caso.")

    print("\n" + "=" * 74)
    print("  DOVE LITIGANO DI PIU'")
    print("=" * 74)
    print("\n  Su questi almeno uno dei due sbaglia. Sono venti titoli: leggerli")
    print("  a mano dice quale, e vale piu' di tutte le medie qui sopra.\n")
    peggiori = sorted(righe, key=lambda r: -abs(float(r[2]) - float(r[3])))[:20]
    for tk, titolo, g, l, _ in peggiori:
        print(f"  [{tk:<9}] GDELT {float(g):+.2f}  Llama {float(l):+.2f}   {titolo[:60]}")
    print()

    _confronto_prompt(righe)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    except ImportError:
        pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--campione", type=int, default=300,
                    help="quante righe far valutare (default 300)")
    ap.add_argument("--scrivi", action="store_true",
                    help="scrive davvero in sentiment_2")
    ap.add_argument("--rapporto", action="store_true",
                    help="stampa i numeri su quello che c'e' gia'")
    ap.add_argument("--rivaluta", action="store_true",
                    help="ripunteggia le STESSE righe col prompt bilanciato")
    args = ap.parse_args()

    if args.rapporto:
        sys.exit(rapporto())

    prepara_colonne()
    righe = (da_rivalutare(args.campione) if args.rivaluta
             else da_valutare(args.campione))
    if not righe:
        print("\n  Nessuna riga in attesa.")
        print("  O sono gia' state fatte tutte, o la raccolta oraria non sta")
        print("  ancora producendo righe 'gdelt': controllalo prima.\n")
        sys.exit(0)

    che = ("da ripunteggiare col prompt bilanciato" if args.rivaluta
           else "con il tono GDELT da far valutare anche a Llama")
    print(f"\n  {len(righe)} righe {che}.")
    if not args.scrivi:
        coda = " --rivaluta" if args.rivaluta else ""
        print("  Niente e' stato scritto. Per farlo davvero:")
        print(f"    python backend/calibra.py --campione {args.campione}{coda} --scrivi\n")
        sys.exit(0)

    fatti = valuta(righe, scrivi=True, bilanciato=args.rivaluta)
    print(f"\n  Secondo parere scritto su {fatti} righe.")
    print("  Adesso i numeri:  python backend/calibra.py --rapporto\n")
