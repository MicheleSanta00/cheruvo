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


# ── Leggere il numero senza farsi ingannare dal timer ─────────────────────
#
# Il frontend si ricarica da solo: la classifica ogni 15 minuti, il titolo
# aperto ogni 10, i prezzi del grafico giornaliero ogni 60 secondi. Quindi
# `richieste` sale anche con una scheda dimenticata aperta e NON misura
# l'interesse, per quanto il docstring di questo file l'abbia sostenuto fino
# al 18 agosto 2026. Quello che un timer non gonfia sono i percorsi distinti.
class _CursoreFinto:
    def __init__(self, righe):
        self._righe = righe

    def execute(self, *_a, **_k):
        pass

    def fetchall(self):
        return self._righe

    def close(self):
        pass


def _con_righe(righe):
    from unittest.mock import MagicMock, patch
    conn = MagicMock()
    conn.cursor.return_value = _CursoreFinto(righe)
    pool = MagicMock()
    pool.getconn.return_value = conn
    return patch("database.get_pool", return_value=pool)


def test_una_scheda_lasciata_aperta_non_sembra_una_visita_attiva():
    """
    Il 17 agosto 2026 il rapporto richieste/sessioni era 78 a 1, il piu' alto
    mai registrato, e sembrava il visitatore piu' interessato di sempre. Erano
    i prezzi del grafico giornaliero richiesti una volta al minuto.
    """
    righe = [("s1", "/api/prices/NVDA", 62),
             ("s1", "/api/market/today", 5),
             ("s1", "/api/news/NVDA", 4),
             ("s1", "/api/sentiment/NVDA", 4)]
    with _con_righe(righe):
        d = visite.dettaglio("2026-08-17")

    assert len(d) == 1
    assert d[0]["richieste"] == 75, "le richieste restano tante"
    assert d[0]["percorsi"] == 4, (
        "i percorsi distinti devono restare quattro: sessantadue chiamate "
        "allo stesso indirizzo sono un timer, non una persona")


def test_chi_gira_davvero_nel_sito_si_vede_dai_percorsi():
    """Tre titoli guardati fanno tre terzine di percorsi diversi."""
    righe = [(f"s2", f"/api/{cosa}/{t}", 1)
             for t in ("NVDA", "ENI.MI", "BTC-USD")
             for cosa in ("news", "prices", "sentiment")]
    with _con_righe(righe):
        d = visite.dettaglio("2026-08-17")

    assert d[0]["percorsi"] == 9
    assert d[0]["richieste"] == 9, (
        "nove richieste e nove percorsi: meno traffico del caso qui sopra "
        "ma molto piu' interesse")


def test_il_dettaglio_tiene_separate_le_sessioni():
    righe = [("s1", "/api/market/today", 3),
             ("s2", "/api/market/today", 1),
             ("s2", "/api/news/ENI.MI", 1)]
    with _con_righe(righe):
        d = {x["sessione"]: x for x in visite.dettaglio("2026-08-17")}

    assert d["s1"]["percorsi"] == 1 and d["s1"]["richieste"] == 3
    assert d["s2"]["percorsi"] == 2 and d["s2"]["richieste"] == 2


def test_il_riepilogo_porta_anche_i_percorsi():
    """
    Senza questa colonna il rapporto mostra solo il numero gonfiabile, ed e'
    quello che si guarda per decidere se la promozione funziona.
    """
    from datetime import date
    with _con_righe([(date(2026, 8, 17), 1, 78, 4)]):
        r = visite.riepilogo(14)

    assert r[0]["percorsi"] == 4
    assert r[0]["richieste"] == 78


def test_un_giorno_senza_visite_non_inventa_niente():
    with _con_righe([]):
        assert visite.dettaglio("2026-08-12") == []


# ── La promessa sulla privacy, imposta invece che dichiarata ──────────────
def test_la_schermata_iniziale_non_e_una_scelta():
    """
    Il 16 agosto 2026 DIA e GOOG comparivano in sei sessioni su nove, sempre
    con un solo `/news/`, mai con prezzi o sentiment. Non li cercava nessuno:
    sono nella watchlist predefinita e la sidebar li chiede da sola.
    """
    iniziale = ["/api/market/today", "/api/market/stats", "/api/fear-greed",
                "/api/news/DIA", "/api/news/GOOG"]
    assert visite.titoli_scelti(iniziale) == set()


def test_un_titolo_aperto_si_riconosce_dal_validate():
    """`useFinData` chiama /validate/ come prima cosa, e solo li'."""
    percorsi = ["/api/market/today", "/api/news/DIA", "/api/news/GOOG",
                "/api/validate/SOL-USD", "/api/news/SOL-USD",
                "/api/prices/SOL-USD", "/api/sentiment/SOL-USD"]
    assert visite.titoli_scelti(percorsi) == {"SOL-USD"}


def test_la_sessione_da_sei_percorsi_del_16_agosto_aveva_scelto_solana():
    """
    Con la vecchia regola (percorsi <= 6) questa sessione veniva stampata
    come "ha aperto e basta". Aveva aperto Solana.
    """
    percorsi = ["/api/market/today", "/api/market/stats", "/api/fear-greed",
                "/api/news/SOL-USD", "/api/prices/SOL-USD",
                "/api/sentiment/SOL-USD", "/api/validate/SOL-USD"]
    assert visite.titoli_scelti(percorsi) == {"SOL-USD"}


def test_piu_titoli_aperti_si_contano_tutti():
    percorsi = [f"/api/validate/{t}" for t in
                ("ETH-USD", "DOGE-USD", "SOL-USD", "ETH-USD")]
    assert visite.titoli_scelti(percorsi) == {"ETH-USD", "DOGE-USD", "SOL-USD"}


def test_l_identificativo_dell_utente_non_finisce_nella_tabella():
    """
    Il docstring promette che il conteggio non e' legato a un account. Il 18
    agosto 2026 il dettaglio dei percorsi ha mostrato
    `/api/subscription/b86cd4db-...` salvato accanto al gettone di sessione:
    da li' si risaliva alla persona con una join.
    """
    visite._conteggio.clear()
    visite.registra("s1", "/api/subscription/b86cd4db-7a1e-43b3-8042-9976dd921579")
    chiavi = list(visite._conteggio)
    visite._conteggio.clear()

    assert chiavi == [("s1", "/api/subscription/:id")], chiavi
    assert not any("b86cd4db" in p for _, p in chiavi)


def test_i_percorsi_normali_restano_intatti():
    """Mascherare troppo vorrebbe dire perdere proprio quello che serve."""
    for p in ("/api/news/NVDA", "/api/prices/ENI.MI", "/api/summary/BTC-USD",
              "/api/market/today", "/api/validate/ADIL"):
        assert visite.senza_identificativi(p) == p, p


def test_l_identificativo_sparisce_anche_in_mezzo_al_percorso():
    assert visite.senza_identificativi(
        "/api/utenti/b86cd4db-7a1e-43b3-8042-9976dd921579/watchlist"
    ) == "/api/utenti/:id/watchlist"


def test_due_utenti_diversi_sullo_stesso_indirizzo_si_sommano():
    """
    Mascherare non deve creare righe doppie: due sessioni sullo stesso
    endpoint devono restare due chiavi, la stessa sessione una sola.
    """
    visite._conteggio.clear()
    visite.registra("s1", "/api/subscription/aaaaaaaa-1111-2222-3333-444444444444")
    visite.registra("s1", "/api/subscription/bbbbbbbb-1111-2222-3333-444444444444")
    assert visite._conteggio[("s1", "/api/subscription/:id")] == 2
    assert len(visite._conteggio) == 1
    visite._conteggio.clear()
