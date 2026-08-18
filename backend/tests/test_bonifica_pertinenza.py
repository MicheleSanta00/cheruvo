"""
test_bonifica_pertinenza.py — Il conto prima della cancellazione.

Il rischio qui non e' contare male, e' cancellare. Una riga di archivio tolta
non torna indietro, e il programma decide su un filtro che e' stato sbagliato
per settimane. Quindi: senza --elimina non deve toccare niente, e quello che
non sa giudicare deve lasciarlo stare.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("DATABASE_URL", "postgresql://fake:fake@localhost/fake")

from unittest.mock import patch

import bonifica_pertinenza as bp


SPAZZATURA = "Milwaukee fire near 18th and Mineral , house uninhabitable"
BUONA = "NEAR Protocol price rallies as investors buy the token"


def test_separa_le_righe_buone_da_quelle_fuori_tema():
    righe = [(1, "NEAR-USD", SPAZZATURA),
             (2, "NEAR-USD", BUONA),
             (3, "NEAR-USD", "Body found in water near Lawyers Head in Dunedin")]
    r = bp.esamina(righe)
    assert r["NEAR-USD"]["totale"] == 3
    assert sorted(r["NEAR-USD"]["da_togliere"]) == [1, 3]


def test_un_simbolo_fuori_elenco_non_viene_giudicato():
    """
    ADIL e BB sono stati scritti a mano il 17 agosto 2026 e non hanno un
    termine di ricerca noto. Senza quello non si puo' dire se la riga sia
    pertinente, e cancellare a caso e' peggio che lasciare dentro un dubbio.
    """
    righe = [(1, "ADIL", "Adial Pharmaceuticals announces something"),
             (2, "BB", "BlackBerry reports quarterly results")]
    assert bp.esamina(righe) == {}


def test_un_titolo_che_non_nomina_l_azienda_viene_contato():
    righe = [(1, "NVDA", "Nvidia shares rise after earnings beat"),
             (2, "NVDA", "AMD launches new graphics card")]
    r = bp.esamina(righe)
    assert r["NVDA"]["da_togliere"] == [2]


def test_sui_nomi_netti_non_conta_quello_che_il_filtro_non_toglie():
    """
    Il conto deve rispecchiare il filtro vero, non uno piu' severo: se
    proponesse di cancellare righe che oggi entrerebbero comunque, il numero
    che si guarda prima di cancellare sarebbe gonfio.
    """
    righe = [(1, "NVDA", "Nvidia unveils new Blackwell chip at GTC")]
    assert bp.esamina(righe)["NVDA"]["da_togliere"] == []


def test_tiene_solo_tre_esempi_per_titolo():
    righe = [(i, "NEAR-USD", f"Fire near place number {i}") for i in range(10)]
    r = bp.esamina(righe)
    assert len(r["NEAR-USD"]["da_togliere"]) == 10
    assert len(r["NEAR-USD"]["esempi"]) == bp.ESEMPI


def test_un_titolo_vuoto_non_fa_esplodere_niente():
    bp.esamina([(1, "NEAR-USD", None), (2, "NEAR-USD", "")])


# ── La parte che conta: non cancella se non glielo chiedi ─────────────────
def test_senza_elimina_non_tocca_il_database(capsys):
    righe = [(1, "NEAR-USD", SPAZZATURA), (2, "NEAR-USD", BUONA)]
    with patch("bonifica_pertinenza._righe", return_value=righe), \
         patch("bonifica_pertinenza._elimina") as cancella:
        assert bp.main() == 0
    assert not cancella.called, "ha cancellato senza che nessuno glielo chiedesse"
    testo = capsys.readouterr().out
    assert "Non e' stata cancellata nessuna riga" in testo
    assert "--elimina" in testo


def test_con_elimina_cancella_solo_quelle_contate(capsys):
    righe = [(1, "NEAR-USD", SPAZZATURA), (2, "NEAR-USD", BUONA),
             (3, "NEAR-USD", "Crash on I - 80 east slows traffic near Wells Avenue")]
    with patch("bonifica_pertinenza._righe", return_value=righe), \
         patch("bonifica_pertinenza._elimina", return_value=2) as cancella:
        assert bp.main(elimina=True) == 0
    (ids,), _ = cancella.call_args
    assert sorted(ids) == [1, 3], "la riga buona non deve finire nell'elenco"


def test_il_conto_delle_non_giudicabili_viene_detto(capsys):
    righe = [(1, "NEAR-USD", SPAZZATURA), (2, "ADIL", "Qualcosa su Adial")]
    with patch("bonifica_pertinenza._righe", return_value=righe), \
         patch("bonifica_pertinenza._elimina"):
        bp.main()
    assert "non giudicabili" in capsys.readouterr().out


def test_niente_da_cancellare_non_e_un_errore(capsys):
    with patch("bonifica_pertinenza._righe", return_value=[(1, "NEAR-USD", BUONA)]), \
         patch("bonifica_pertinenza._elimina") as cancella:
        assert bp.main(elimina=True) == 0
    assert not cancella.called
    assert "Niente da cancellare" in capsys.readouterr().out
