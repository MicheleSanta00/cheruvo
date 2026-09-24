"""
ritardo_notizie.py — quanto la stampa ha recuperato il movimento già avvenuto.

DA DOVE NASCE QUESTO FILE

Il 19 settembre 2026 `verifica_segnale.py` ha chiuso la domanda per cui
Cheruvo era nato. Su Bitcoin, 44 giorni utilizzabili e 5.285 notizie: nella
direzione diretta non passa niente a nessun orizzonte, e a sette giorni la
correlazione di rango è −0,001. Nella direzione opposta invece regge, e regge
sotto block bootstrap: il sentiment di oggi segue il movimento dei due giorni
precedenti con rho +0,605 (p peggiore 0,0074) e dei sette con rho +0,606
(p 0,0146).

Il sentiment non anticipa il prezzo. Lo insegue.

Finora quel fatto stava in home scritto come una scusa ("un termometro, non
un barometro"). Questo file prova a farne invece la cosa che il prodotto
mostra. Se la stampa insegue il prezzo, allora si può dire A CHE PUNTO è
l'inseguimento: quanto il tono di oggi è più caldo o più freddo di quello che
il movimento degli ultimi giorni farebbe aspettare.

LA TRAPPOLA, SCRITTA PRIMA DEL CODICE

Un numero del genere si legge da solo come una previsione. "Le notizie non
hanno ancora recuperato" diventa "quindi il prezzo si muoverà", che è
esattamente la promessa che questo progetto ha passato mesi a non fare.

Per questo il residuo non esce da qui verso l'interfaccia finché non è passato
dallo stesso setaccio di tutto il resto: permutazione, block bootstrap su
cinque lunghezze, p peggiore, soglia fissata prima. Se prevede è un segnale e
si può scrivere. Se non prevede è una descrizione dello stato attuale, e si
scrive lo stesso ma con parole diverse.

LA REGOLA DI ONESTÀ CHE COSTA PIÙ CARA

La retta che dice "dato questo movimento, ci si aspetta questo tono" va
stimata SOLO su giorni precedenti a quello che si sta giudicando. Stimarla su
tutti i 44 e poi misurare i residui sugli stessi 44 significa costruire il
numero con i dati su cui lo si prova, ed è il modo più comune di ottenere un
risultato che non esiste.

Il prezzo è che i primi giorni si buttano via per addestrare. Con 44 giorni in
archivio e una finestra minima di 20, restano circa 24 residui: SOTTO i 30 che
il progetto si è imposto come minimo per dire qualcosa. Quindi è previsto, e
normale, che per un po' questo file risponda "non lo so". È la risposta
giusta, non un guasto.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta

from anomalie import SIGMA_ARTICOLO, mad, mediana
from verifica_segnale import (
    BLOCCHI, MINIMO_GIORNI, MINIMO_NOTIZIE, ORIZZONTI,
    permutazione, sensibilita_blocchi, serie_prezzi, serie_sentiment,
    spearman,
)

# Su quanti giorni indietro si misura il movimento che la stampa insegue.
#
# Due, e non uno né sette. A un giorno la correlazione misurata è +0,338, a due
# sale a +0,605, a sette resta +0,606: la salita si ferma fra uno e due giorni
# e dopo non aggiunge niente. Prendere sette darebbe lo stesso legame con
# finestre che si sovrappongono di sei giorni su sette, cioè tutta
# l'autocorrelazione in più e nessuna informazione in più.
RITARDO = 2

# Quanti giorni servono per stimare la retta prima di poter giudicare il primo.
#
# Venti è un compromesso fra due errori opposti. Troppo pochi e la retta la
# decide il rumore, quindi il residuo misura la stima e non il mondo. Troppi e
# non resta niente da misurare: ogni giorno speso ad addestrare è un giorno in
# meno di risultato, e l'archivio parte dal 7 agosto 2026.
MINIMO_FIT = 20

# La soglia di significatività, fissata qui e non dopo aver guardato.
#
# Tre orizzonti sono tre occasioni di essere fortunati, quindi 0,05 diviso 3.
# È la stessa che usa verifica_segnale.py, e deve restare la stessa: cambiarla
# per questo file soltanto sarebbe scegliere la soglia dopo aver visto il dato.
SOGLIA_P = 0.05 / len(ORIZZONTI)


def retta(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """
    Minimi quadrati: restituisce (intercetta, pendenza) di ys su xs.

    Una retta è un'approssimazione, e va detto: il legame misurato è fra
    RANGHI, cioè monotono ma non per forza lineare. Su questo intervallo la
    differenza è piccola, e soprattutto è un'approssimazione che si paga da
    sola: se la retta descrive male il legame, il residuo è sporco e il test
    a valle non passa. L'errore non resta nascosto, si presenta al controllo.
    """
    n = len(xs)
    if n < 2:
        return 0.0, 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return my, 0.0
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx
    return my - b * mx, b


def rendimento_precedente(prezzi: dict[date, float], giorno: date,
                          k: int = RITARDO) -> float | None:
    """Il movimento fra la chiusura di giorno-k e quella di giorno."""
    prima = giorno - timedelta(days=k)
    p0, p1 = prezzi.get(prima), prezzi.get(giorno)
    if not p0 or p1 is None:
        return None
    return (p1 - p0) / p0


def serie_ritardo(sent: dict, prezzi: dict, k: int = RITARDO,
                  minimo_fit: int = MINIMO_FIT,
                  oggi: date | None = None) -> list[dict]:
    """
    Per ogni giorno: tono vero, tono atteso dal movimento, e la differenza.

    La retta usata per il giorno T è stimata sui giorni PRECEDENTI a T e su
    nessun altro. Cresce di un giorno alla volta, come crescerebbe in
    produzione: il numero che si vede oggi è calcolato con quello che si
    sapeva ieri, e non con quello che si saprà.

    LA GIORNATA IN CORSO NON È UNA GIORNATA.

    Il 19 settembre 2026, alle prime esecuzioni, l'ultima riga diceva 25
    notizie. La media dell'archivio su Bitcoin è circa 120 al giorno: quelle
    25 non erano un calo, erano la mattina.

    Il guaio è che il numero SEMBRA uguale a tutti gli altri. Quel giorno il
    ritardo valeva +0,081 con un pavimento di ±0,090, quindi rumore. Ma il
    pavimento è SIGMA_ARTICOLO/√n, e n cresce tutto il giorno: la sera, con 80
    articoli, il pavimento scende a 0,050 e lo stesso +0,081 diventa "1,6
    volte il pavimento" senza che sia cambiato niente tranne l'ora.

    Un numero che si rafforza col passare della giornata è un numero che
    inganna chi lo guarda due volte. Quindi la giornata in corso si calcola,
    si mostra, e si tiene FUORI dal test: `anomalie.py` ha lo stesso problema
    e lo chiama `giornata_troppo_giovane`.
    """
    oggi = date.today() if oggi is None else oggi
    coppie: list[tuple[date, float, float]] = []
    for giorno, (media, quante) in sorted(sent.items()):
        if quante < MINIMO_NOTIZIE:
            continue
        r = rendimento_precedente(prezzi, giorno, k)
        if r is None:
            continue
        coppie.append((giorno, r, media))

    righe = []
    for i, (giorno, r, s) in enumerate(coppie):
        passato = coppie[:i]
        if len(passato) < minimo_fit:
            continue
        a, b = retta([p[1] for p in passato], [p[2] for p in passato])
        atteso = a + b * r
        righe.append({
            "giorno": giorno,
            "rendimento": r,
            "sentiment": s,
            "atteso": atteso,
            "residuo": s - atteso,
            "giorni_stima": len(passato),
            "quante": quante,
            # Sotto questo, il ritardo è indistinguibile dal caso di quali
            # articoli sono usciti quel giorno. Vedi `pavimento()`.
            "pavimento": pavimento(quante),
            # La giornata non è finita: il conteggio crescerà ancora, e con
            # lui il pavimento si abbasserà. Si guarda, non si misura.
            "parziale": giorno >= oggi,
        })
    return righe


def pavimento(quante: int) -> float:
    """
    L'errore naturale di una media di `quante` articoli: SIGMA_ARTICOLO/√n.

    Serve perché un residuo senza scala non è un'informazione. "+0,079" non
    dice a nessuno se la stampa sta davvero correndo più del movimento o se
    quel giorno sono semplicemente usciti articoli un po' più ottimisti del
    solito: è lo stesso difetto per cui la home apriva con "ADA +0,34 su 3
    news" ed era un primo posto sorteggiato.

    Stesso SIGMA_ARTICOLO di `anomalie.py` e di `incertezza.js`, importato e
    non ricopiato: tre copie dello stesso 0,45 sono tre occasioni di
    aggiornarne due.
    """
    if quante < 1:
        return float("inf")
    return SIGMA_ARTICOLO / (quante ** 0.5)


def rendimento_futuro(prezzi: dict[date, float], giorno: date,
                      orizzonte: int) -> float | None:
    """Il movimento fra la chiusura di giorno e quella di giorno+orizzonte."""
    dopo = giorno + timedelta(days=orizzonte)
    p0, p1 = prezzi.get(giorno), prezzi.get(dopo)
    if not p0 or p1 is None:
        return None
    return (p1 - p0) / p0


def stampa_ultimo(righe: list[dict], k: int) -> None:
    """
    L'ultimo giorno, con le due scale accanto invece che da solo.

    Un residuo nudo è illeggibile. "+0,079" va confrontato con due cose
    diverse, e servono tutte e due:

    - il PAVIMENTO, cioè quanto oscilla la media di quel giorno solo perché
      sono usciti quegli articoli e non altri. Sotto il pavimento il numero
      non esiste;
    - la NORMALE del titolo, cioè quanto il ritardo oscilla di solito. Sopra
      il pavimento ma dentro la normale vuol dire "misurabile ma ordinario",
      che è l'informazione utile nove giorni su dieci.

    Senza la seconda si finisce a chiamare notizia ogni scostamento visibile,
    che è il difetto che `anomalie.py` esiste per non avere.
    """
    u = righe[-1]
    stato = " — GIORNATA IN CORSO" if u.get("parziale") else ""
    print(f"  Ultimo giorno calcolato ({u['giorno']}, "
          f"{u['quante']} notizie){stato}:")
    print(f"    movimento {k}gg     {u['rendimento']:+.2%}")
    print(f"    tono atteso        {u['atteso']:+.3f}")
    print(f"    tono vero          {u['sentiment']:+.3f}")
    print(f"    ritardo            {u['residuo']:+.3f}")
    print(f"    pavimento          ±{u['pavimento']:.3f}"
          f"   ({SIGMA_ARTICOLO}/√{u['quante']})")

    if abs(u["residuo"]) < u["pavimento"]:
        print("    → sotto il pavimento: non distinguibile da quali articoli")
        print("      sono usciti oggi. Non è un ritardo, è rumore.")
    else:
        print(f"    → {abs(u['residuo']) / u['pavimento']:.1f}x il pavimento")

    passati = [r["residuo"] for r in righe[:-1]]
    if len(passati) >= 10:
        m = mediana(passati)
        d = mad(passati)
        print(f"    normale del titolo  mediana {m:+.3f}, dispersione {d:.3f}")
        if d > 0:
            quanti = abs(u["residuo"] - m) / d
            print(f"    → {quanti:.1f} deviazioni dalla sua normale", end="")
            print("  (ordinario)" if quanti < 2 else "  (fuori dal solito)")

    if u.get("parziale"):
        print()
        print("    Attenzione: la giornata non è finita. Il conteggio salirà,")
        print("    il pavimento si abbasserà, e lo stesso ritardo sembrerà più")
        print("    forte stasera di quanto sembri adesso. Non è fuori dal test")
        print("    per prudenza, è fuori perché non è ancora un dato.")


def _riga_esito(nome: str, xs: list[float], ys: list[float]) -> str:
    if len(xs) < 3:
        return f"  {nome:<22} dati insufficienti"
    rho = spearman(xs, ys)
    p_perm = permutazione(xs, ys)
    blocchi = sensibilita_blocchi(xs, ys)
    if not blocchi:
        return f"  {nome:<22} rho {rho:+.3f}   serie troppo corta per i blocchi"
    peggiore = max(blocchi.values())
    quale = max(blocchi, key=lambda b: blocchi[b])
    esito = "PASSA" if peggiore < SOGLIA_P else "no"
    return (f"  {nome:<22} rho {rho:+.3f}   p perm {p_perm:.4f}   "
            f"p blocco peggiore {peggiore:.4f} (blocco {quale})   {esito}")


def analizza(ticker: str, giorni: int = 60, k: int = RITARDO) -> int:
    sent = serie_sentiment(ticker, giorni)
    prezzi = serie_prezzi(ticker, giorni)
    tutte = serie_ritardo(sent, prezzi, k)

    # La giornata in corso si mostra ma non si misura: vedi `serie_ritardo`.
    righe = [r for r in tutte if not r["parziale"]]
    in_corso = [r for r in tutte if r["parziale"]]

    print("=" * 70)
    print(f"  RITARDO DELLE NOTIZIE — {ticker}")
    print("=" * 70)
    print()
    print(f"  Movimento inseguito: ultimi {k} giorni")
    print(f"  Giorni di sentiment utilizzabili: {len(sent)}")
    print(f"  Residui su giornate chiuse (dopo {MINIMO_FIT} di stima): "
          f"{len(righe)}")
    if in_corso:
        print(f"  Giornate ancora aperte, tenute fuori dal test: "
              f"{len(in_corso)}")
    print()

    if len(righe) < MINIMO_GIORNI:
        print(f"  NON SI DICE NIENTE. Servono almeno {MINIMO_GIORNI} residui e")
        print(f"  ce ne sono {len(righe)}. Non è un guasto: la finestra di")
        print(f"  stima consuma i primi {MINIMO_FIT} giorni, ed è il prezzo")
        print("  di non usare il futuro per costruire il passato.")
        print()
        if righe:
            print(f"  Mancano {MINIMO_GIORNI - len(righe)} giorni.")
            print()
            stampa_ultimo(righe + in_corso, k)
        print()
        return 0

    residui = [r["residuo"] for r in righe]

    # CONTROLLO DELLO STRUMENTO, prima del risultato.
    #
    # Il residuo è per costruzione quello che la retta NON spiega, quindi
    # contro il movimento passato deve venire circa zero. Se venisse alto, la
    # retta non sta togliendo quello che dovrebbe e tutto il resto è sospetto.
    # È lo stesso ruolo che ha il controllo sul giorno stesso in
    # verifica_segnale.py, dove uno zero perfetto aveva nascosto per settimane
    # una divisione degenere.
    print("  Controllo: il residuo contro il movimento che dovrebbe aver tolto")
    print("  (deve venire vicino a zero, altrimenti la retta non funziona)")
    print(_riga_esito("passato", [r["rendimento"] for r in righe], residui))
    print()

    print(f"  Il ritardo prevede il rendimento? (soglia {SOGLIA_P:.3f})")
    passato_qualcosa = False
    for h in ORIZZONTI:
        xs, ys = [], []
        for r in righe:
            f = rendimento_futuro(prezzi, r["giorno"], h)
            if f is None:
                continue
            xs.append(r["residuo"])
            ys.append(f)
        riga = _riga_esito(f"T+{h} ({len(xs)} gg)", xs, ys)
        if riga.endswith("PASSA"):
            passato_qualcosa = True
        print(riga)
    print()

    if passato_qualcosa:
        print("  Qualcosa passa. Prima di scriverlo da qualche parte va")
        print("  replicato su un secondo titolo: un risultato solo è un")
        print("  risultato solo.")
    else:
        print("  Non prevede niente. Allora il ritardo NON è un segnale, è una")
        print("  descrizione di adesso: quanto la stampa ha recepito il")
        print("  movimento, non quanto ne resta da fare. Si può mostrare, ma")
        print("  con parole che non promettono un domani.")
    print()
    stampa_ultimo(righe, k)
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
        description="Quanto la stampa ha recuperato il movimento già avvenuto")
    ap.add_argument("--ticker", default="BTC-USD")
    ap.add_argument("--giorni", type=int, default=60)
    ap.add_argument("--ritardo", type=int, default=RITARDO,
                    help=f"giorni di movimento inseguito (default {RITARDO})")
    args = ap.parse_args()
    sys.exit(analizza(args.ticker, args.giorni, args.ritardo))
