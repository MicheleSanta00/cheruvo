"""
Test del ritardo delle notizie.

La proprietà da difendere è una sola, e se cade non se ne accorge nessuno:
il numero del giorno T dev'essere calcolato con quello che si sapeva PRIMA di
T. Una retta stimata anche su un solo giorno successivo produce residui più
piccoli del vero e un test che passa senza motivo, e non lascia tracce: il
programma gira, stampa numeri plausibili, e sono sbagliati.

Per questo il test centrale qui sotto non controlla un valore atteso. Controlla
che aggiungere giorni IN FONDO non cambi nemmeno di una cifra i residui già
calcolati.
"""
from datetime import date, timedelta

import ritardo_notizie as rn


def _giorni(n: int, da=date(2026, 8, 7)):
    return [da + timedelta(days=i) for i in range(n)]


def _prezzi(valori, da=date(2026, 8, 7)):
    return {da + timedelta(days=i): v for i, v in enumerate(valori)}


def _sent(valori, quante=50, da=date(2026, 8, 7)):
    return {da + timedelta(days=i): (v, quante) for i, v in enumerate(valori)}


# ── La retta ──────────────────────────────────────────────────────────────
def test_la_retta_ritrova_una_retta():
    xs = [0.0, 1.0, 2.0, 3.0]
    ys = [1.0, 3.0, 5.0, 7.0]        # y = 1 + 2x
    a, b = rn.retta(xs, ys)
    assert abs(a - 1.0) < 1e-9
    assert abs(b - 2.0) < 1e-9


def test_la_retta_non_esplode_su_una_x_costante():
    """Tutti i movimenti identici: la pendenza non è definita, non si inventa."""
    a, b = rn.retta([0.5] * 5, [1.0, 2.0, 3.0, 4.0, 5.0])
    assert b == 0.0
    assert abs(a - 3.0) < 1e-9


# ── Il movimento inseguito ────────────────────────────────────────────────
def test_senza_il_prezzo_di_partenza_non_si_inventa_un_rendimento():
    prezzi = {date(2026, 8, 10): 100.0}
    assert rn.rendimento_precedente(prezzi, date(2026, 8, 10), k=2) is None


def test_il_rendimento_guarda_indietro_non_avanti():
    prezzi = _prezzi([100.0, 110.0, 120.0])
    r = rn.rendimento_precedente(prezzi, date(2026, 8, 9), k=2)
    assert abs(r - 0.20) < 1e-9        # da 100 a 120, non da 120 a qualcosa


# ── IL TEST CHE CONTA ─────────────────────────────────────────────────────
def test_il_residuo_di_oggi_non_cambia_se_domani_arrivano_altri_giorni():
    """
    Stima in avanti e basta.

    Si calcolano i residui su una serie, poi si allunga la serie in fondo e si
    ricalcola. I residui dei giorni che c'erano già devono restare IDENTICI:
    se cambiano, vuol dire che la retta di un giorno passato si è accorta di
    un giorno futuro, ed è esattamente il difetto che rende un risultato
    impossibile da smentire e falso.
    """
    n = 40
    prezzi = _prezzi([100.0 * (1.01 ** i) for i in range(n)])
    sent = _sent([(i % 7) / 10.0 - 0.3 for i in range(n)])

    corte = rn.serie_ritardo(sent, prezzi, k=2, minimo_fit=10)

    n2 = n + 15
    prezzi2 = _prezzi([100.0 * (1.01 ** i) for i in range(n2)])
    sent2 = _sent([(i % 7) / 10.0 - 0.3 for i in range(n2)])
    # I giorni in più hanno un andamento del tutto diverso: se sporcassero le
    # stime precedenti, la differenza salterebbe all'occhio.
    for i in range(n, n2):
        g = date(2026, 8, 7) + timedelta(days=i)
        sent2[g] = (0.95, 50)
        prezzi2[g] = 10.0

    lunghe = rn.serie_ritardo(sent2, prezzi2, k=2, minimo_fit=10)
    per_giorno = {r["giorno"]: r["residuo"] for r in lunghe}

    assert corte, "servono residui da confrontare"
    for r in corte:
        assert r["giorno"] in per_giorno
        assert abs(r["residuo"] - per_giorno[r["giorno"]]) < 1e-12, r["giorno"]


def test_niente_residui_finche_la_finestra_di_stima_non_e_piena():
    n = 25
    prezzi = _prezzi([100.0 + i for i in range(n)])
    sent = _sent([0.1] * n)
    righe = rn.serie_ritardo(sent, prezzi, k=2, minimo_fit=20)
    # I primi giorni servono a stimare e non producono niente. Restano al
    # massimo quelli oltre la finestra, mai tutti.
    assert len(righe) < n
    assert all(r["giorni_stima"] >= 20 for r in righe)


def test_i_giorni_con_poche_notizie_non_entrano():
    """Una media su due articoli è un aneddoto, e non deve stimare niente."""
    n = 30
    prezzi = _prezzi([100.0 + i for i in range(n)])
    sent = _sent([0.1] * n, quante=rn.MINIMO_NOTIZIE - 1)
    assert rn.serie_ritardo(sent, prezzi, k=2, minimo_fit=5) == []


def test_su_un_legame_perfettamente_lineare_il_ritardo_e_zero():
    """
    Se il tono è davvero una funzione lineare del movimento, non c'è niente
    da recuperare e il residuo deve annullarsi. È il controllo che dice che
    il numero misura uno SCARTO e non un livello.
    """
    n = 40
    prezzi = _prezzi([100.0 * (1.0 + 0.01 * ((i % 5) - 2)) ** 1 for i in range(n)])
    sent = {}
    for i in range(n):
        g = date(2026, 8, 7) + timedelta(days=i)
        r = rn.rendimento_precedente(prezzi, g, k=2)
        if r is None:
            continue
        sent[g] = (0.2 + 3.0 * r, 50)      # esattamente una retta

    righe = rn.serie_ritardo(sent, prezzi, k=2, minimo_fit=10)
    assert righe
    assert max(abs(r["residuo"]) for r in righe) < 1e-6


def test_la_soglia_resta_quella_del_progetto():
    """
    Cambiare la soglia per questo file soltanto significherebbe sceglierla
    dopo aver visto il dato, che è la cosa che tutto il progetto esiste per
    non fare.
    """
    assert abs(rn.SOGLIA_P - 0.05 / 3) < 1e-12
    assert rn.BLOCCHI == (2, 3, 5, 7, 10)


# ── La scala ──────────────────────────────────────────────────────────────
def test_il_pavimento_scende_col_numero_di_articoli():
    """
    L'errore di una media di n articoli e' SIGMA_ARTICOLO/radice di n: con
    quattro volte le notizie si dimezza. E' la stessa regola di anomalie.py,
    e deve restare la stessa costante e non una copia.
    """
    assert rn.pavimento(25) > rn.pavimento(100)
    assert abs(rn.pavimento(100) - rn.SIGMA_ARTICOLO / 10) < 1e-12
    assert abs(rn.pavimento(25) - 2 * rn.pavimento(100)) < 1e-12


def test_senza_articoli_il_pavimento_e_infinito():
    """Zero notizie non vuol dire tono neutro: vuol dire che non si sa."""
    assert rn.pavimento(0) == float("inf")


def test_ogni_riga_porta_con_se_la_propria_scala():
    n = 40
    prezzi = _prezzi([100.0 * (1.01 ** i) for i in range(n)])
    sent = _sent([(i % 7) / 10.0 - 0.3 for i in range(n)], quante=64)
    righe = rn.serie_ritardo(sent, prezzi, k=2, minimo_fit=10)
    assert righe
    for r in righe:
        assert r["quante"] == 64
        assert abs(r["pavimento"] - rn.SIGMA_ARTICOLO / 8) < 1e-12


# ── La giornata in corso ──────────────────────────────────────────────────
def test_la_giornata_di_oggi_e_marcata_parziale():
    """
    Oggi il conteggio non e' finito, quindi il pavimento e' piu' alto di
    quello vero e scendera' durante la giornata. Lo stesso ritardo sembrerebbe
    piu' forte la sera che la mattina: va marcato, non mescolato.
    """
    n = 40
    prezzi = _prezzi([100.0 * (1.01 ** i) for i in range(n)])
    sent = _sent([(i % 7) / 10.0 - 0.3 for i in range(n)])
    finto_oggi = date(2026, 8, 7) + timedelta(days=n - 1)

    righe = rn.serie_ritardo(sent, prezzi, k=2, minimo_fit=10,
                             oggi=finto_oggi)
    assert righe
    assert righe[-1]["parziale"] is True
    assert all(r["parziale"] is False for r in righe[:-1])


def test_le_giornate_chiuse_non_diventano_parziali_col_tempo():
    """Una giornata finita resta finita: il flag guarda la data, non il conto."""
    n = 30
    prezzi = _prezzi([100.0 + i for i in range(n)])
    sent = _sent([0.1 + (i % 3) / 100 for i in range(n)])
    dopo = date(2026, 8, 7) + timedelta(days=n + 5)
    righe = rn.serie_ritardo(sent, prezzi, k=2, minimo_fit=10, oggi=dopo)
    assert righe
    assert not any(r["parziale"] for r in righe)
