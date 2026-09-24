"""
esporta_dataset.py — l'archivio, in un file che qualcun altro può verificare.

PERCHÉ ESISTE

Il 28 settembre 2026 esce un articolo che dice: il sentiment delle notizie non
anticipa il prezzo, lo insegue. È un'affermazione che va creduta o verificata,
e finora si poteva solo credere. Questo file la rende verificabile: chi vuole
rifare il conto si scarica le stesse righe e lo rifà.

COSA ESCE, E SOPRATTUTTO COSA NON ESCE

Escono SOLO le righe GDELT. Non è pigrizia, è l'unica scelta difendibile.

I termini di GDELT, letti dal testo originale il 19 settembre 2026, dicono:
"You may redistribute, rehost, republish, and mirror any of the GDELT datasets
in any form", a condizione di citare il progetto E di linkare il sito. Quindi
quelle righe si possono ridistribuire.

Le altre no, o non allo stesso modo:

- BCE ed ESMA chiedono che le MODIFICHE siano dichiarate, e calcolare un
  punteggio di sentiment è una modifica. Le loro righe portano
  `score_source='istituzionale'` proprio per questo. Impacchettarle sotto una
  citazione GDELT direbbe una cosa falsa sulla loro licenza.
- Alpha Vantage è un'autorizzazione scritta al NOSTRO uso, ottenuta dal
  supporto. Un'autorizzazione a noi non è una licenza di ridistribuzione.
- SEC EDGAR è pubblico dominio e si potrebbe, ma mescolarlo dentro un file
  che dichiara una licenza sola costringerebbe chi scarica a fidarsi invece
  che a controllare.

Un dataset con tre licenze diverse e una riga sola di attribuzione è
esattamente il tipo di scorciatoia che a luglio è costata NewsAPI, Google News
RSS e i feed Yahoo. Meglio un file più piccolo e vero.

IL PERIODO DI RACCOLTA VIENE DICHIARATO, NON NASCOSTO

C'è una data che cambia il significato dei numeri. Fino al 16 agosto 2026 il
filtro di contesto riconosceva i guadagni in cinque lingue e non aveva UNA
parola per la perdita in nessuna: misurato allora, le notizie scartate avevano
media -0,095 contro +0,084 di quelle ammesse. Il sentiment di quel periodo è
spostato verso l'alto PER COSTRUZIONE.

Togliere quelle righe in silenzio sarebbe peggio che lasciarle: chi scarica
non saprebbe che sono mancate. Quindi restano, con una colonna che dice a
quale periodo appartengono, e chi rifà il conto decide da sé. È la stessa
decisione che prende `verifica_segnale.py` con `DA_QUANDO`, esposta invece che
sepolta.
"""
from __future__ import annotations

import csv
import sys
from datetime import date

# Il giorno da cui la raccolta è stabile. Prima di questo il filtro di
# contesto aveva l'asimmetria descritta in cima al file.
FILTRO_CORRETTO = date(2026, 8, 16)

# Il giorno in cui sono cambiate le regole di raccolta. Fra questo e
# FILTRO_CORRETTO i dati esistono ma sono spostati verso l'alto.
REGOLE_CAMBIATE = date(2026, 8, 7)

COLONNE = ("ticker", "data_pubblicazione", "fonte", "lingua", "titolo",
           "url", "sentiment", "origine_punteggio", "periodo_raccolta")

CITAZIONE = ("Data from The GDELT Project (https://www.gdeltproject.org/). "
             "Sentiment scores computed by Cheruvo (https://cheruvo.com).")


def periodo(giorno: date) -> str:
    """A quale regime di raccolta appartiene una riga."""
    if giorno >= FILTRO_CORRETTO:
        return "stabile"
    if giorno >= REGOLE_CAMBIATE:
        return "filtro-asimmetrico"
    return "pre-riforma"


def righe(limite: int | None = None):
    """
    Legge l'archivio. Solo GDELT, solo righe con un punteggio e un titolo.

    L'ordinamento è per data e poi per ticker: un file ordinato in modo
    stabile produce lo stesso diff a ogni esportazione, quindi chi lo
    riscarica vede cosa è cambiato invece di un file tutto nuovo.
    """
    from database import get_pool

    sql = """
        SELECT ticker, published_date, source, lingua, title, url,
               sentiment, score_source
        FROM news
        WHERE source LIKE 'GDELT%%'
          AND sentiment IS NOT NULL
          AND title IS NOT NULL
          AND btrim(title) <> ''
          AND published_date IS NOT NULL
        ORDER BY published_date, ticker, title
    """
    if limite:
        sql += f" LIMIT {int(limite)}"

    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        for r in cur.fetchall():
            giorno = r[1].date() if hasattr(r[1], "date") else r[1]
            yield {
                "ticker": r[0],
                "data_pubblicazione": r[1].isoformat() if r[1] else "",
                "fonte": r[2] or "",
                "lingua": r[3] or "",
                "titolo": r[4],
                "url": r[5] or "",
                "sentiment": f"{r[6]:.4f}",
                "origine_punteggio": r[7] or "",
                "periodo_raccolta": periodo(giorno),
            }
        cur.close()
    finally:
        pool.putconn(conn)


def esporta(percorso: str, limite: int | None = None) -> dict:
    """Scrive il CSV e restituisce il riepilogo, che serve alla scheda."""
    conti: dict[str, int] = {}
    per_ticker: dict[str, int] = {}
    prima = ultima = None
    totale = 0

    with open(percorso, "w", encoding="utf-8", newline="") as f:
        scrittore = csv.DictWriter(f, fieldnames=COLONNE)
        scrittore.writeheader()
        for riga in righe(limite):
            scrittore.writerow(riga)
            totale += 1
            conti[riga["periodo_raccolta"]] = \
                conti.get(riga["periodo_raccolta"], 0) + 1
            per_ticker[riga["ticker"]] = per_ticker.get(riga["ticker"], 0) + 1
            g = riga["data_pubblicazione"][:10]
            prima = g if prima is None else min(prima, g)
            ultima = g if ultima is None else max(ultima, g)

    return {
        "righe": totale,
        "periodi": conti,
        "ticker": len(per_ticker),
        "per_ticker": per_ticker,
        "dal": prima,
        "al": ultima,
    }


def main(percorso: str, limite: int | None = None) -> int:
    r = esporta(percorso, limite)

    print("=" * 70)
    print("  ESPORTAZIONE DATASET")
    print("=" * 70)
    print()
    print(f"  File            {percorso}")
    print(f"  Righe           {r['righe']:,}")
    print(f"  Titoli          {r['ticker']}")
    print(f"  Periodo         {r['dal']} → {r['al']}")
    print()
    print("  Per regime di raccolta:")
    for nome in ("pre-riforma", "filtro-asimmetrico", "stabile"):
        q = r["periodi"].get(nome, 0)
        if q:
            print(f"    {nome:<22} {q:>8,}")
    print()

    if r["per_ticker"]:
        print("  I dieci titoli più coperti:")
        for tk, q in sorted(r["per_ticker"].items(),
                            key=lambda kv: -kv[1])[:10]:
            print(f"    {tk:<12} {q:>8,}")
        print()

    # I titoli sottili vanno NOMINATI, non contati.
    #
    # La prima versione stampava "17 titoli hanno meno di 100 righe" e basta.
    # È un avviso che non si può usare: chi legge la scheda vuole sapere SE il
    # titolo che gli interessa è fra quelli, e un numero non glielo dice. Un
    # avviso che non si può usare è arredamento, e l'arredamento sulle
    # avvertenze è peggio di niente, perché fa sembrare che siano state date.
    magri = sorted(((q, tk) for tk, q in r["per_ticker"].items() if q < 100))
    if magri:
        print(f"  {len(magri)} titoli sotto le 100 righe, da nominare nella")
        print("  scheda. Su questi una media giornaliera è un aneddoto:")
        for q, tk in magri:
            print(f"    {tk:<12} {q:>6,}")
        print()

    print(f"  Attribuzione obbligatoria da mettere nella scheda:")
    print(f"    {CITAZIONE}")
    print()
    return 0


if __name__ == "__main__":
    import argparse
    import os

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 ".env"))
    except ImportError:
        pass

    ap = argparse.ArgumentParser(
        description="Esporta le righe GDELT dell'archivio in un CSV")
    ap.add_argument("--out", default="cheruvo_sentiment.csv")
    ap.add_argument("--limite", type=int, default=None,
                    help="solo per provare, esporta le prime N righe")
    args = ap.parse_args()
    sys.exit(main(args.out, args.limite))
