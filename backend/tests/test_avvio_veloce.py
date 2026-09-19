"""
L'avvio non deve aspettare le creazioni di tabella.

Misurato il 18 settembre 2026. Render dichiara circa sessanta secondi per
riaccendere un servizio gratuito spento; aprendo il sito se ne aspettavano
due o tre. Una parte era `lifespan`, che eseguiva in fila cinque funzioni di
inizializzazione (una trentina fra CREATE TABLE, CREATE INDEX e ALTER TABLE,
ognuna con la sua connessione) prima di lasciar servire la prima richiesta.

E' lo stesso difetto scritto in cima a visite.py, un livello piu' su: la',
DDL dentro ogni richiesta; qui, DDL dentro ogni avvio.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("DATABASE_URL", "postgresql://fake:fake@localhost/fake")

import inspect


def test_lifespan_non_chiama_le_init_prima_di_servire():
    import main
    sorgente = inspect.getsource(main.lifespan)
    prima_dello_yield = sorgente.split("yield")[0]
    for nome in ("init_database", "init_subscriptions_table",
                 "init_onboarding_table", "init_digest_tables",
                 "init_earnings_tables"):
        assert f"{nome}()" not in prima_dello_yield, (
            f"{nome} e' tornata sulla strada del primo visitatore")


def test_le_init_vengono_comunque_eseguite():
    """Spostarle in sottofondo non vuol dire toglierle."""
    import main
    sorgente = inspect.getsource(main._prepara_tabelle)
    for nome in ("init_database", "init_subscriptions_table",
                 "init_onboarding_table", "init_digest_tables",
                 "init_earnings_tables"):
        assert nome in sorgente, f"{nome} non viene piu' eseguita affatto"


def test_un_errore_di_una_init_non_ferma_le_altre_e_si_vede_nel_log():
    """
    In sottofondo nessuno guarda il risultato: se una fallisce in silenzio,
    la tabella non c'e' e non lo sa nessuno.
    """
    import main
    sorgente = inspect.getsource(main._prepara_tabelle)
    assert "logger.error" in sorgente
    assert "except Exception" in sorgente


def test_il_pool_invece_resta_prima_dello_yield():
    """
    Quello serve davvero subito: e' una connessione sola, e senza di lui la
    prima richiesta se la creerebbe comunque pagandola per intera.
    """
    import main
    prima_dello_yield = inspect.getsource(main.lifespan).split("yield")[0]
    assert "get_pool()" in prima_dello_yield
