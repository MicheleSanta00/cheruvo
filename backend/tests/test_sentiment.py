"""
test_sentiment.py — Test per la funzione VADER vader_sentiment().
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from quick_fetch import vader_sentiment, _av_sentiment


class TestVaderSentiment:

    def test_stringa_vuota_restituisce_zero(self):
        assert vader_sentiment("") == 0.0

    def test_none_restituisce_zero(self):
        assert vader_sentiment(None) == 0.0

    def test_testo_positivo(self):
        score = vader_sentiment("The company reported record profits and outstanding growth!")
        assert score > 0.2, f"Atteso > 0.2, ottenuto {score}"

    def test_testo_negativo(self):
        score = vader_sentiment("The company collapsed, massive losses, terrible results")
        assert score < -0.2, f"Atteso < -0.2, ottenuto {score}"

    def test_testo_neutro(self):
        score = vader_sentiment("The company released its quarterly report today.")
        assert -0.3 < score < 0.3, f"Atteso vicino a 0, ottenuto {score}"

    def test_output_nel_range(self):
        for text in [
            "BUY BUY BUY amazing incredible best ever!!!",
            "CRASH DISASTER FRAUD BANKRUPT terrible horrible",
            "quarterly earnings report fiscal year",
        ]:
            score = vader_sentiment(text)
            assert -1.0 <= score <= 1.0, f"Score fuori range per: {text!r}"

    def test_output_arrotondato_a_4_decimali(self):
        score = vader_sentiment("Stocks are up today")
        # float con al massimo 4 decimali
        assert score == round(score, 4)


class TestAvSentiment:

    def test_usa_ticker_sentiment_specifico(self):
        """Priorità 1: score specifico per il ticker nella lista ticker_sentiment."""
        item = {
            "title": "Market news",
            "summary": "",
            "overall_sentiment_score": "0.1",
            "ticker_sentiment": [
                {"ticker": "AAPL", "ticker_sentiment_score": "0.45"},
                {"ticker": "MSFT", "ticker_sentiment_score": "-0.3"},
            ],
        }
        assert _av_sentiment(item, "AAPL") == 0.45
        assert _av_sentiment(item, "MSFT") == -0.3

    def test_usa_overall_se_ticker_non_presente(self):
        """Priorità 2: overall score quando il ticker non è in ticker_sentiment."""
        item = {
            "title": "Market news",
            "summary": "",
            "overall_sentiment_score": "0.25",
            "ticker_sentiment": [{"ticker": "GOOGL", "ticker_sentiment_score": "0.1"}],
        }
        assert _av_sentiment(item, "AAPL") == 0.25

    def test_fallback_vader_se_no_score(self):
        """Priorità 3: VADER sul testo se mancano entrambi gli score AV."""
        item = {
            "title": "Stocks crash dramatically on terrible earnings",
            "summary": "",
            "ticker_sentiment": [],
        }
        score = _av_sentiment(item, "AAPL")
        assert score < 0, f"Atteso negativo da VADER, ottenuto {score}"

    def test_score_sempre_nel_range(self):
        """Anche score fuori range da AV vengono clampati a [-1, 1]."""
        item = {
            "overall_sentiment_score": "1.5",  # valore anomalo
            "ticker_sentiment": [],
        }
        score = _av_sentiment(item, "AAPL")
        assert -1.0 <= score <= 1.0

    def test_ticker_case_insensitive(self):
        """Il confronto ticker è case-insensitive."""
        item = {
            "overall_sentiment_score": "0.0",
            "ticker_sentiment": [{"ticker": "aapl", "ticker_sentiment_score": "0.5"}],
        }
        assert _av_sentiment(item, "AAPL") == 0.5
