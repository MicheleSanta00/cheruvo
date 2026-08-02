"""
pulizia_licenze.py — Censimento (e rimozione) delle news rimaste in archivio
da fonti che oggi non abbiamo licenza di usare.

Perché serve. A luglio abbiamo staccato NewsAPI, Google News RSS e i feed
Yahoo/Sole24Ore perché nessuno dei tre permette l'uso commerciale. Abbiamo
però tolto solo i "rubinetti": le righe già salvate sono rimaste nel database
e continuano a comparire nell'app. Aprendo NVDA oggi si leggono ancora tre
titoli marcati "Google News".

Come riconosciamo il lecito. Non per elenco di ciò che è vietato (le righe
NewsAPI portano il nome della testata originale, quindi sono impossibili da
elencare) ma al contrario: si tiene solo ciò che proviene dalle fonti che
usiamo oggi, e tutto il resto è per definizione roba vecchia.

ATTENZIONE: la cancellazione è definitiva e abbassa il conteggio "notizie
totali" mostrato in home. Per questo il comportamento predefinito è il solo
CENSIMENTO: stampa cosa toglierebbe e non tocca niente.

    python backend/pulizia_licenze.py            # conta e basta
    python backend/pulizia_licenze.py --elimina  # esegue davvero
"""
import logging
import sys

from database import get_pool

logger = logging.getLogger(__name__)

# Fonti con diritto d'uso commerciale verificato. Il confronto è sul PREFISSO
# perché GDELT scrive "GDELT · nomedominio.it".
PREFISSI_LECITI = (
    "GDELT",            # licenza libera anche commerciale, redistribuzione inclusa
    "SEC EDGAR",        # atti pubblici USA, pubblico dominio
    "Alpha Vantage",    # solo se AV_ENABLED, cioè dietro autorizzazione scritta
)


def _condizione_sql() -> str:
    """WHERE che seleziona le righe NON coperte da licenza."""
    return " AND ".join(f"source NOT LIKE '{p} %' AND source <> '{p}'"
                        for p in PREFISSI_LECITI)


def censisci() -> list[tuple[str, int]]:
    """Elenco (fonte, quante righe) delle news non più utilizzabili."""
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT source, COUNT(*) AS n
            FROM news
            WHERE {_condizione_sql()}
            GROUP BY source
            ORDER BY n DESC
        """)
        righe = cur.fetchall()
        cur.close()
    finally:
        pool.putconn(conn)
    return [(r[0], r[1]) for r in righe]


def elimina() -> int:
    """Cancella le righe non coperte da licenza. Ritorna quante ne ha tolte."""
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(f"DELETE FROM news WHERE {_condizione_sql()}")
        quante = cur.rowcount
        conn.commit()
        cur.close()
    finally:
        pool.putconn(conn)
    logger.info("Pulizia licenze: %d righe rimosse", quante)
    return quante


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM news")
        totale = cur.fetchone()[0]
        cur.close()
    finally:
        pool.putconn(conn)

    voci = censisci()
    da_togliere = sum(n for _, n in voci)

    print(f"\nNotizie in archivio: {totale}")
    print(f"Senza licenza d'uso: {da_togliere} "
          f"({da_togliere / totale * 100:.1f}% del totale)\n" if totale else "")
    for fonte, n in voci[:25]:
        print(f"  {n:>7}  {fonte}")
    if len(voci) > 25:
        print(f"  ... e altre {len(voci) - 25} fonti")

    if "--elimina" not in sys.argv:
        print("\nNessuna modifica fatta. Per eseguire davvero:")
        print("  python backend/pulizia_licenze.py --elimina\n")
        sys.exit(0)

    print(f"\nRimuovo {da_togliere} righe...")
    print(f"Fatto: {elimina()} righe rimosse. "
          f"Restano {totale - da_togliere} notizie.\n")
