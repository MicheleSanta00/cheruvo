"""
backfill_gdelt.py — Ricostruisce lo storico news usando SOLO GDELT.

Perché esiste. Il 5 agosto 2026 il censimento delle licenze ha contato 33.126
notizie in archivio, di cui 32.675 (il 98,6%) provenienti da fonti che non
abbiamo diritto di usare commercialmente: Google News, i feed Yahoo, NewsAPI.
Cancellarle è necessario, ma cancellarle e basta lascerebbe il prodotto con 451
notizie: contatore in home a zero virgola, e i 90 giorni di storico promessi nel
piano PRO vuoti.

GDELT ha licenza libera anche commerciale e permette di interrogare intervalli
di date passate, non solo le ultime ore. Quindi lo storico si può ricostruire
in modo lecito PRIMA di demolire quello illecito.

Uso tipico, dal più economico al più completo:

    python backend/backfill_gdelt.py --prova
        Solo la verifica: controlla che GDELT accetti le finestre storiche.
        Una chiamata, nessuna scrittura.

    python backend/backfill_gdelt.py --giorni 90 --mercati crypto
        Novanta giorni di criptovalute. Le venti monete viaggiano su UNA
        interrogazione raggruppata, quindi costa una trentina di chiamate in
        tutto: pochi minuti. È la sezione da cui vuoi monetizzare, ed è anche
        la più economica da riempire.

    python backend/backfill_gdelt.py --giorni 90 --mercati tutti
        Anche i titoli azionari. Molto più lento: gli undici titoli USA non si
        possono raggruppare e costano una chiamata ciascuno per finestra.

Il lavoro si interrompe da solo al raggiungimento di --limite-minuti e dice
fin dove è arrivato. Rilanciarlo è sicuro: i doppioni vengono scartati in
fase di salvataggio, quindi ripassare sulle stesse date non crea righe doppie.
"""
import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gdelt_source import TERMINE_QUERY, e_crypto, fetch_gdelt, _interroga  # noqa: E402
from quick_fetch import save_news  # noqa: E402

logger = logging.getLogger("backfill")


def tickers_da_riempire(mercati: str) -> list[str]:
    """
    Quali titoli ricostruire. Solo quelli in TERMINE_QUERY: per gli altri il
    termine di ricerca andrebbe risolto da yfinance una volta per finestra,
    e su un ciclo lungo diventa il collo di bottiglia.
    """
    tutti = list(TERMINE_QUERY)
    if mercati == "crypto":
        return [t for t in tutti if e_crypto(t)]
    if mercati == "azioni":
        return [t for t in tutti if not e_crypto(t)]
    return tutti


def sonda_finestre(tentativi: int = 5, attesa: float = 60.0) -> bool:
    """
    Verifica che GDELT rispetti davvero startdatetime/enddatetime.

    Serve perché il modo in cui questo script fallirebbe altrimenti è
    subdolo: se GDELT ignorasse i due parametri risponderebbe lo stesso 200
    con articoli, ma sarebbero le notizie di OGGI, riscritte identiche per
    ogni finestra. Il log direbbe "salvate 0 nuove" trenta volte di fila e
    sembrerebbe che semplicemente non ci fosse nulla da recuperare.

    Quindi non basta guardare se torna roba: si controlla che le date degli
    articoli cadano DENTRO l'intervallo chiesto.

    Perché insiste per minuti invece di arrendersi subito. Nella prima
    versione la sonda faceva due tentativi in trenta secondi, e il 5 agosto
    2026 ha ammazzato un lavoro da un'ora perché GDELT era momentaneamente
    stizzito: il giro precedente, lanciato pochi minuti prima, aveva
    consumato la pazienza dell'indirizzo IP. La punizione di GDELT non
    finisce quando smetti di chiamare, dura ancora per un po'.

    Una sonda che decide in trenta secondi se vale la pena lavorare un'ora è
    sproporzionata: costa molto meno aspettare cinque minuti che rinunciare.
    """
    fine = datetime.now(timezone.utc) - timedelta(days=30)
    inizio = fine - timedelta(days=3)
    logger.info("Sonda: chiedo a GDELT gli articoli fra %s e %s",
                inizio.strftime("%d/%m"), fine.strftime("%d/%m"))

    articoli = []
    for n in range(tentativi):
        articoli = _interroga("Bitcoin sourcelang:english", 30, "1d",
                              finestra=(inizio, fine))
        if articoli:
            break
        if n < tentativi - 1:
            logger.warning("Sonda: GDELT non risponde (tentativo %d di %d). "
                           "Aspetto %.0f secondi e riprovo: di solito è una "
                           "strozzatura passeggera, non un guasto.",
                           n + 1, tentativi, attesa)
            time.sleep(attesa)

    if not articoli:
        logger.error("Sonda fallita: GDELT non ha risposto per %.0f minuti di "
                     "fila. L'indirizzo IP è sotto punizione, quasi sempre "
                     "perché un giro precedente ha chiamato troppo. Aspetta "
                     "una mezz'ora prima di rilanciare: non serve cambiare "
                     "niente nel codice.",
                     tentativi * attesa / 60)
        return False

    # seendate arriva come YYYYMMDDTHHMMSSZ
    dentro, fuori = 0, 0
    for a in articoli:
        sd = (a.get("seendate") or "").replace("T", "").replace("Z", "")[:8]
        if not sd:
            continue
        if inizio.strftime("%Y%m%d") <= sd <= fine.strftime("%Y%m%d"):
            dentro += 1
        else:
            fuori += 1

    logger.info("Sonda: %d articoli, %d dentro la finestra, %d fuori",
                len(articoli), dentro, fuori)
    if dentro == 0:
        logger.error("Sonda fallita: GDELT ha risposto ma NESSUN articolo cade "
                     "nell'intervallo chiesto. Sta ignorando le date: la "
                     "ricostruzione riscriverebbe le notizie di oggi trenta "
                     "volte. Mi fermo qui.")
        return False
    logger.info("Sonda superata: le finestre storiche funzionano.")
    return True


def calma_il_ritmo(pausa: float) -> None:
    """
    Rallenta di proposito le chiamate a GDELT, prima ancora di cominciare.

    Attenzione a non attribuire a questa funzione più di quello che fa. La
    prima versione di questo commento sosteneva che partire calmi rendesse il
    lavoro più veloce, e i due giri del 5 agosto 2026 hanno detto il
    contrario: il primo, partito da 5 secondi, ha superato la sonda; il
    secondo, partito da 10, l'ha fallita al primo colpo. Se la teoria fosse
    stata giusta sarebbe successo l'opposto.

    Quello che conta davvero non è il ritmo ma la MEMORIA della punizione. Il
    secondo giro è partito pochi minuti dopo il primo, dallo stesso indirizzo,
    che nel frattempo aveva consumato la pazienza di GDELT con qualche
    centinaio di chiamate. La punizione non finisce quando smetti: resta
    addosso all'indirizzo ancora per un pezzo.

    Quindi la pausa alta serve, ma per un motivo più modesto: consuma la
    pazienza più lentamente, e fa durare più a lungo la finestra di lavoro
    prima che il rubinetto si chiuda. Non la riapre. Se il rubinetto è già
    chiuso l'unica cosa che funziona è aspettare, e questo lo fa la sonda.
    """
    import gdelt_source as g
    g.PAUSA_MINIMA = pausa
    g._pausa_corrente = pausa
    # Il tetto di 20 secondi era tarato sul cron, che ha 12 minuti in tutto e
    # deve rinunciare in fretta. Qui di tempo ce n'è, quindi conviene poter
    # arretrare davvero invece di insistere contro un muro.
    g.PAUSA_MASSIMA = max(g.PAUSA_MASSIMA, pausa * 4)
    # Stessa storia per l'attesa dopo un 429: 8 secondi bastavano al cron, che
    # preferisce saltare un ticker piuttosto che perdere il giro. Qui saltare
    # significa lasciare un buco nello storico, quindi conviene aspettare.
    g.ATTESA_MASSIMA_RIPROVA = max(g.ATTESA_MASSIMA_RIPROVA, pausa * 3)
    logger.info("Ritmo: una chiamata ogni %.0fs (tetto %.0fs, attesa dopo un "
                "rifiuto fino a %.0fs)",
                pausa, g.PAUSA_MASSIMA, g.ATTESA_MASSIMA_RIPROVA)


def backfill(giorni: int, ampiezza: int, mercati: str, limite_minuti: int,
             solo: str | None = None) -> int:
    tickers = [solo.upper()] if solo else tickers_da_riempire(mercati)

    # Con UN titolo solo si rinuncia al paniere di mercato e si interroga
    # direttamente il suo nome. Le 250 posizioni di GDELT vanno tutte a lui
    # invece di essere spartite fra venti monete, e i giorni con abbastanza
    # notizie da fare una media sensata si moltiplicano. Costa lo stesso
    # numero di chiamate: una per finestra.
    da_solo = len(tickers) == 1
    logger.info("Ricostruzione: %d giorni a finestre di %d, %d titoli (%s)%s",
                giorni, ampiezza, len(tickers), mercati,
                ", interrogazione dedicata" if da_solo else "")

    avvio = time.time()
    limite = limite_minuti * 60
    adesso = datetime.now(timezone.utc)
    totale = 0
    finestre_fatte = 0
    vuote = 0            # finestre consecutive senza un solo articolo
    n_finestre = max(1, giorni // ampiezza)

    # Si parte dal passato recente e si va indietro: se il tempo finisce, quello
    # che manca è la parte più vecchia, che è anche la meno importante.
    for i in range(n_finestre):
        fine = adesso - timedelta(days=i * ampiezza)
        inizio = fine - timedelta(days=ampiezza)

        trascorso = time.time() - avvio
        if trascorso > limite:
            logger.warning("Limite di %d minuti raggiunto. Ricostruite %d "
                           "finestre su %d: lo storico arriva indietro fino al "
                           "%s. Rilancia per continuare da lì.",
                           limite_minuti, finestre_fatte, n_finestre,
                           fine.strftime("%d/%m/%Y"))
            break

        logger.info("── finestra %d/%d: %s → %s ──", i + 1, n_finestre,
                    inizio.strftime("%d/%m"), fine.strftime("%d/%m"))
        nella_finestra = 0
        trovati = 0
        for ticker in tickers:
            try:
                news = fetch_gdelt(ticker, finestra=(inizio, fine),
                                   usa_paniere=not da_solo)
                trovati += len(news)
                if news:
                    salvate = save_news(ticker, news)
                    nella_finestra += salvate
                    if salvate:
                        logger.info("   %-10s %d nuove", ticker, salvate)
            except Exception as e:
                logger.error("   %-10s errore: %s", ticker, e)

        totale += nella_finestra
        finestre_fatte += 1
        logger.info("   finestra chiusa: %d articoli, %d nuove (totale %d)",
                    trovati, nella_finestra, totale)

        # Zero NUOVE è normale: significa che quella finestra era già stata
        # ricostruita e i doppioni sono stati scartati. Zero ARTICOLI no:
        # vuol dire che GDELT ha smesso di rispondere. Se succede per tre
        # finestre di fila non ha senso continuare a bussare per un'ora: si
        # consumano minuti di Actions per riportare a casa niente.
        vuote = vuote + 1 if trovati == 0 else 0
        if vuote >= 3:
            logger.warning("Tre finestre di fila senza un solo articolo: GDELT "
                           "ha chiuso il rubinetto. Mi fermo qui invece di "
                           "consumare i minuti rimasti. Riprova fra mezz'ora, "
                           "riparte da dove serve.")
            break

    durata = (time.time() - avvio) / 60
    logger.info("─" * 55)
    logger.info("Ricostruzione finita in %.1f minuti: %d notizie nuove da "
                "GDELT, su %d finestre", durata, totale, finestre_fatte)
    return totale


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)-7s | %(message)s",
                        datefmt="%H:%M:%S")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--giorni", type=int, default=90,
                    help="quanto indietro andare (default 90)")
    ap.add_argument("--finestra", type=int, default=3,
                    help="ampiezza di ogni interrogazione in giorni (default 3). "
                         "GDELT rende al massimo 250 articoli per chiamata: "
                         "finestre larghe su Bitcoin sfondano quel tetto e "
                         "perdono pezzi.")
    ap.add_argument("--mercati", choices=("crypto", "azioni", "tutti"),
                    default="crypto", help="quali titoli (default crypto)")
    ap.add_argument("--ticker", default=None,
                    help="ricostruisci UN solo titolo (es. BTC-USD). Molto più "
                         "efficace per quel titolo: le 250 posizioni per "
                         "interrogazione vanno tutte a lui invece di essere "
                         "spartite con le altre monete.")
    ap.add_argument("--limite-minuti", type=int, default=45,
                    help="tempo massimo, poi si ferma pulito (default 45)")
    ap.add_argument("--pausa", type=float, default=10.0,
                    help="secondi fra due chiamate a GDELT (default 10). "
                         "Il fetch quotidiano usa 5, ma su centinaia di "
                         "chiamate di fila quel ritmo fa scattare il 429 e si "
                         "finisce ad aspettare di più ottenendo di meno.")
    ap.add_argument("--prova", action="store_true",
                    help="esegui solo la sonda e esci, senza scrivere niente")
    args = ap.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    except ImportError:
        pass

    calma_il_ritmo(args.pausa)

    if not sonda_finestre():
        sys.exit(1)

    if args.prova:
        logger.info("Era solo una prova: non ho scritto niente.")
        sys.exit(0)

    backfill(args.giorni, args.finestra, args.mercati, args.limite_minuti,
             args.ticker)
