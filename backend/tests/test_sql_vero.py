"""
Le query, eseguite da un Postgres VERO.

PERCHE' ESISTE (24 settembre 2026)

Tutti gli altri test sostituiscono il database con un MagicMock, che accetta
qualunque stringa: una virgola fuori posto in una CTE, un `%` non raddoppiato,
una colonna scritta male passano verdi e si scoprono in produzione. E il
cuore del prodotto sta proprio nell'SQL: la classifica (market.py), il
rilevatore di anomalie, il digest, gli avvisi.

Qui le stesse funzioni girano contro un Postgres vero, con uno schema come
quello di Supabase (compresa la tabella auth.users). Si accendono solo se
c'e' la variabile CHERUVO_TEST_DATABASE_URL, che deve puntare a un database
DI PROVA: il test crea e distrugge un database suo, ma non va mai puntato a
Supabase.

In locale, con Docker:

    docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=prova postgres:16
    set CHERUVO_TEST_DATABASE_URL=postgresql://postgres:prova@localhost:5432/postgres
    python -m pytest tests/test_sql_vero.py -q

Su GitHub Actions girano da soli: il workflow avvia un Postgres di servizio.
"""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

URL_BASE = os.environ.get("CHERUVO_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not URL_BASE, reason="serve CHERUVO_TEST_DATABASE_URL")

RADICE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="module")
def pool():
    import psycopg2
    import psycopg2.pool

    nome = f"cheruvo_prova_{uuid.uuid4().hex[:8]}"
    amm = psycopg2.connect(URL_BASE)
    amm.autocommit = True
    amm.cursor().execute(f'CREATE DATABASE "{nome}"')
    url = URL_BASE.rsplit("/", 1)[0] + "/" + nome
    p = psycopg2.pool.ThreadedConnectionPool(1, 5, dsn=url)

    # Lo schema di Supabase che il codice da' per scontato.
    conn = p.getconn()
    cur = conn.cursor()
    cur.execute("CREATE SCHEMA auth")
    cur.execute("CREATE TABLE auth.users (id UUID PRIMARY KEY, email TEXT)")
    conn.commit()
    p.putconn(conn)

    import database
    with patch.object(database, "get_pool", lambda: p), \
         patch.object(database, "_get_connection", lambda: p.getconn()), \
         patch.object(database, "_release_connection", lambda c: p.putconn(c)):
        database.init_database()
        import stripe_routes, digest, onboarding, earnings, alerts
        with patch.object(stripe_routes, "get_pool", lambda: p):
            stripe_routes.init_subscriptions_table()
        digest.init_digest_tables()
        with patch.object(onboarding, "get_pool", lambda: p):
            onboarding.init_onboarding_table()
        earnings.init_earnings_tables()
        with patch.object(alerts, "get_pool", lambda: p):
            alerts.init_alert_log()
        yield p

    p.closeall()
    amm.cursor().execute(f'DROP DATABASE "{nome}" WITH (FORCE)')
    amm.close()


def _esegui(pool, sql, parametri=None):
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(sql, parametri)
        righe = cur.fetchall() if cur.description else None
        conn.commit()
        cur.close()
        return righe
    finally:
        pool.putconn(conn)


def _notizia(pool, ticker, titolo, sentiment, ore_fa=1, fonte="GDELT · x.com",
             origine="gdelt"):
    quando = datetime.now(timezone.utc) - timedelta(hours=ore_fa)
    _esegui(pool, """
        INSERT INTO news (ticker, source, title, summary, published_date, url,
                          sentiment, score_source)
        VALUES (%s, %s, %s, '', %s, 'https://x.com/a', %s, %s)
    """, (ticker, fonte, titolo, quando, sentiment, origine))


# ── La classifica ─────────────────────────────────────────────────────────

def test_la_classifica_fonde_le_riprese_su_un_database_vero(pool):
    import market
    for i in range(6):
        _notizia(pool, "BTC-USD", f"Notizia distinta numero {i}", 0.1, fonte=f"GDELT · s{i}.com")
    # La stessa notizia ripresa da dieci testate: vale una voce.
    for i in range(10):
        _notizia(pool, "BTC-USD", "Bitcoin ETF inflows hit record!", 0.9, fonte=f"GDELT · r{i}.com")
    with patch.object(market, "get_pool", lambda: pool):
        righe = market._fetch_market()
        copertura = market._fetch_copertura()
    btc = [r for r in righe if r["ticker"] == "BTC-USD"][0]
    assert btc["news"] == 7          # 6 distinte + 1 ripresa dieci volte
    assert btc["riprese"] == 9
    assert abs(btc["sentiment"] - (0.6 + 0.9) / 7) < 1e-3
    assert copertura["BTC-USD"]["ora"] == 7


def test_la_chiave_del_titolo_sql_e_quella_python_coincidono(pool):
    """
    market.py lo dice: le due normalizzazioni DEVONO restare uguali, se no
    grafico e classifica fondono gruppi diversi. Finora nessuno lo provava.
    """
    import market
    from giornaliero import chiave_titolo
    titoli = ["Bitcoin ETF inflows hit record!", "  NVIDIA  (NVDA) jumps 4.5%  ",
              "Hüfte, Ärger & Öl: la Borsa è giù", "Tesla's Q2 -- deliveries miss",
              "snake_case_title e $NVDA", "日本株 上昇",
              "x" * 200]
    for t in titoli:
        riga = _esegui(pool, f"SELECT {market.CHIAVE_TITOLO_SQL} FROM (SELECT %s AS title) t", (t,))
        assert riga[0][0] == chiave_titolo(t), t


# ── Il rilevatore di anomalie ─────────────────────────────────────────────

def test_anomalie_legge_volume_con_le_riprese_e_tono_senza(pool):
    import anomalie
    oggi = datetime.now(timezone.utc).date()
    conteggi, toni, totale, distinte = anomalie._giorni_per_ticker(pool)
    assert conteggi["BTC-USD"][oggi] == 16      # tutte le righe: attenzione
    assert distinte["BTC-USD"][oggi] == 7       # notizie distinte: giudizi
    assert abs(toni["BTC-USD"][oggi] - (0.6 + 0.9) / 7) < 1e-3


# ── Gli avvisi ────────────────────────────────────────────────────────────

def test_destinatari_e_registro_degli_avvisi(pool):
    import alerts
    uid = str(uuid.uuid4())
    _esegui(pool, "INSERT INTO auth.users (id, email) VALUES (%s, 'mario@x.it')", (uid,))
    _esegui(pool, "INSERT INTO watchlist (user_id, ticker) VALUES (%s, 'BTC-USD')", (uid,))
    with patch.object(alerts, "get_pool", lambda: pool):
        persone = alerts.destinatari()
        assert persone["mario@x.it"]["tickers"] == ["BTC-USD"]
        assert alerts.gia_avvisati("mario@x.it", ["BTC-USD"]) == set()
        alerts.segna_avvisati("mario@x.it", ["BTC-USD"])
        alerts.segna_avvisati("mario@x.it", ["BTC-USD"])     # doppio: nessun errore
        assert alerts.gia_avvisati("mario@x.it", ["BTC-USD"]) == {"BTC-USD"}
        # Chi disattiva le email facoltative sparisce dai destinatari.
        _esegui(pool, "INSERT INTO digest_prefs (user_id, enabled) VALUES (%s, FALSE)", (uid,))
        assert "mario@x.it" not in alerts.destinatari()


# ── Il digest ─────────────────────────────────────────────────────────────

def test_il_digest_mette_in_fondo_le_notizie_senza_punteggio(pool):
    import digest
    _notizia(pool, "ETH-USD", "Ethereum senza punteggio", None, ore_fa=2)
    _notizia(pool, "ETH-USD", "Ethereum forte", -0.8, ore_fa=3)
    _notizia(pool, "ETH-USD", "Ethereum debole", 0.1, ore_fa=4)
    stats = digest.get_week_stats(["ETH-USD"])
    titoli = [n["title"] for n in stats["ETH-USD"]["news"]]
    assert titoli == ["Ethereum forte", "Ethereum debole"]


# ── L'email di benvenuto una volta sola ───────────────────────────────────

def test_la_prenotazione_del_benvenuto_riesce_una_volta(pool):
    import onboarding
    uid = str(uuid.uuid4())
    with patch.object(onboarding, "get_pool", lambda: pool):
        onboarding.register_user(uid, "a@b.c")
        assert onboarding._prenota(uid, 0) is True
        assert onboarding._prenota(uid, 0) is False
        onboarding._libera(uid, 0)
        assert onboarding._prenota(uid, 0) is True


# ── Il ripasso notturno ───────────────────────────────────────────────────

def test_il_ripasso_conserva_il_tono_gdelt_e_il_marchio_regolatorio(pool):
    sys.path.insert(0, RADICE)
    import backfill_sentiment as bf
    _notizia(pool, "SOL-USD", "Solana tone row", 0.25, origine="gdelt")
    _notizia(pool, "SOL-USD", "ESMA statement on MiCA", 0.0,
             fonte="ESMA", origine="istituzionale")
    ids = dict(_esegui(pool, "SELECT title, id FROM news WHERE ticker = 'SOL-USD'"))
    with patch.object(bf, "get_pool", lambda: pool):
        righe = bf._fetch_chunk(50, {ids["Solana tone row"] + 100000})
        assert {r[1] for r in righe} >= {"Solana tone row", "ESMA statement on MiCA"}
        bf._apply([(ids["Solana tone row"], -0.4), (ids["ESMA statement on MiCA"], 0.3)])
        dopo = {t: (s, o, g) for t, s, o, g in _esegui(pool, """
            SELECT title, sentiment, score_source, tono_gdelt FROM news
            WHERE ticker = 'SOL-USD'""")}
        assert dopo["Solana tone row"][1] == "llm2"
        assert abs(dopo["Solana tone row"][2] - 0.25) < 1e-6, "il tono GDELT e' salvo"
        assert dopo["ESMA statement on MiCA"][1] == "istituzionale_llm2"
        # E non vengono piu' ripresi.
        rimasti = {r[1] for r in bf._fetch_chunk(50)}
        assert "ESMA statement on MiCA" not in rimasti


def test_il_ripunteggio_del_cron_conserva_il_marchio(pool):
    import sentiment_groq
    _notizia(pool, "LINK-USD", "Fed statement on crypto", 0.0,
             fonte="Federal Reserve Board", origine="istituzionale")
    with patch.object(sentiment_groq, "get_pool", lambda: pool), \
         patch.object(sentiment_groq, "score_batch", return_value=[0.2]):
        assert sentiment_groq.rescore_non_av_news("LINK-USD") == 1
        assert sentiment_groq.rescore_non_av_news("LINK-USD") == 0
    origine = _esegui(pool, "SELECT score_source FROM news WHERE ticker = 'LINK-USD'")
    assert origine == [("istituzionale_llm2",)]


# ── La migrazione 009 ─────────────────────────────────────────────────────

def test_la_migrazione_009_toglie_il_muro_e_tiene_il_tetto(pool):
    percorso = os.path.join(RADICE, "supabase", "migrations", "009_watchlist_senza_muro.sql")
    _esegui(pool, open(percorso, encoding="utf-8").read())
    uid = str(uuid.uuid4())
    for tk in ("NVDA", "AAPL", "MSFT", "ENI.MI", "BTC-USD"):
        _esegui(pool, "INSERT INTO watchlist (user_id, ticker) VALUES (%s, %s)", (uid, tk))
    assert _esegui(pool, "SELECT COUNT(*) FROM watchlist WHERE user_id = %s", (uid,))[0][0] == 5

    import psycopg2
    with pytest.raises(psycopg2.Error):
        _esegui(pool, "INSERT INTO watchlist (user_id, ticker) VALUES (%s, 'nvda; drop')", (uid,))
    for i in range(95):
        _esegui(pool, "INSERT INTO watchlist (user_id, ticker) VALUES (%s, %s)", (uid, f"T{i}"))
    with pytest.raises(psycopg2.Error):
        _esegui(pool, "INSERT INTO watchlist (user_id, ticker) VALUES (%s, 'UNOPIU')", (uid,))
