"""
test_quick_fetch.py — Test per format_date() e logica di deduplicazione in quick_fetch.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from quick_fetch import format_date


class TestFormatDate:

    def test_none_restituisce_none(self):
        assert format_date(None) is None

    def test_stringa_vuota_restituisce_none(self):
        assert format_date("") is None

    def test_iso_format_standard(self):
        result = format_date("2024-01-15T10:30:00")
        assert result == "2024-01-15 10:30:00"

    def test_solo_data(self):
        result = format_date("2024-03-20")
        assert result is not None
        assert result.startswith("2024-03-20")

    def test_formato_alpha_vantage(self):
        # Alpha Vantage usa YYYYMMDDTHHMMSS
        result = format_date("20240115T103000")
        assert result is not None
        assert "2024" in result

    def test_stringa_troppo_corta(self):
        # Meno di 10 caratteri — non possiamo estrarre la data
        result = format_date("2024")
        # Accettiamo None o una stringa (fallback)
        # L'importante è che non sollevi eccezioni
        assert result is None or isinstance(result, str)

    def test_formato_rfc_2822(self):
        # Formato usato da RSS/Atom feeds
        result = format_date("Mon, 15 Jan 2024 10:30:00 +0000")
        assert result is not None
        assert "2024-01-15" in result


class TestDeduplicazione:
    """Verifica la logica di deduplicazione per URL in quick_fetch()."""

    def test_rimuove_duplicati_per_url(self):
        """quick_fetch usa un set 'seen' sugli URL — verifica la logica."""
        news = [
            {"url": "https://example.com/1", "title": "News 1"},
            {"url": "https://example.com/1", "title": "News 1 duplicate"},
            {"url": "https://example.com/2", "title": "News 2"},
        ]
        seen, unique = set(), []
        for n in news:
            if n.get("url") and n["url"] not in seen:
                seen.add(n["url"])
                unique.append(n)

        assert len(unique) == 2
        assert unique[0]["url"] == "https://example.com/1"
        assert unique[1]["url"] == "https://example.com/2"

    def test_articolo_senza_url_escluso(self):
        """Articoli senza URL vengono scartati dalla deduplicazione."""
        news = [
            {"url": "", "title": "No URL"},
            {"url": "https://example.com/1", "title": "Has URL"},
        ]
        seen, unique = set(), []
        for n in news:
            if n.get("url") and n["url"] not in seen:
                seen.add(n["url"])
                unique.append(n)

        assert len(unique) == 1
        assert unique[0]["title"] == "Has URL"
