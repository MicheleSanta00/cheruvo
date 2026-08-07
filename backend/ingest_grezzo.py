"""
ingest_grezzo.py — Raccolta news dai file GDELT pubblicati ogni 15 minuti.

Il fratello che scrive di `gdelt_grezzo.py`, che invece misura soltanto.

PERCHÉ ESISTE, coi numeri della misura del 6 agosto 2026.

L'API di GDELT concede 250 risultati per interrogazione e punisce chi chiama
spesso. Con venti monete raggruppate, a Bitcoin arrivavano circa quattro
articoli al giorno: troppo pochi perché una media giornaliera significhi
qualcosa. Dai file grezzi, nello stesso quarto d'ora, Bitcoin ne rendeva due,
cioè dell'ordine dei centonovanta al giorno.

Quel numero va preso per quello che è. Tre articoli crypto in un solo campione
danno una stima con un margine largo: il valore vero sta grosso modo fra 60 e
800 al giorno. Anche il fondo di quell'intervallo però è dieci volte quello che
abbiamo, quindi la decisione regge; è la cifra precisa che non va scritta da
nessuna parte come se fosse una misura.

TRE SCELTE CHE VALE LA PENA CONOSCERE

1. Il punteggio lo dà GDELT, non Groq.
   Il file porta il tono calcolato sul TESTO INTEGRALE dell'articolo. Noi
   calcoliamo il sentiment su titolo più 120 caratteri di sommario. Su un
   flusso da duecento articoli al giorno, passarli tutti a un modello
   costerebbe quota e tempo per ottenere un punteggio basato su MENO testo.
   Le righe raccolte qui vengono marcate `score_source='gdelt'` e Groq le
   lascia stare, come già fa con quelle di Alpha Vantage.

2. Il filtro di contesto è obbligatorio, non un abbellimento.
   Questi file contengono meteo, sport e cronaca del mondo intero. Senza
   filtro, "Avalanche kills three skiers" entrerebbe in archivio come notizia
   su AVAX. Dal 7 agosto 2026 il contesto finanziario è richiesto a TUTTI i
   titoli azionari e non più solo alle parole ambigue: nella prima giornata
   piena GOOGL e MSFT da soli valevano 816 righe su 1.541, quasi tutte
   aggiornamenti di prodotto. Le monete restano libere, perché il nome della
   moneta è già di per sé un termine di mercato.

3. Un articolo può valere per più titoli.
   Prima ci si fermava al primo che combaciava, e le azioni vengono prima
   delle monete nel dizionario: "Microsoft mette Bitcoin in tesoreria" veniva
   archiviata come notizia MSFT e Bitcoin la perdeva.

4. Si scarica all'indietro, non in avanti.
   I file più recenti valgono più dei vecchi, quindi se il tempo finisce si
   perde la coda e non la testa.

    python backend/ingest_grezzo.py --ore 6
    python backend/ingest_grezzo.py --ore 24 --limite-minuti 20
"""
import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gdelt_grezzo import (BASE, COL_DATA, COL_DOMINIO, COL_URL,  # noqa: E402
                          conta_pertinenti, leggi_gkg, lingua, titolo, tono)
from gdelt_source import TERMINE_QUERY  # noqa: E402
from quick_fetch import save_news  # noqa: E402

logger = logging.getLogger("ingest")

# Da tono GDELT a nostro sentiment.
#
# GDELT dichiara una scala da -100 a +100, ma nella pratica i valori stanno
# quasi tutti fra -10 e +10: nel campione misurato andavano da -1,98 a +3,22.
# Dividere per dieci porta quell'intervallo utile dentro il nostro -1..+1
# conservando l'ordine, che è quello che serve per fare medie e classifiche.
#
# È una CONVENZIONE, non una verità: un tono GDELT di +3 e un nostro +0,3 non
# sono la stessa cosa misurata due volte. Servono a confrontare articoli fra
# loro, non a dire quanto è positiva una notizia in assoluto.
DIVISORE_TONO = 10.0


def _tono_nostro(t: float | None) -> float:
    if t is None:
        return 0.0
    return max(-1.0, min(1.0, t / DIVISORE_TONO))


def quarti_dora_indietro(ore: int) -> list[str]:
    """
    I timestamp dei file da scaricare, dal più recente al più vecchio.

    GDELT pubblica ai minuti 00, 15, 30 e 45 di ogni ora. Si parte da un
    quarto d'ora fa e non da adesso, perché il file dell'istante corrente
    spesso non è ancora stato pubblicato e darebbe un 404.
    """
    adesso = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    adesso -= timedelta(minutes=adesso.minute % 15 + 15)
    return [(adesso - timedelta(minutes=15 * i)).strftime("%Y%m%d%H%M%S")
            for i in range(ore * 4)]


def raccogli(ore: int, limite_minuti: int, solo_inglese: bool = False) -> int:
    termini = dict(TERMINE_QUERY)
    stamp = quarti_dora_indietro(ore)
    feed = [("", "inglese")] if solo_inglese else [("", "inglese"),
                                                   ("translation.", "tradotto")]

    logger.info("Raccolgo %d quarti d'ora (%d ore) da %d feed",
                len(stamp), ore, len(feed))

    avvio = time.time()
    limite = limite_minuti * 60
    per_ticker: dict[str, list] = {}
    letti = scartati_falsi = file_ok = file_ko = articoli_distinti = 0

    for ts in stamp:
        if time.time() - avvio > limite:
            logger.warning("Limite di %d minuti raggiunto: mi fermo a %s. "
                           "I file non letti sono i più vecchi, che valgono meno.",
                           limite_minuti, ts)
            break

        for suffisso, nome_feed in feed:
            url = f"{BASE}/{ts}.{suffisso}gkg.csv.zip"
            try:
                righe = leggi_gkg(url)
            except Exception as e:
                # Un 404 è normale: non tutti i quarti d'ora hanno un file in
                # entrambi i feed, e quello tradotto viaggia con qualche minuto
                # di ritardo rispetto all'inglese.
                logger.debug("  %s (%s): %s", ts, nome_feed, str(e)[:60])
                file_ko += 1
                continue

            file_ok += 1
            letti += len(righe)
            trovati, _, _ = conta_pertinenti(righe, termini)
            ingenui, _, _ = conta_pertinenti(righe, termini, rigoroso=False)
            scartati_falsi += sum(ingenui.values()) - sum(trovati.values())

            for riga in righe:
                t = titolo(riga)
                if not t:
                    continue
                quali = _quali_ticker(t, termini)
                if not quali:
                    continue
                articoli_distinti += 1
                base = {
                    "source": f"GDELT · {riga[COL_DOMINIO] or 'n/d'}",
                    "title": t[:480],
                    "summary": "",
                    "published_date": _data(riga),
                    "url": riga[COL_URL] or "",
                    "sentiment": _tono_nostro(tono(riga)),
                    # Groq lascia stare queste righe: il loro punteggio nasce
                    # dal testo integrale, che è più di quanto veda lui.
                    "score_source": "gdelt",
                    "lingua": lingua(riga),
                }
                for tk in quali:
                    # Una copia per ticker: passare lo stesso oggetto a più
                    # chiamate di save_news significherebbe che una modifica
                    # fatta dentro la prima si ritrova nelle altre.
                    per_ticker.setdefault(tk, []).append(dict(base))

    salvate = 0
    for tk, news in sorted(per_ticker.items(), key=lambda x: -len(x[1])):
        try:
            n = save_news(tk, news)
            salvate += n
            if n:
                logger.info("  %-11s %4d nuove su %d trovate", tk, n, len(news))
        except Exception as e:
            logger.error("  %-11s errore in salvataggio: %s", tk, e)

    durata = (time.time() - avvio) / 60
    logger.info("─" * 58)
    logger.info("File letti: %d (%d non disponibili)", file_ok, file_ko)
    logger.info("Righe esaminate: %d", letti)
    logger.info("Scartati come falsi positivi: %d", scartati_falsi)
    # Due numeri e non uno: da quando un articolo può appartenere a più titoli,
    # le assegnazioni sono di più degli articoli. Confonderli farebbe sembrare
    # la copertura più ampia di quanto sia.
    logger.info("Articoli pertinenti: %d, assegnazioni: %d, salvati come nuovi: %d",
                articoli_distinti,
                sum(len(v) for v in per_ticker.values()), salvate)
    logger.info("Durata: %.1f minuti", durata)
    return salvate


def _quali_ticker(titolo_art: str, termini: dict) -> list[str]:
    """
    A quali titoli appartiene questo articolo. Possono essere più di uno.

    Usa le STESSE regole della misura, importate da gdelt_grezzo: confini di
    parola, contesto obbligatorio dove serve, maiuscole per le sigle.
    Riscriverle qui significherebbe avere due filtri che col tempo divergono,
    e scoprirlo un mese dopo guardando dati sporchi.

    Restituisce un elenco e non un valore solo perché un articolo che parla di
    Microsoft e di Bitcoin parla di tutti e due. Fermarsi al primo, come
    faceva la versione precedente, dava la precedenza a chi capitava prima nel
    dizionario: le azioni, sempre, per come è scritto TERMINE_QUERY.
    """
    from gdelt_grezzo import CONTESTO, MAIUSCOLI, serve_contesto
    import re as _re

    trovati = []
    ha_contesto = bool(CONTESTO.search(titolo_art))
    for tk, term in termini.items():
        flag = 0 if term in MAIUSCOLI else _re.IGNORECASE
        if not _re.search(r"\b" + _re.escape(term) + r"\b", titolo_art, flag):
            continue
        if serve_contesto(tk, term) and not ha_contesto:
            continue
        trovati.append(tk)
    return trovati


def _data(riga: list[str]) -> str:
    """
    La data di pubblicazione, dal campo V2.1DATE (YYYYMMDDHHMMSS).

    Se manca o è malformata si ripiega su adesso: una riga senza data
    finirebbe fuori da ogni finestra temporale e sarebbe come non averla
    raccolta, che è peggio di averla con un'ora imprecisa.
    """
    grezza = (riga[COL_DATA] or "").strip() if len(riga) > COL_DATA else ""
    try:
        d = datetime.strptime(grezza, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        return d.isoformat()
    except (ValueError, TypeError):
        return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)-7s | %(message)s",
                        datefmt="%H:%M:%S")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ore", type=int, default=6,
                    help="quante ore indietro (default 6, come il cron)")
    ap.add_argument("--limite-minuti", type=int, default=15,
                    help="tempo massimo, poi si ferma pulito")
    ap.add_argument("--solo-inglese", action="store_true",
                    help="salta il feed tradotto: dimezza il traffico")
    args = ap.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    except ImportError:
        pass

    sys.exit(0 if raccogli(args.ore, args.limite_minuti, args.solo_inglese) >= 0 else 1)
