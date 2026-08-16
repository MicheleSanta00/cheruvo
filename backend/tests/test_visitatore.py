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
    assert tier_di(None) == "free"
    assert tier_di({}) == "free"
    assert tier_di({"email": "x@y.z"}) == "free", "senza 'sub' non e' nessuno"


def test_non_esistono_livelli_nuovi():
    """
    Se un giorno qui torna fuori un "visita", o qualunque altro nome, vuol
    dire che si sta decidendo una politica di prodotto dentro una funzione
    che doveva solo dire chi sei.
    """
    assert tier_di(None) in ("free", "pro")
