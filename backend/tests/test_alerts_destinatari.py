"""
A chi arrivano gli avvisi.

IL DIFETTO, trovato il 31 agosto 2026 mentre si stava per pubblicizzare la
funzione. `get_pro_users_watchlists` faceva un JOIN stretto su `subscriptions`
con `status = 'pro'`. Il paywall è spento dal 7 agosto e gli abbonati sono
zero, quindi quella tabella non ha righe 'pro' e l'interrogazione tornava
sempre vuota.

Risultato: il rilevatore di anomalie calcolava tutto correttamente, l'email
non partiva mai per nessuno, e nei log si leggeva "Nessun utente PRO con
watchlist. Skip." quattro volte al giorno senza che sembrasse un errore.

È lo stesso residuo del piano a pagamento che il 18 agosto teneva l'intera
app dietro il login. Questi test esistono perché non torni una terza volta.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("DATABASE_URL", "postgresql://fake:fake@localhost/fake")

from unittest.mock import MagicMock, patch

import alerts


def _pool_con(righe):
    conn, cur = MagicMock(), MagicMock()
    cur.fetchall.return_value = righe
    conn.cursor.return_value = cur
    return conn, cur


def test_un_utente_senza_abbonamento_riceve_gli_avvisi():
    conn, _ = _pool_con([("mario@example.com", "NVDA"),
                         ("mario@example.com", "BTC-USD")])
    with patch("alerts._conn", return_value=conn), patch("alerts._rel"):
        r = alerts.watchlist_per_utente()
    assert r == {"mario@example.com": ["NVDA", "BTC-USD"]}


def test_la_query_non_pretende_piu_un_abbonamento():
    """
    Il controllo che conta. Finché in questa query c'è `status = 'pro'`, in un
    prodotto dove PRO non esiste, la risposta è sempre nessuno.
    """
    conn, cur = _pool_con([])
    with patch("alerts._conn", return_value=conn), patch("alerts._rel"):
        alerts.watchlist_per_utente()
    sql = cur.execute.call_args[0][0]
    assert "status" not in sql.lower(), sql
    assert "subscriptions" not in sql.lower(), sql
    assert "auth.users" in sql.lower(), "le email stanno in auth.users"


def test_chi_non_ha_watchlist_non_riceve_niente():
    """L'avviso è su cosa segui: senza watchlist non c'è niente da seguire."""
    conn, _ = _pool_con([])
    with patch("alerts._conn", return_value=conn), patch("alerts._rel"):
        assert alerts.watchlist_per_utente() == {}


def test_senza_destinatari_non_esplode_e_non_manda():
    conn, _ = _pool_con([])
    with patch("alerts._conn", return_value=conn), patch("alerts._rel"), \
         patch("alerts.get_sentiment_alerts") as anomalie:
        alerts.check_and_send_alerts()
    assert not anomalie.called, "senza destinatari non serve nemmeno calcolare"


def test_i_ticker_di_piu_utenti_si_uniscono_una_volta_sola():
    """
    Se dieci persone seguono Nvidia, l'anomalia si calcola una volta e non
    dieci: su un piano gratuito la differenza si sente.
    """
    conn, _ = _pool_con([("a@x.com", "NVDA"), ("b@x.com", "NVDA"),
                         ("b@x.com", "ETH-USD")])
    visti = {}

    def finto(tickers):
        visti["tickers"] = sorted(tickers)
        return []

    with patch("alerts._conn", return_value=conn), patch("alerts._rel"), \
         patch("alerts.get_sentiment_alerts", side_effect=finto):
        alerts.check_and_send_alerts()

    assert visti["tickers"] == ["ETH-USD", "NVDA"]
