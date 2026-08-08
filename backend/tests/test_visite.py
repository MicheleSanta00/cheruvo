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
