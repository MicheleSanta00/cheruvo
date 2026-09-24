"""
Chi non ha un account che trattamento riceve.

Una riga sola, ma e' quella che decide se un visitatore vede il prodotto o una
schermata di accesso, e va tenuta ferma: la prima versione inventava un tier
"visita" con sette giorni di storico, cioe' cambiava di nascosto cosa si
compra registrandosi mentre il compito era solo togliere il muro.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from auth import tier_di


def test_chi_non_ha_un_account_vale_come_un_iscritto_senza_abbonamento():
    """
    La regola del titolo, in TUTTI e due gli stati del paywall.

    Fino al 24 settembre 2026 questo test controllava `tier_di(None) ==
    "free"`, che e' vero solo col paywall acceso. Col paywall spento un
    iscritto senza abbonamento vale "pro", quindi il visitatore restava un
    gradino sotto e riceveva 403 sui periodi lunghi: esattamente il "livello
    nuovo inventato di nascosto" che questo file dice di voler impedire.
    """
    from unittest.mock import patch
    import auth

    for acceso in (True, False):
        with patch("auth.PAYWALL_ATTIVO", acceso), \
             patch("auth.get_pool") as pool:
            # Un iscritto senza riga in `subscriptions`.
            pool.return_value.getconn.return_value.cursor.return_value \
                .fetchone.return_value = None
            auth._tier_cache.clear()
            iscritto = auth.get_user_tier("utente-senza-abbonamento")
            assert tier_di(None) == iscritto, f"paywall acceso={acceso}"
            assert tier_di({}) == iscritto
            assert tier_di({"email": "x@y.z"}) == iscritto, "senza 'sub' non e' nessuno"
        auth._tier_cache.clear()


def test_col_paywall_acceso_il_visitatore_e_free():
    from unittest.mock import patch
    with patch("auth.PAYWALL_ATTIVO", True):
        assert tier_di(None) == "free"


def test_non_esistono_livelli_nuovi():
    """
    Se un giorno qui torna fuori un "visita", o qualunque altro nome, vuol
    dire che si sta decidendo una politica di prodotto dentro una funzione
    che doveva solo dire chi sei.
    """
    assert tier_di(None) in ("free", "pro")
