"""
Test del conteggio visite.

Due proprietà da proteggere, e sono in tensione fra loro.

La prima è che il conteggio non menta: se ci finiscono dentro la sveglia
esterna e i crawler, il numero si gonfia e si finisce per festeggiare il
traffico di un cron.

La seconda è che non faccia danni: questo codice gira dentro un middleware, su
OGNI richiesta. Se solleva un'eccezione perché il database non risponde,
l'utente riceve un errore per colpa di una statistica. Vale meno di zero.
"""
import visite


# ── Cosa NON va contato ───────────────────────────────────────────────────
def test_la_sveglia_esterna_non_conta_come_visita():
    """
    /ping viene chiamato ogni pochi minuti da cron-job.org per non far
    addormentare Render. Contarlo vorrebbe dire vedere centinaia di visite
    al giorno fatte da nessuno, ed è il numero gonfio che fa prendere
    decisioni sbagliate.
    """
    for p in ("/ping", "/health"):
        assert any(p.startswith(i) for i in visite.IGNORA), p


def test_le_pagine_vere_contano():
    assert not any("/api/market/today".startswith(i) for i in visite.IGNORA)
    assert not any("/api/news/BTC-USD".startswith(i) for i in visite.IGNORA)


def test_i_crawler_dichiarati_vengono_esclusi():
    for ua in ("Mozilla/5.0 (compatible; Googlebot/2.1)",
               "python-requests/2.31.0",
               "curl/8.4.0",
               "Uptime-Monitor/1.0",
               ""):
        assert visite.e_bot(ua), ua


def test_un_browser_vero_non_viene_scambiato_per_un_bot():
    umani = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Version/17.0 Mobile Safari/604.1",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Firefox/121.0",
    ]
    for ua in umani:
        assert not visite.e_bot(ua), ua


# ── Non deve mai rompere la richiesta vera ────────────────────────────────
def test_senza_gettone_non_fa_niente_e_non_esplode():
    visite.registra("", "/api/market/today")
    visite.registra(None, "/api/market/today")


def test_un_database_irraggiungibile_non_propaga_l_errore():
    """
    Gira dentro un middleware, su ogni richiesta. Un'eccezione qui
    trasformerebbe un problema di statistica nel problema dell'utente.
    """
    from unittest.mock import patch
    with patch("database.get_pool", side_effect=RuntimeError("db giù")):
        visite.registra("sessione-finta", "/api/market/today")   # non deve sollevare
        visite.scarica_su_database()


# ── Il difetto che ha fatto morire il backend ─────────────────────────────
def test_registrare_non_tocca_il_database():
    """
    La prima versione, dell'8 agosto 2026, apriva una connessione a OGNI
    richiesta e ci eseguiva pure un CREATE TABLE IF NOT EXISTS. Il pool ne ha
    da 2 a 10: bastavano poche richieste ravvicinate perché finissero e il
    backend smettesse di rispondere. E' morto a intermittenza per due giorni.

    Adesso `registra` deve limitarsi a sommare in memoria.
    """
    from unittest.mock import patch
    with patch("database.get_pool") as pool:
        for i in range(300):
            visite.registra(f"sessione-{i % 20}", "/api/market/today")
        assert not pool.called, (
            "registra() ha chiesto una connessione: e' tornato il difetto "
            "che svuotava il pool a ogni richiesta")


def test_il_conteggio_si_accumula_invece_di_scrivere_ogni_volta():
    visite._conteggio.clear()
    for _ in range(50):
        visite.registra("una-sessione", "/api/market/today")
    assert visite._conteggio[("una-sessione", "/api/market/today")] == 50
    assert len(visite._conteggio) == 1, "50 richieste, una sola riga da scrivere"
    visite._conteggio.clear()


def test_se_la_scrittura_fallisce_i_conteggi_non_si_perdono():
    """
    Uno scarico fallito non deve buttare via quello che aveva in mano: al
    giro dopo si riprova.
    """
    from unittest.mock import patch
    visite._conteggio.clear()
    for _ in range(7):
        visite.registra("sessione-x", "/api/market/today")

    with patch("database.get_pool", side_effect=RuntimeError("db giù")):
        assert visite.scarica_su_database() == 0

    assert visite._conteggio.get(("sessione-x", "/api/market/today")) == 7, (
        "i conteggi sono stati persi invece di essere rimessi in coda")
    visite._conteggio.clear()
