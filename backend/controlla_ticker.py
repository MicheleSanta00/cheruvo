"""
controlla_ticker.py — Ogni simbolo seguito esiste davvero?

PERCHÉ

L'11 agosto 2026 un utente esperto ha scritto di stare attento ai pasticci di
Yahoo sulle azioni italiane. Sono andato a controllare e il pasticcio c'era, ma
non era di Yahoo: era mio. `STM.MI` non è il simbolo di STMicroelectronics su
Piazza Affari. Quello giusto è `STMMI.MI`, mentre `STM` da solo è la
quotazione di New York, un'altra cosa con un altro prezzo.

Il simbolo sbagliato stava in archivio da mesi. Non se n'era accorto nessuno
perché il sintomo era muto: chi apriva quel titolo vedeva "Dati prezzi non
disponibili" e passava oltre, e le notizie continuavano a entrare sotto un
ticker che nessun listino conosce. Sette righe, prima del 30 luglio.

Su 44 simboli seguiti quello era l'unico rotto. Ma un errore che si vede solo
aprendo il titolo giusto è un errore che si trova per caso, e trovare per caso
non è un metodo. Da qui questo script.

COSA CONTROLLA

Chiede a Yahoo un prezzo per ogni simbolo dell'elenco. Se non torna niente, il
simbolo non esiste o è scritto male: sono la stessa cosa dal punto di vista di
chi lo apre.

Non controlla che il simbolo sia quello GIUSTO, e la differenza conta. `STM`
esiste ed è valido, ma è la società a New York invece che a Milano: uno
scambio del genere passerebbe questo controllo senza un fiato. Per quello
serve un occhio umano che sappia cosa sta cercando.

    python backend/controlla_ticker.py
    python backend/controlla_ticker.py --rinomina STM.MI STMMI.MI
"""
import argparse
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger("controlla_ticker")

# Le tabelle che si portano dietro un ticker e che vanno spostate insieme,
# altrimenti la watchlist di qualcuno resta appesa a un simbolo che non esiste.
TABELLE = ("news", "watchlist", "earnings_calendar")

PAUSA = 0.4   # Yahoo non ama le raffiche, e qui non c'è nessuna fretta


def censisci() -> list[str]:
    """Restituisce l'elenco dei simboli a cui Yahoo non sa rispondere."""
    from gdelt_source import TERMINE_QUERY
    from prices import validate_ticker

    simboli = sorted(TERMINE_QUERY)
    morti = []

    print("\n" + "=" * 66)
    print(f"  CONTROLLO SIMBOLI — {len(simboli)} seguiti")
    print("=" * 66 + "\n")

    for tk in simboli:
        try:
            info = validate_ticker(tk) or {}
            valido = bool(info.get("valid"))
            nome = info.get("nome") or ""
        except Exception as e:
            valido, nome = False, f"errore: {e}"

        if valido:
            print(f"  ok    {tk:<12} {nome[:40]}")
        else:
            print(f"  ROTTO {tk:<12} {nome[:40]}")
            morti.append(tk)
        time.sleep(PAUSA)

    print()
    if morti:
        print(f"  {len(morti)} simboli su {len(simboli)} non esistono: {', '.join(morti)}")
        print("  Trova quello giusto e spostaci le righe:")
        print(f"    python backend/controlla_ticker.py --rinomina {morti[0]} NUOVO.MI\n")
    else:
        print(f"  Tutti e {len(simboli)} rispondono.\n")
    return morti


def rinomina(vecchio: str, nuovo: str, davvero: bool = False) -> int:
    """
    Sposta le righe da un simbolo all'altro.

    Prima conta e mostra, poi scrive solo se glielo si chiede: è la stessa
    cautela di ripara_titoli.py, e nasce dallo stesso motivo, cioè che una
    UPDATE senza WHERE giusto non si annulla.
    """
    from database import get_pool

    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        totale = 0
        for tabella in TABELLE:
            try:
                cur.execute(f"SELECT count(*) FROM {tabella} WHERE ticker = %s", (vecchio,))
                n = cur.fetchone()[0]
            except Exception:
                # La tabella può non esistere in questo ambiente: non è un
                # errore, è una funzione che qui non c'è.
                conn.rollback()
                continue
            if n:
                print(f"  {tabella:<20} {n} righe da spostare")
                totale += n
                if davvero:
                    cur.execute(f"UPDATE {tabella} SET ticker = %s WHERE ticker = %s",
                                (nuovo, vecchio))

        if not totale:
            print(f"  Nessuna riga sotto {vecchio}: non c'è niente da spostare.")
            return 0

        if davvero:
            conn.commit()
            print(f"\n  Spostate {totale} righe da {vecchio} a {nuovo}.\n")
        else:
            conn.rollback()
            print(f"\n  {totale} righe verrebbero spostate da {vecchio} a {nuovo}.")
            print("  Niente è stato scritto. Per scrivere davvero aggiungi --scrivi\n")
        return totale
    finally:
        pool.putconn(conn)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    except ImportError:
        pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rinomina", nargs=2, metavar=("VECCHIO", "NUOVO"),
                    help="sposta le righe da un simbolo all'altro")
    ap.add_argument("--scrivi", action="store_true",
                    help="con --rinomina, scrive davvero invece di mostrare")
    args = ap.parse_args()

    if args.rinomina:
        rinomina(args.rinomina[0], args.rinomina[1], args.scrivi)
    else:
        sys.exit(1 if censisci() else 0)
