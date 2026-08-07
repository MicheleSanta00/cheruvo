"""
ripara_titoli.py — Decodifica le entità HTML nei titoli già in archivio.

Perché serve. GDELT consegna i caratteri non inglesi come entità numeriche, e
per mesi nessuno le ha decodificate. Un titolo tedesco è finito in archivio
come "H&#xFC;fte verschlissen", uno arabo come una fila di "&#x633;", ed è
così che l'utente li leggeva nell'app. Il difetto è stato scoperto il 7 agosto
2026 leggendo il registro di una misura, non da una segnalazione: nessuno usa
ancora il prodotto abbastanza da lamentarsi.

`gdelt_grezzo.titolo` adesso decodifica, quindi le righe NUOVE nascono
corrette. Questo script serve solo per l'arretrato.

Perché non è una semplice UPDATE. Ci sono due trappole.

La prima è la doppia decodifica. "&amp;lt;" decodificato una volta dà "&lt;",
decodificato due volte dà "<". Se questo script girasse due volte su una riga
già riparata potrebbe cambiarla ancora, quindi si tocca solo ciò che contiene
ancora un'entità e ci si ferma a una passata sola.

La seconda è che decodificare può produrre HTML vero. Un titolo che contiene
"&lt;script&gt;" diventerebbe "<script>", e quel testo finisce in una pagina.
React lo tratta come testo e non come marcatura, quindi non è un buco, ma
salvare marcatura dentro un campo che deve essere testo resta sbagliato: le
righe che dopo la decodifica contengono "<" o ">" vengono saltate e contate a
parte, così si vedono invece di passare inosservate.

    python backend/ripara_titoli.py            # censimento, non tocca niente
    python backend/ripara_titoli.py --ripara   # esegue davvero
"""
import html
import logging
import re
import sys

from database import get_pool

logger = logging.getLogger(__name__)

# Un'entità HTML: &#x1F600; oppure &#128512; oppure &amp;
ENTITA = re.compile(r"&(#[0-9]+|#[xX][0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]{1,31});")

LIMITE_ESEMPI = 12


def _da_riparare() -> list[tuple[int, str]]:
    """Le righe il cui titolo contiene ancora un'entità HTML."""
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        # Il LIKE fa la scrematura grossolana nel database, la regex di Python
        # decide davvero: "AT&T" contiene una "&" e non è un'entità.
        cur.execute("SELECT id, title FROM news WHERE title LIKE %s", ("%&%",))
        righe = cur.fetchall()
        cur.close()
    finally:
        pool.putconn(conn)
    return [(i, t) for i, t in righe if t and ENTITA.search(t)]


def _totale() -> int:
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM news")
        n = cur.fetchone()[0]
        cur.close()
    finally:
        pool.putconn(conn)
    return n


def _decodifica(t: str) -> str:
    """Una passata sola, mai due: vedi la nota sulla doppia decodifica."""
    return html.unescape(t).strip()


def ripara(coppie: list[tuple[int, str]]) -> int:
    """Scrive i titoli corretti. Restituisce quante righe ha toccato."""
    if not coppie:
        return 0
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        for id_, nuovo in coppie:
            cur.execute("UPDATE news SET title = %s WHERE id = %s",
                        (nuovo[:480], id_))
        conn.commit()
        cur.close()
    finally:
        pool.putconn(conn)
    logger.info("Titoli riparati: %d", len(coppie))
    return len(coppie)


def main(esegui: bool) -> int:
    totale = _totale()
    rotte = _da_riparare()

    da_scrivere: list[tuple[int, str]] = []
    saltate: list[tuple[int, str]] = []
    for id_, vecchio in rotte:
        nuovo = _decodifica(vecchio)
        if nuovo == vecchio:
            continue
        if "<" in nuovo or ">" in nuovo:
            saltate.append((id_, nuovo))
            continue
        da_scrivere.append((id_, nuovo))

    print(f"\nNotizie in archivio: {totale}")
    quota = len(rotte) / totale if totale else 0
    print(f"Con entità HTML nel titolo: {len(rotte)} ({quota:.1%})")
    print(f"Da riparare: {len(da_scrivere)}")
    if saltate:
        print(f"Saltate perché la decodifica produce marcatura: {len(saltate)}")

    if da_scrivere:
        print("\nEsempi:")
        for _, nuovo in da_scrivere[:LIMITE_ESEMPI]:
            vecchio = next(v for i, v in rotte if _decodifica(v) == nuovo)
            print(f"  prima: {vecchio[:66]}")
            print(f"  dopo:  {nuovo[:66]}\n")

    if saltate:
        print("Saltate (da guardare a mano):")
        for id_, nuovo in saltate[:LIMITE_ESEMPI]:
            print(f"  id {id_}: {nuovo[:66]}")
        print()

    if not esegui:
        print("Nessuna modifica fatta. Per eseguire davvero:")
        print("  python backend/ripara_titoli.py --ripara\n")
        return 0

    if not da_scrivere:
        print("Niente da riparare.\n")
        return 0

    print(f"Riparo {len(da_scrivere)} titoli...")
    print(f"Fatto: {ripara(da_scrivere)} titoli riscritti.\n")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)-7s | %(message)s",
                        datefmt="%H:%M:%S")
    sys.exit(main("--ripara" in sys.argv))
