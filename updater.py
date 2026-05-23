"""
updater.py
----------
Script autonomo per l'aggiornamento automatico del database news.
Va eseguito dal Windows Task Scheduler, indipendentemente da Streamlit.

Configurazione Task Scheduler:
  Programma : C:\Users\<utente>\AppData\Local\Programs\Python\Python311\python.exe
  Argomenti : updater.py
  Cartella  : C:\Users\<utente>\OneDrive\Desktop\Sentiment Analysis\Script
  Trigger   : ogni 6 ore (o come preferisci)
"""

import sys
import logging
from pathlib import Path
from datetime import datetime

# --- Path setup: assicura che i moduli del progetto siano importabili ---
ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT))

# --- Logging su file ---
LOG_PATH = ROOT / "data" / "updater.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)

# --- Ticker da aggiornare automaticamente ---
TICKERS = [
    "NVDA",
    "AAPL",
    "TSLA",
    "MSFT",
    "GOOGL",
]

# --- Legge le API key dal file secrets.toml (stesso usato da Streamlit) ---
def load_api_keys():
    """
    Prova a leggere da .streamlit/secrets.toml locale o globale.
    Fallback: variabili d'ambiente.
    """
    import os

    # Cerca prima nel progetto, poi nella home utente
    candidates = [
        ROOT / ".streamlit" / "secrets.toml",
        Path.home() / ".streamlit" / "secrets.toml",
    ]

    for path in candidates:
        if path.exists():
            try:
                import tomllib  # Python 3.11+
            except ImportError:
                try:
                    import tomli as tomllib  # pip install tomli
                except ImportError:
                    log.warning("tomllib non disponibile, uso variabili d'ambiente")
                    break

            with open(path, "rb") as f:
                secrets = tomllib.load(f)
            log.info(f"API key caricate da {path}")
            return {
                'ALPHA_VANTAGE': secrets.get('ALPHA_VANTAGE', ''),
                'NEWSAPI':       secrets.get('NEWSAPI', ''),
                'FMP':           secrets.get('FMP', ''),
            }

    # Fallback: variabili d'ambiente
    log.warning("secrets.toml non trovato, uso variabili d'ambiente")
    return {
        'ALPHA_VANTAGE': os.getenv('ALPHA_VANTAGE', ''),
        'NEWSAPI':       os.getenv('NEWSAPI', ''),
        'FMP':           os.getenv('FMP', ''),
    }


def main():
    log.info("=" * 60)
    log.info(f"Avvio aggiornamento automatico – {datetime.now():%d/%m/%Y %H:%M}")
    log.info("=" * 60)

    api_key = load_api_keys()

    from data.database import SuperNewsAnalyzer

    totale = 0
    for ticker in TICKERS:
        try:
            analyzer = SuperNewsAnalyzer(ticker, api_key)
            count = analyzer.mega_fetch_silent()
            totale += count
        except Exception as e:
            log.error(f"{ticker}: errore imprevisto – {e}")

    log.info(f"Aggiornamento completato. Totale nuove news: {totale}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()