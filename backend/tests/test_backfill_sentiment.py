"""
Il ripasso notturno con Groq (backfill_sentiment.py, nella radice).

Tre difetti chiusi il 24 settembre 2026, scritti per esteso in cima al file:
il tono GDELT veniva perso per sempre, le righe regolatorie perdevano il
marchio della licenza, e una riga senza punteggio faceva girare il giro a
vuoto fino al tempo massimo.
"""
import os
import sys
from unittest.mock import MagicMock, patch

RADICE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RADICE)
sys.path.insert(0, os.path.join(RADICE, "backend"))
os.environ.setdefault("DATABASE_URL", "postgresql://fake:fake@localhost/fake")
os.environ.setdefault("GROQ_API_KEY", "gsk_fake_key_for_tests")

import backfill_sentiment as bf  # noqa: E402


def _pool():
    pool, conn, cur = MagicMock(), MagicMock(), MagicMock()
    pool.getconn.return_value = conn
    conn.cursor.return_value = cur
    return pool, cur


def test_il_tono_gdelt_si_mette_da_parte_prima_di_scriverci_sopra():
    pool, cur = _pool()
    with patch("backfill_sentiment.get_pool", return_value=pool), \
         patch("psycopg2.extras.execute_values") as ev:
        bf._apply([(1, 0.3)])
    sql = ev.call_args[0][1]
    # In un UPDATE Postgres calcola TUTTE le espressioni sui valori vecchi
    # della riga: tono_gdelt riceve il tono di prima anche se `sentiment`
    # viene riscritto nella stessa istruzione.
    assert "tono_gdelt = CASE WHEN news.score_source = 'gdelt'" in sql
    assert "THEN news.sentiment" in sql


def test_le_righe_regolatorie_tengono_il_marchio():
    pool, cur = _pool()
    with patch("backfill_sentiment.get_pool", return_value=pool), \
         patch("psycopg2.extras.execute_values") as ev:
        bf._apply([(1, 0.3)])
    assert "istituzionale_llm2" in ev.call_args[0][1]


def test_una_riga_senza_punteggio_non_torna_a_ogni_lotto():
    """
    Prima: la riga piu' recente senza punteggio veniva richiesta a ogni
    giro, e con un lotto intero cosi' il programma consumava quota Groq per
    cinquanta minuti senza avanzare.
    """
    richieste = []

    def finto_fetch(limit, saltare=()):
        richieste.append(set(saltare))
        if len(richieste) == 1:
            return [(1, "a", ""), (2, "b", "")]
        return []          # al secondo giro non resta niente di nuovo

    with patch("backfill_sentiment.init_database"), \
         patch("backfill_sentiment._count_remaining", return_value=2), \
         patch("backfill_sentiment._fetch_chunk", side_effect=finto_fetch), \
         patch("backfill_sentiment.score_batch", return_value=[None, 0.4]), \
         patch("backfill_sentiment._apply", return_value=1), \
         patch("backfill_sentiment.time.sleep"):
        bf.main()
    assert richieste[1] == {1}, "la riga 1 senza punteggio va saltata nel giro dopo"


def test_la_selezione_non_riprende_le_righe_gia_fatte():
    pool, cur = _pool()
    cur.fetchall.return_value = []
    with patch("backfill_sentiment.get_pool", return_value=pool):
        bf._fetch_chunk(15, {7})
    sql, parametri = cur.execute.call_args[0]
    assert "<> ALL(%s)" in sql and "NOT (id = ANY(%s))" in sql
    assert "istituzionale_llm2" in parametri[0]
    assert parametri[1] == [7]
