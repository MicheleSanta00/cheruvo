"""
Le email dei primi giorni.

Trovato il 24 settembre 2026, leggendo le email come le riceve un utente:
  - il giorno 7 vendeva "Cheruvo PRO a 9 euro al mese" a chi aveva gia'
    tutto gratis, perche' il paywall e' spento dal 6 agosto;
  - il giorno 0 prometteva limiti (3 titoli, 30 giorni) che non esistono;
  - nessuna diceva come smettere di riceverle;
  - `send_welcome` mandava un benvenuto nuovo a ogni chiamata.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("DATABASE_URL", "postgresql://fake:fake@localhost/fake")

from unittest.mock import MagicMock, patch

import onboarding


def test_col_paywall_spento_il_giorno_7_non_vende_niente():
    with patch("auth.PAYWALL_ATTIVO", False):
        oggetto, corpo = onboarding._email_day7("a@b.c", "https://x/unsub")
    for vietata in ("€9", "9/mese", "PRO", "Sblocca"):
        assert vietata not in oggetto + corpo, vietata
    assert "rispondi" in corpo.lower()


def test_col_paywall_acceso_il_giorno_7_torna_quello_di_prima():
    with patch("auth.PAYWALL_ATTIVO", True):
        oggetto, corpo = onboarding._email_day7("a@b.c")
    assert "PRO" in oggetto


def test_il_benvenuto_non_promette_limiti_che_non_esistono():
    with patch("auth.PAYWALL_ATTIVO", False):
        _, corpo = onboarding._email_day0("a@b.c")
    assert "fino a 3" not in corpo and "30 giorni" not in corpo
    assert "Llama" not in corpo


def test_ogni_email_dice_come_smettere_di_riceverla():
    link = "https://x/api/digest/unsubscribe?u=1&t=2"
    with patch("auth.PAYWALL_ATTIVO", False):
        for crea in (onboarding._email_day0, onboarding._email_day3,
                     onboarding._email_day7):
            _, corpo = crea("a@b.c", link)
            assert link in corpo, crea.__name__


def _pool_con_prenotazione(presa: bool):
    pool, conn, cur = MagicMock(), MagicMock(), MagicMock()
    conn.cursor.return_value = cur
    cur.fetchone.return_value = (1,) if presa else None
    pool.getconn.return_value = conn
    return pool, cur


def test_il_benvenuto_parte_una_volta_sola():
    """Si dichiarava idempotente e non lo era: ogni chiamata, un'email."""
    pool, cur = _pool_con_prenotazione(presa=False)
    with patch("onboarding.get_pool", return_value=pool), \
         patch("onboarding._send") as manda:
        assert onboarding.send_welcome("u1", "a@b.c") is False
    assert not manda.called


def test_se_l_invio_fallisce_la_prenotazione_si_libera():
    pool, cur = _pool_con_prenotazione(presa=True)
    with patch("onboarding.get_pool", return_value=pool), \
         patch("onboarding._send", return_value=False):
        assert onboarding.send_welcome("u1", "a@b.c") is False
    sql = " ".join(str(c) for c in cur.execute.call_args_list)
    assert "sent_day0 = FALSE WHERE" in sql, "il giro dopo deve poterci riprovare"


def test_un_giorno_inventato_non_diventa_sql():
    import pytest
    with pytest.raises(ValueError):
        onboarding.mark_sent("u1", 99)


def test_chi_ha_detto_basta_non_riceve_i_consigli():
    import inspect
    sorgente = inspect.getsource(onboarding.check_and_send_onboarding_emails)
    assert "digest_prefs" in sorgente and "enabled" in sorgente
