"""
Test del controllo simboli.

Il difetto che ha fatto nascere lo script era muto: `STM.MI` non esiste su
nessun listino, chi apriva quel titolo leggeva "Dati prezzi non disponibili" e
passava oltre, e intanto le notizie continuavano a entrare in archivio sotto un
ticker fantasma. Sette righe prima che qualcuno se ne accorgesse per caso.

Qui si prova che il censimento distingue vivo da morto e che lo spostamento
delle righe non scrive niente finché non glielo si chiede.
"""
from unittest.mock import MagicMock, patch

import controlla_ticker as ct


def test_i_simboli_che_non_rispondono_finiscono_nell_elenco():
    finti = {"ENI.MI": "Eni", "STM.MI": "STM.MI", "NVDA": "NVIDIA"}
    def finto_validate(tk):
        return {"valid": tk != "STM.MI", "nome": finti[tk]}

    with patch.dict("sys.modules"), \
         patch("gdelt_source.TERMINE_QUERY", finti), \
         patch("prices.validate_ticker", side_effect=finto_validate), \
         patch.object(ct, "PAUSA", 0):
        assert ct.censisci() == ["STM.MI"]


def test_un_simbolo_che_esplode_conta_come_rotto():
    """Un'eccezione di rete non deve far saltare il censimento a metà."""
    def finto_validate(tk):
        if tk == "ROTTO.MI":
            raise RuntimeError("rete giù")
        return {"valid": True, "nome": tk}

    with patch("gdelt_source.TERMINE_QUERY", {"ROTTO.MI": "x", "ENI.MI": "Eni"}), \
         patch("prices.validate_ticker", side_effect=finto_validate), \
         patch.object(ct, "PAUSA", 0):
        assert ct.censisci() == ["ROTTO.MI"]


def _pool_finto(conteggi):
    pool, conn, cur = MagicMock(), MagicMock(), MagicMock()
    conn.cursor.return_value = cur
    pool.getconn.return_value = conn
    cur.fetchone.side_effect = [(n,) for n in conteggi]
    return pool, conn, cur


def test_senza_scrivi_non_tocca_niente():
    pool, conn, cur = _pool_finto([7, 0, 0])
    with patch("database.get_pool", return_value=pool):
        assert ct.rinomina("STM.MI", "STMMI.MI") == 7
    conn.commit.assert_not_called()
    assert not [c for c in cur.execute.call_args_list if "UPDATE" in str(c)], \
        "senza --scrivi non deve partire nessuna UPDATE"


def test_con_scrivi_sposta_e_conferma():
    pool, conn, cur = _pool_finto([7, 2, 0])
    with patch("database.get_pool", return_value=pool):
        assert ct.rinomina("STM.MI", "STMMI.MI", davvero=True) == 9
    conn.commit.assert_called_once()
    aggiornamenti = [c for c in cur.execute.call_args_list if "UPDATE" in str(c)]
    assert len(aggiornamenti) == 2, "una UPDATE per ogni tabella che aveva righe"


def test_se_non_c_e_niente_da_spostare_non_si_inventa_una_scrittura():
    pool, conn, _ = _pool_finto([0, 0, 0])
    with patch("database.get_pool", return_value=pool):
        assert ct.rinomina("STM.MI", "STMMI.MI", davvero=True) == 0
    conn.commit.assert_not_called()
