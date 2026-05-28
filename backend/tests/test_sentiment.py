"""
test_sentiment.py — Test per la funzione VADER vader_sentiment().
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from quick_fetch import vader_sentiment


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
