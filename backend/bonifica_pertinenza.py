"""
bonifica_pertinenza.py — Quante righe in archivio non parlano del loro titolo.

PERCHE' ESISTE

Fino al 18 agosto 2026 il percorso dell'API (`gdelt_source._e_pertinente`) non
aveva ne' il confronto che rispetta le maiuscole ne' il contesto finanziario
obbligatorio: quelle due difese stavano solo nel percorso dei file grezzi. Da
li' passano `quick_fetch` (update_news, quattro volte al giorno, e il bottone
di scarico) e `backfill_gdelt`, che il 16 agosto ha ricostruito una settimana
di storico.

Risultato misurato quel giorno: NEAR-USD aveva 43 notizie in 48 ore, piu' di
Ethereum, e nessuna parlava della moneta. Erano incendi, incidenti stradali e
basi di droni.

Il filtro adesso e' corretto, ma le righe gia' scritte restano dentro le medie
e dentro la classifica. Questo programma le CONTA. Cancella solo se glielo si
chiede esplicitamente, perche' un conto sbagliato che cancella e' peggio del
problema che risolve.

    python backend/bonifica_pertinenza.py                # conta e basta
    python backend/bonifica_pertinenza.py --ticker NEAR-USD
    python backend/bonifica_pertinenza.py --elimina      # cancella davvero

COSA NON GIUDICA

I titoli fuori da TERMINE_QUERY, cioe' quelli scaricati a richiesta da chi ha
scritto un simbolo a mano (ADIL, BB il 17 agosto): per loro non esiste un
termine di ricerca noto, quindi non si puo' dire se la riga sia pertinente e
non si tocca. Meglio lasciare dentro qualcosa di dubbio che cancellare a caso.
"""
import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger("bonifica")

# Quanti titoli scartati mostrare per ticker.
#
# Tre bastano quando il verdetto e' ovvio: su NEAR-USD ne bastava uno. Non
# bastano per decidere su META, dove il 18 agosto 2026 fra i tre esempi ce
# n'era uno giusto ("Apple Vision Pro vs Meta Ray-Bans") e uno sbagliatissimo
# ("US states seek $200 billion penalty in blockbuster Meta lawsuit"). Con tre
# righe si cancellano 190 notizie senza sapere quante fossero vere.
ESEMPI = 3


def _righe(ticker: str | None) -> list[tuple]:
    from database import get_pool
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        if ticker:
            cur.execute("SELECT id, ticker, title FROM news WHERE ticker = %s",
                        (ticker,))
        else:
            cur.execute("SELECT id, ticker, title FROM news")
        righe = cur.fetchall()
        cur.close()
    finally:
        pool.putconn(conn)
    return righe


def esamina(righe: list[tuple], esempi: int = ESEMPI) -> dict:
    """
    Per ogni ticker: quante righe ci sono, quante non reggono, e tre esempi.

    Non tocca niente e non chiede niente alla rete.
    """
    from gdelt_source import TERMINE_QUERY, _e_pertinente, _parole_chiave

    per_ticker: dict[str, dict] = {}
    _chiavi: dict[str, list[str]] = {}

    for id_, tk, titolo in righe:
        termine = TERMINE_QUERY.get(tk)
        if not termine:
            continue                      # non giudicabile: vedi il docstring
        if tk not in _chiavi:
            _chiavi[tk] = _parole_chiave(tk, termine)

        v = per_ticker.setdefault(tk, {"totale": 0, "da_togliere": [],
                                       "esempi": []})
        v["totale"] += 1
        if not _e_pertinente(titolo or "", _chiavi[tk], tk, termine):
            v["da_togliere"].append(id_)
            if len(v["esempi"]) < esempi:
                v["esempi"].append(titolo)
    return per_ticker


def _elimina(ids: list[int]) -> int:
    from database import get_pool
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        # A blocchi: un IN con decine di migliaia di elementi non e' una
        # query, e' un modo di far scadere la connessione.
        tolte = 0
        for i in range(0, len(ids), 500):
            blocco = ids[i:i + 500]
            cur.execute("DELETE FROM news WHERE id = ANY(%s)", (blocco,))
            tolte += cur.rowcount
        conn.commit()
        cur.close()
    finally:
        pool.putconn(conn)
    return tolte


def main(ticker: str | None = None, elimina: bool = False,
         esempi: int = ESEMPI) -> int:
    righe = _righe(ticker)
    per_ticker = esamina(righe, esempi)

    print("=" * 72)
    print("  PERTINENZA DELL'ARCHIVIO")
    print("=" * 72)

    if not per_ticker:
        print("\n  Nessuna riga giudicabile.")
        return 0

    ordinati = sorted(per_ticker.items(),
                      key=lambda kv: -len(kv[1]["da_togliere"]))

    print(f"\n  {'titolo':<12}{'righe':>8}{'da togliere':>14}{'quota':>9}")
    print("  " + "-" * 43)
    tutti_gli_id: list[int] = []
    for tk, v in ordinati:
        n = len(v["da_togliere"])
        tutti_gli_id.extend(v["da_togliere"])
        if not n:
            continue
        print(f"  {tk:<12}{v['totale']:>8}{n:>14}{n / v['totale']:>8.0%}")

    print(f"\n  Righe giudicate: {sum(v['totale'] for v in per_ticker.values())}")
    print(f"  Righe che non reggono il filtro: {len(tutti_gli_id)}")
    non_giudicate = len(righe) - sum(v["totale"] for v in per_ticker.values())
    if non_giudicate:
        print(f"  Righe non giudicabili (simbolo fuori elenco): {non_giudicate}")

    print("\n  Esempi, dai titoli piu' colpiti:")
    for tk, v in ordinati[:5 if not ticker else len(ordinati)]:
        if not v["esempi"]:
            continue
        print(f"\n    {tk}")
        for t in v["esempi"]:
            print(f"      {(t or '')[:66]}")

    if not elimina:
        print("\n  Non e' stata cancellata nessuna riga.")
        print("  Guarda gli esempi qui sopra: se sono davvero fuori tema,")
        print("  rilancia con --elimina.")
        return 0

    if not tutti_gli_id:
        print("\n  Niente da cancellare.")
        return 0

    tolte = _elimina(tutti_gli_id)
    print(f"\n  Cancellate {tolte} righe.")
    print("  Le medie e la classifica si aggiornano al prossimo giro di cache.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    except ImportError:
        pass

    ap = argparse.ArgumentParser(
        description="Conta le righe che non parlano del titolo a cui sono attribuite")
    ap.add_argument("--ticker", help="guarda un titolo solo")
    ap.add_argument("--elimina", action="store_true",
                    help="cancella davvero (senza, conta e basta)")
    ap.add_argument("--esempi", type=int, default=ESEMPI,
                    help="quanti titoli scartati mostrare per ticker "
                         f"(default {ESEMPI}; su un ticker solo alzalo a 30)")
    args = ap.parse_args()
    sys.exit(main(args.ticker, args.elimina, args.esempi))
