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


# ── 24 settembre 2026: doppioni, etichetta neutra, uscita ─────────────────

class _Registro:
    """Un finto database con dentro le watchlist e il registro degli invii."""

    def __init__(self, righe):
        self.righe = righe
        self.inviati = set()

    def conn(self):
        registro = self
        cur = MagicMock()
        stato = {"ultimo": None}

        def execute(sql, params=None):
            stato["ultimo"] = (sql, params)
            if "INSERT INTO alert_log" in sql:
                registro.inviati.add((params[0], params[1]))

        def fetchall():
            sql, params = stato["ultimo"]
            if "FROM alert_log" in sql:
                email, tickers = params
                return [(t,) for (e, t) in registro.inviati if e == email and t in tickers]
            return registro.righe

        cur.execute.side_effect = execute
        cur.fetchall.side_effect = fetchall
        c = MagicMock()
        c.cursor.return_value = cur
        return c


def _anomalia(tk):
    return {"ticker": tk, "avg_sentiment": 0.02, "news_count": 30,
            "notizie_tipiche": 8.0, "z_volume": 6.0, "z_tono": None}


def test_la_stessa_anomalia_non_parte_quattro_volte_al_giorno():
    """
    Il cron gira quattro volte e l'anomalia resta anomala tutto il giorno:
    senza registro partivano quattro email uguali.
    """
    reg = _Registro([("mario@example.com", "NVDA", "u-1")])
    with patch("alerts._conn", side_effect=reg.conn), patch("alerts._rel"), \
         patch("alerts.get_sentiment_alerts", return_value=[_anomalia("NVDA")]), \
         patch("alerts.resend.Emails.send") as manda:
        for _ in range(4):
            alerts.check_and_send_alerts()
    assert manda.call_count == 1


def test_un_titolo_nuovo_nello_stesso_giorno_parte_lo_stesso():
    reg = _Registro([("mario@example.com", "NVDA", "u-1"),
                     ("mario@example.com", "SOL-USD", "u-1")])
    with patch("alerts._conn", side_effect=reg.conn), patch("alerts._rel"), \
         patch("alerts.resend.Emails.send") as manda:
        with patch("alerts.get_sentiment_alerts", return_value=[_anomalia("NVDA")]):
            alerts.check_and_send_alerts()
        with patch("alerts.get_sentiment_alerts",
                   return_value=[_anomalia("NVDA"), _anomalia("SOL-USD")]):
            alerts.check_and_send_alerts()
    assert manda.call_count == 2
    secondo = manda.call_args_list[1][0][0]
    assert "SOL-USD" in secondo["subject"] and "NVDA" not in secondo["subject"]


def test_un_tono_vicino_a_zero_non_e_negativo():
    """Prima tutto fra -0,15 e +0,15, zero compreso, usciva 'negativo' in rosso."""
    for v in (0.0, 0.1, -0.1, 0.149):
        _, etichetta, _ = alerts._sentiment_label(v)
        assert etichetta == "neutro", v
    assert alerts._sentiment_label(-0.2)[1] == "negativo"
    assert alerts._sentiment_label(0.2)[1] == "positivo"


def test_l_avviso_dice_come_smettere_di_riceverlo():
    corpo = alerts._build_email_html([_anomalia("NVDA")], "https://x/api/digest/unsubscribe?u=1&t=2")
    assert "unsubscribe" in corpo


def test_chi_ha_detto_basta_non_riceve_avvisi():
    """La query stessa esclude chi ha disattivato le email facoltative."""
    conn, cur = _pool_con([])
    with patch("alerts._conn", return_value=conn), patch("alerts._rel"):
        alerts.destinatari()
    sql = cur.execute.call_args[0][0]
    assert "digest_prefs" in sql and "enabled" in sql
