"""
test_sentiment_groq.py — Robustezza dello scoring LLM.

Invariante chiave: se Groq fallisce, NON si scrive nulla (niente zeri
al posto degli score VADER). score_batch → None su fallimento totale,
None per i singoli score non validi.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("DATABASE_URL", "postgresql://fake:fake@localhost/fake")
os.environ.setdefault("GROQ_API_KEY", "gsk_fake_key_for_tests")

from unittest.mock import MagicMock, patch

import sentiment_groq
from sentiment_groq import score_batch
from quick_fetch import _llm_refine

ARTICLES = [{"title": "Company beats earnings", "summary": "record profit"},
            {"title": "CEO resigns amid probe", "summary": ""}]


def _mock_groq(content: str):
    client = MagicMock()
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    client.chat.completions.create.return_value = resp
    return client


class TestScoreBatch:

    def test_risposta_oggetto_scores(self):
        with patch("sentiment_groq._get_groq", return_value=_mock_groq('{"scores": [0.6, -0.45]}')):
            assert score_batch(ARTICLES) == [0.6, -0.45]

    def test_risposta_lista_nuda(self):
        with patch("sentiment_groq._get_groq", return_value=_mock_groq('[0.2, 0.3]')):
            assert score_batch(ARTICLES) == [0.2, 0.3]

    def test_clamp_fuori_range(self):
        with patch("sentiment_groq._get_groq", return_value=_mock_groq('{"scores": [5, -3]}')):
            assert score_batch(ARTICLES) == [1.0, -1.0]

    def test_json_rotto_ritorna_none(self):
        with patch("sentiment_groq._get_groq", return_value=_mock_groq('non sono json')):
            assert score_batch(ARTICLES) is None

    def test_eccezione_api_ritorna_none(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("model decommissioned")
        with patch("sentiment_groq._get_groq", return_value=client):
            assert score_batch(ARTICLES) is None

    def test_score_singolo_invalido_diventa_none(self):
        with patch("sentiment_groq._get_groq", return_value=_mock_groq('{"scores": [0.5, "boh"]}')):
            assert score_batch(ARTICLES) == [0.5, None]

    def test_lista_nuda_incompleta_scarta_il_batch(self):
        """
        Lista senza indici e più corta del previsto: NON si può sapere quale
        articolo il modello abbia saltato. Prima si riempiva col padding in
        coda, il che assegnava i punteggi agli articoli sbagliati in silenzio.
        Ora l'intero batch viene scartato: meglio nessun punteggio che uno finto.
        """
        with patch("sentiment_groq._get_groq", return_value=_mock_groq('{"scores": [0.5]}')):
            assert score_batch(ARTICLES) is None


class TestMappaturaPerIndice:
    """
    Il modello rimanda il numero dell'articolo con ogni punteggio, così un
    elemento saltato non fa scalare tutti gli altri.
    """

    def test_indici_espliciti(self):
        r = '{"scores": [{"n": 1, "s": 0.6}, {"n": 2, "s": -0.45}]}'
        with patch("sentiment_groq._get_groq", return_value=_mock_groq(r)):
            assert score_batch(ARTICLES) == [0.6, -0.45]

    def test_articolo_saltato_non_sposta_gli_altri(self):
        """Il bug storico: manca il n.1, il punteggio del n.2 resta sul n.2."""
        r = '{"scores": [{"n": 2, "s": -0.45}]}'
        with patch("sentiment_groq._get_groq", return_value=_mock_groq(r)):
            assert score_batch(ARTICLES) == [None, -0.45]

    def test_ordine_sparso(self):
        r = '{"scores": [{"n": 2, "s": -0.45}, {"n": 1, "s": 0.6}]}'
        with patch("sentiment_groq._get_groq", return_value=_mock_groq(r)):
            assert score_batch(ARTICLES) == [0.6, -0.45]

    def test_indice_fuori_range_ignorato(self):
        r = '{"scores": [{"n": 1, "s": 0.6}, {"n": 99, "s": 0.9}]}'
        with patch("sentiment_groq._get_groq", return_value=_mock_groq(r)):
            assert score_batch(ARTICLES) == [0.6, None]

    def test_titoli_gdelt_ripuliti(self):
        """GDELT spezza la punteggiatura: va normalizzata prima del modello."""
        client = _mock_groq('{"scores": [{"n": 1, "s": 0.1}]}')
        with patch("sentiment_groq._get_groq", return_value=client):
            score_batch([{"title": "Netflix , Inc . Shares Up 1 . 6 %", "summary": ""}])
        inviato = client.chat.completions.create.call_args[1]["messages"][0]["content"]
        assert "Netflix, Inc. Shares Up 1.6%" in inviato

    def test_scoring_deterministico(self):
        """temperature deve essere 0: stessa notizia, stesso punteggio."""
        client = _mock_groq('{"scores": [{"n": 1, "s": 0.1}, {"n": 2, "s": 0.2}]}')
        with patch("sentiment_groq._get_groq", return_value=client):
            score_batch(ARTICLES)
        assert client.chat.completions.create.call_args[1]["temperature"] == 0

    def test_batch_vuoto(self):
        assert score_batch([]) == []


class TestRescoreNonSovrascrive:

    def test_batch_fallito_non_scrive_nel_db(self):
        """Groq giù → nessun UPDATE, gli score VADER restano."""
        pool = MagicMock(); conn = MagicMock(); cur = MagicMock()
        conn.cursor.return_value = cur
        cur.fetchall.return_value = [(1, "titolo a", ""), (2, "titolo b", "")]
        pool.getconn.return_value = conn
        with patch("sentiment_groq.get_pool", return_value=pool), \
             patch("sentiment_groq.score_batch", return_value=None), \
             patch("psycopg2.extras.execute_values") as ev:
            updated = sentiment_groq.rescore_non_av_news("NVDA")
        assert updated == 0
        ev.assert_not_called()

    def test_aggiorna_solo_score_validi(self):
        pool = MagicMock(); conn = MagicMock(); cur = MagicMock()
        conn.cursor.return_value = cur
        cur.fetchall.return_value = [(1, "a", ""), (2, "b", "")]
        pool.getconn.return_value = conn
        with patch("sentiment_groq.get_pool", return_value=pool), \
             patch("sentiment_groq.score_batch", return_value=[0.7, None]), \
             patch("psycopg2.extras.execute_values") as ev:
            updated = sentiment_groq.rescore_non_av_news("NVDA")
        assert updated == 1
        args = ev.call_args[0]
        assert args[2] == [(1, 0.7)]   # solo la coppia valida


class TestLlmRefineOnDemand:

    def test_groq_giu_conserva_vader(self):
        news = [{"source": "Google News", "title": "t", "summary": "", "sentiment": 0.31}]
        with patch("sentiment_groq.score_batch", return_value=None):
            n = _llm_refine(news)
        assert n == 0
        assert news[0]["sentiment"] == 0.31
        assert news[0].get("score_source", "vader") == "vader"

    def test_raffina_gli_score_validi(self):
        news = [
            {"source": "Google News", "title": "a", "summary": "", "sentiment": 0.0},
            {"source": "Google News", "title": "b", "summary": "", "sentiment": 0.1},
            {"source": "Alpha Vantage", "title": "c", "summary": "", "sentiment": 0.5},
        ]
        with patch("sentiment_groq.score_batch", return_value=[0.62, None]):
            n = _llm_refine(news)
        assert n == 1
        # 'llm2' = versione con mappatura per indice; le vecchie 'llm' vanno ripassate
        assert news[0]["sentiment"] == 0.62 and news[0]["score_source"] == "llm2"
        assert news[1]["sentiment"] == 0.1                      # None → resta VADER
        assert news[2]["sentiment"] == 0.5                      # AV mai toccato

    def test_senza_api_key_non_fa_nulla(self):
        news = [{"source": "Google News", "title": "t", "summary": "", "sentiment": 0.2}]
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            assert _llm_refine(news) == 0
        assert news[0]["sentiment"] == 0.2
