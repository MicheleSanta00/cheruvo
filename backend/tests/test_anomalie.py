"""
Test del rilevatore di anomalie.

Il rischio qui non è che il codice si rompa: è che gridi. Un rilevatore che
segnala tutti i giorni non viene più letto dopo tre giorni, e uno che non
segnala mai non serve a niente. Le due proprietà da proteggere sono quindi
speculari.

La prima: un giorno tranquillo NON deve produrre un avviso. La seconda: un
picco vero deve produrlo anche se in passato c'era già stato un picco, perché
è esattamente lì che un rilevatore basato su media e deviazione standard si
acceca da solo.
"""
from datetime import date, timedelta

import anomalie as an


def _giorni(quanti: int, inizio=None) -> list:
    # I giorni finti partono da DA_QUANDO: prima di quella data il modulo
    # scarta tutto, e un test costruito su luglio misurerebbe il filtro
    # invece della statistica.
    inizio = inizio or an.DA_QUANDO
    return [inizio + timedelta(days=i) for i in range(quanti)]


def _scenario(conteggi_passati: list[int], oggi_n: int,
              toni_passati=None, tono_oggi=0.0):
    """Costruisce i tre dizionari come li produrrebbe la query."""
    giorni = _giorni(len(conteggi_passati) + 1)
    oggi = giorni[-1]
    conteggi = {g: n for g, n in zip(giorni, conteggi_passati + [oggi_n])}
    toni_passati = toni_passati or [0.0] * len(conteggi_passati)
    toni = {g: t for g, t in zip(giorni, toni_passati + [tono_oggi])}
    # Il totale del giorno è tenuto costante: così le variazioni di quota
    # dipendono solo dalla moneta, che è quello che questi test misurano.
    totale = {g: 1000 for g in giorni}
    return an._per_ticker("TEST-USD", conteggi, toni, totale, oggi)


# ── Il pavimento sul tono ─────────────────────────────────────────────────
#
# Trovati il 21 agosto 2026, il primo giorno in cui il rilevatore ha parlato
# in produzione. Il volume aveva il suo pavimento di Poisson dal principio, il
# tono no, e si e' visto subito.
def test_il_tono_di_un_giorno_con_un_articolo_non_si_giudica():
    """
    AMD, 21 agosto 2026: scarto sul tono 2,78 calcolato su UN articolo. La
    "media giornaliera" era il punteggio di quel singolo pezzo.
    """
    r = _scenario([10] * 15, oggi_n=1,
                  toni_passati=[0.08] * 15, tono_oggi=0.9)
    assert r["z_tono"] is None, r
    assert r["stato"] != "anomalia"


def test_sotto_cinque_articoli_il_tono_tace_ma_il_volume_no():
    """
    Le due misure sono indipendenti: pochi articoli tolgono il giudizio sul
    tono, non quello sul volume. Un crollo di volume resta un crollo.
    """
    r = _scenario([40] * 15, oggi_n=2, toni_passati=[0.0] * 15, tono_oggi=0.9)
    assert r["z_tono"] is None
    assert r["z_volume"] is not None


def test_uno_scostamento_dentro_l_errore_della_media_non_e_un_anomalia():
    """
    GOOGL, 21 agosto 2026: dichiarato anomalo con z 4,06. Dieci articoli,
    tono 0,294 contro 0,128 tipico, cioe' uno scostamento di 0,166 contro un
    errore naturale di 0,45/√10 = 0,142. Poco piu' di un errore standard.
    """
    r = _scenario([17] * 15, oggi_n=10,
                  toni_passati=[0.128, 0.13, 0.126, 0.129, 0.127] * 3,
                  tono_oggi=0.294)
    assert abs(r["z_tono"]) < an.SOGLIA_Z, r
    assert r["stato"] == "normale", r


def test_ma_uno_scostamento_grosso_su_tanti_articoli_si_vede_ancora():
    """
    Il pavimento non deve rendere il rilevatore sordo: con cinquanta articoli
    l'errore della media scende a 0,064 e un salto vero resta visibile.
    """
    r = _scenario([50] * 15, oggi_n=50,
                  toni_passati=[0.05] * 15, tono_oggi=0.75)
    assert r["z_tono"] is not None
    assert r["stato"] == "anomalia", r


def test_il_pavimento_del_tono_scende_quando_gli_articoli_salgono():
    """La stessa notizia su piu' articoli deve pesare di piu', non di meno."""
    pochi = _scenario([30] * 15, oggi_n=6,
                      toni_passati=[0.0] * 15, tono_oggi=0.4)
    tanti = _scenario([30] * 15, oggi_n=60,
                      toni_passati=[0.0] * 15, tono_oggi=0.4)
    assert abs(tanti["z_tono"]) > abs(pochi["z_tono"])


def test_la_sigma_per_articolo_e_quella_misurata_sull_archivio():
    """
    Se cambia qui e non in market.py o in incertezza.js, tre parti del
    prodotto cominciano a usare tre dispersioni diverse per la stessa cosa.
    """
    assert an.SIGMA_ARTICOLO == 0.45
    assert an.MINIMO_ARTICOLI_TONO == 5


# ── Statistica di base ────────────────────────────────────────────────────
def test_la_mediana_regge_pari_e_dispari():
    assert an.mediana([3, 1, 2]) == 2
    assert an.mediana([4, 1, 2, 3]) == 2.5
    assert an.mediana([]) == 0.0


def test_il_mad_e_sulla_scala_di_una_sigma():
    """
    Su dati normali MAD × 1,4826 ≈ deviazione standard. Senza quel fattore le
    soglie direbbero "due sigma" intendendo tutt'altro.
    """
    v = [10, 12, 8, 11, 9, 10, 12, 8]
    assert 1.0 < an.mad(v) < 4.0


def test_dispersione_nulla_senza_pavimento_non_produce_un_numero():
    """
    Venti giorni identici: qualunque scostamento sarebbe infinito. Meglio
    None che un infinito travestito da misura.
    """
    assert an.scarto(20, [10] * 20) is None
    assert an.scarto(20, [10] * 20, pavimento=3.0) is not None


# ── Il caso che conta di più: non gridare ─────────────────────────────────
def test_un_giorno_tranquillo_non_e_un_anomalia():
    r = _scenario([10, 9, 11, 10, 12, 8, 10, 11, 9, 10, 10, 11, 9, 10, 10],
                  oggi_n=11)
    assert r["stato"] == "normale", r


def test_un_articolo_in_piu_su_otto_non_e_un_anomalia():
    """
    Il pavimento di Poisson serve a questo: un conteggio che vale 8 oscilla
    di ±2,8 per natura, anche quando non succede niente.
    """
    r = _scenario([8] * 20, oggi_n=9)
    assert r["stato"] == "normale", r


# ── E il caso speculare: accorgersi davvero ───────────────────────────────
def test_un_picco_vero_viene_segnalato():
    r = _scenario([10, 9, 11, 10, 12, 8, 10, 11, 9, 10, 10, 11, 9, 10, 10],
                  oggi_n=60)
    assert r["stato"] == "anomalia"
    assert r["z_volume"] > an.SOGLIA_Z


def test_un_picco_passato_non_acceca_il_rilevatore():
    """
    Il difetto che questa scelta statistica evita. Con media e deviazione
    standard, il picco a 80 gonfia la sigma abbastanza da far sembrare
    normale il picco successivo: il rilevatore si spegne da solo proprio
    dopo aver visto la cosa che doveva rilevare.
    """
    passato = [10, 9, 11, 10, 80, 8, 10, 11, 9, 10, 10, 11, 9, 10, 10]
    r = _scenario(passato, oggi_n=60)
    assert r["stato"] == "anomalia", (
        "un solo picco nello storico ha già spento il rilevatore")


def test_un_crollo_di_attenzione_viene_segnalato():
    r = _scenario([20, 22, 19, 21, 20, 18, 20, 21, 19, 20, 20, 21, 19, 20, 20],
                  oggi_n=1)
    assert r["stato"] == "anomalia"
    assert r["z_volume"] < 0


def test_il_tono_fuori_norma_basta_da_solo():
    """Volume identico al solito, ma il tono si stacca: è comunque una notizia."""
    toni = [0.05, 0.04, 0.06, 0.05, 0.05, 0.04, 0.06, 0.05,
            0.05, 0.04, 0.06, 0.05, 0.05, 0.04, 0.06]
    r = _scenario([10] * 15, oggi_n=10, toni_passati=toni, tono_oggi=-0.60)
    assert r["stato"] == "anomalia"
    assert r["z_tono"] < -an.SOGLIA_Z


# ── Quando non si sa ──────────────────────────────────────────────────────
def test_con_pochi_giorni_dice_che_sta_imparando():
    """
    L'archivio riparte dal 6 agosto 2026 e le regole di raccolta sono
    cambiate il 7. Una normalità calcolata adesso descriverebbe le nostre
    modifiche, non il mercato.
    """
    r = _scenario([10] * 5, oggi_n=90)
    assert r["stato"] == "in_apprendimento"
    assert r["z_volume"] is None, "ha stimato uno scarto senza storico"
    assert r["giorni_mancanti"] == an.MINIMO_GIORNI - 5


def test_lo_storico_prima_del_cambio_di_regole_non_conta():
    """
    L'errore trovato guardando la prima risposta in produzione: il modulo
    diceva "normale" per Bitcoin, perché grazie alla ricostruzione da GDELT
    aveva più di quattordici giorni di storico. Peccato che quei giorni
    fossero stati raccolti con le regole vecchie, prima che il filtro di
    contesto tagliasse il 72% del volume.

    Confrontare oggi con quei giorni vuol dire misurare le proprie modifiche
    e chiamarle mercato.
    """
    vecchi = _giorni(30, inizio=an.DA_QUANDO - timedelta(days=40))
    oggi = an.DA_QUANDO + timedelta(days=1)
    conteggi = {g: 10 for g in vecchi}
    conteggi[oggi] = 90
    toni = {g: 0.0 for g in list(vecchi) + [oggi]}
    totale = {g: 1000 for g in list(vecchi) + [oggi]}

    r = an._per_ticker("BTC-USD", conteggi, toni, totale, oggi)
    assert r["stato"] == "in_apprendimento", (
        "ha usato come normalità dei giorni raccolti con regole diverse")


def test_una_moneta_quasi_senza_notizie_non_ha_una_normalita():
    """
    Con una mediana di un articolo al giorno, passare a tre e' un raddoppio
    che non significa niente. Meglio dirlo che colorarlo di rosso.
    """
    r = _scenario([1, 0, 1, 2, 1, 0, 1, 1, 0, 1, 1, 2, 0, 1, 1], oggi_n=3)
    assert r["stato"] == "troppo_poche"
    assert r["z_volume"] is None


def test_il_sabato_non_diventa_un_crollo_per_tutti():
    """
    Se il conteggio globale si dimezza, la quota di ogni moneta resta la
    stessa. Senza la correzione, ogni sabato sarebbe un crollo di interesse
    per tutte le monete in una volta, cioe' quaranta avvisi falsi a
    settimana.
    """
    giorni = _giorni(16)
    oggi = giorni[-1]
    conteggi = {g: 10 for g in giorni[:-1]}
    conteggi[oggi] = 5                       # dimezzate le notizie sulla moneta
    totale = {g: 1000 for g in giorni[:-1]}
    totale[oggi] = 500                       # ma anche quelle del mondo intero
    toni = {g: 0.0 for g in giorni}
    r = an._per_ticker("TEST-USD", conteggi, toni, totale, oggi)
    assert r["stato"] == "normale", "il sabato è stato scambiato per un crollo"


# ── La proprietà che decide se la funzione serve o no ─────────────────────
def test_quante_volte_grida_su_giornate_in_cui_non_succede_niente():
    """
    Il test più importante del file, e l'unico che misura invece di
    controllare.

    Si simulano giornate normali: conteggi che oscillano come oscilla un
    conteggio (Poisson) e tono che è solo rumore. In quelle giornate il
    rilevatore NON deve trovare niente, se non rarissimamente.

    La prima versione stava a 2σ e produceva 34 avvisi falsi a settimana su
    quaranta monete, cioè cinque al giorno di nulla. Nessuno legge la sesta
    email inutile. La soglia a 4σ è stata scelta da questa misura, e se
    qualcuno la riabbassa per "vedere più segnali" è qui che deve fermarsi.
    """
    import math
    import random

    random.seed(11)

    def poisson(lam):
        L, k, p = math.exp(-lam), 0, 1.0
        while True:
            k += 1
            p *= random.random()
            if p <= L:
                return k - 1

    giri, falsi = 600, 0
    for _ in range(giri):
        gg = _giorni(29)
        conteggi = {g: poisson(15) for g in gg}
        toni = {g: random.gauss(0.02, 0.15) for g in gg}
        totale = {g: 1000 for g in gg}
        if an._per_ticker("X", conteggi, toni, totale, gg[-1])["stato"] == "anomalia":
            falsi += 1

    quota = falsi / giri
    a_settimana = quota * 40 * 7
    assert a_settimana < 4, (
        f"{a_settimana:.1f} avvisi falsi a settimana su 40 monete "
        f"({quota:.1%} al giorno): a questo ritmo l'email diventa rumore "
        f"e smette di essere letta")


# ── L'elenco ──────────────────────────────────────────────────────────────
def test_le_monete_in_apprendimento_restano_nell_elenco():
    """
    Nasconderle farebbe sembrare l'archivio più maturo di quello che è.
    Sapere che di una moneta non sappiamo dire niente è un'informazione.
    """
    righe = [{"stato": "in_apprendimento", "z_volume": None, "z_tono": None},
             {"stato": "anomalia", "z_volume": 3.0, "z_tono": None}]
    assert len(an.solo_anomalie(righe)) == 1


# ── L'email ───────────────────────────────────────────────────────────────
def test_l_alert_non_scatta_piu_su_una_soglia_fissa():
    """
    Il difetto che questa funzione aveva: `ABS(AVG(sentiment)) > 0.2`.
    Scriveva per una moneta con tre articoli finiti sopra 0,2 e taceva
    quando il volume triplicava senza spostare la media.
    """
    import inspect
    import alerts
    sorgente = inspect.getsource(alerts.get_sentiment_alerts)
    assert "HAVING" not in sorgente, "l'alert usa ancora una soglia fissa in SQL"
    assert "anomalie" in sorgente


def test_l_alert_manda_solo_i_ticker_in_watchlist():
    from unittest.mock import patch
    import alerts
    finte = [{"ticker": "SOL-USD", "stato": "anomalia", "sentiment_oggi": -0.55,
              "notizie_oggi": 36, "notizie_tipiche": 8.0,
              "z_volume": 8.7, "z_tono": -4.0},
             {"ticker": "XRP-USD", "stato": "anomalia", "sentiment_oggi": 0.1,
              "notizie_oggi": 40, "notizie_tipiche": 9.0,
              "z_volume": 5.0, "z_tono": None}]
    with patch("anomalie.calcola", return_value=finte):
        fuori = alerts.get_sentiment_alerts(["SOL-USD"])
    assert [a["ticker"] for a in fuori] == ["SOL-USD"]


def test_la_frase_dell_email_parla_di_notizie_non_di_prezzo():
    """
    "sentiment −0,31" fa alzare le spalle. "36 notizie contro le 8 solite"
    fa aprire il sito, ed è un'affermazione che sappiamo dimostrare.
    """
    import alerts
    frase = alerts._riga_motivo({"ticker": "SOL-USD", "news_count": 36,
                                 "notizie_tipiche": 8.0, "z_volume": 8.7,
                                 "z_tono": -4.0})
    assert "36" in frase and "8" in frase
    assert "negativo" in frase
    for vietata in ("compra", "vendi", "salirà", "scenderà"):
        assert vietata not in frase.lower()


def test_un_alert_senza_anomalia_di_volume_dice_comunque_qualcosa():
    import alerts
    frase = alerts._riga_motivo({"ticker": "BTC-USD", "news_count": 80,
                                 "notizie_tipiche": 78.0, "z_volume": 0.2,
                                 "z_tono": -4.5})
    assert frase and "tono" in frase
