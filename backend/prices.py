"""prices.py — usa Yahoo Finance v8 API direttamente senza yfinance."""
import os
import logging
import requests
import pandas as pd
from datetime import datetime, timedelta
import time

logger = logging.getLogger(__name__)


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://finance.yahoo.com/",
}

PERIOD_DAYS = {
    "1mo":  30,
    "3mo":  90,
    "6mo":  180,
    "1y":   365,
    "2y":   730,
    "5y":   1825,
}

# Periodi INTRADAY: un punto al minuto invece che al giorno.
# Servono alla vista "Oggi", quella che si compone sotto gli occhi mentre la
# borsa è aperta. Yahoo per questi vuole "range" invece di period1/period2.
INTRADAY = {
    "1d": "1m",     # oggi, minuto per minuto (circa 390 punti per una seduta USA)
    "5d": "5m",     # ultima settimana, a passi di 5 minuti
}


def e_intraday(period: str) -> bool:
    return period in INTRADAY


def e_crypto(ticker: str) -> bool:
    """Le crypto su Yahoo hanno il suffisso -USD (BTC-USD, ETH-USD)."""
    return (ticker or "").upper().endswith("-USD")


def get_prices(ticker: str, period: str = "3mo") -> pd.DataFrame:
    if e_intraday(period):
        # Nessun ripiego su Alpha Vantage: il loro piano gratuito non dà
        # l'intraday, quindi se Yahoo non risponde non c'è un piano B.
        return _yahoo_intraday(ticker, period)
    df = _yahoo_chart(ticker, period)
    if not df.empty:
        return df
    logger.warning("Yahoo Chart fallito per %s, provo Alpha Vantage...", ticker)
    return _alpha_vantage_daily(ticker, period)


def stato_mercato(ticker: str) -> dict:
    """
    Se la borsa di quel titolo è aperta adesso, e quando è avvenuto l'ultimo
    scambio. Serve a due cose: non interrogare Yahoo di notte e nel fine
    settimana, e scrivere accanto al prezzo l'ora vera invece di far credere
    all'utente che sia il secondo esatto in cui sta guardando.
    """
    try:
        r = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
            headers=HEADERS, params={"interval": "1d", "range": "1d"}, timeout=10,
        )
        meta = (r.json().get("chart", {}).get("result") or [{}])[0].get("meta", {})
        regolare = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
        adesso = int(time.time())
        crypto = e_crypto(ticker)

        riferimento = meta.get("chartPreviousClose") or meta.get("previousClose")
        tipo_riferimento = "chiusura_precedente"

        # Sulle crypto la "chiusura di ieri" non esiste: il mercato non chiude
        # mai, e quel numero è semplicemente il prezzo a mezzanotte UTC. Alle
        # otto di sera sarebbe un confronto su venti ore spacciato per un
        # giorno. Chi segue le crypto ragiona in variazione a 24 ore vere, e
        # quella la calcoliamo su una finestra mobile.
        if crypto:
            vero = _prezzo_24h_fa(ticker)
            if vero is not None:
                riferimento = vero
                tipo_riferimento = "24h"

        return {
            # Le crypto scambiano sempre: nessun orario da controllare.
            "aperto": True if crypto else
                      bool(regolare.get("start", 0) <= adesso <= regolare.get("end", 0)),
            "sempre_aperto": crypto,
            "ultimo_scambio": meta.get("regularMarketTime"),
            "prezzo": meta.get("regularMarketPrice"),
            "chiusura_precedente": riferimento,
            "tipo_riferimento": tipo_riferimento,
            "valuta": meta.get("currency"),
            "borsa": meta.get("fullExchangeName"),
        }
    except Exception as e:
        logger.warning("stato_mercato %s: %s", ticker, e)
        return {"aperto": False, "sempre_aperto": False, "ultimo_scambio": None,
                "prezzo": None, "chiusura_precedente": None,
                "tipo_riferimento": None, "valuta": None, "borsa": None}


def _prezzo_24h_fa(ticker: str) -> float | None:
    """
    Prezzo di 24 ore fa esatte, preso dalla serie oraria degli ultimi 2 giorni.
    Ritorna None se non si riesce: chi chiama ripiega sulla chiusura Yahoo.
    """
    try:
        r = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
            headers=HEADERS, params={"interval": "1h", "range": "2d"}, timeout=12,
        )
        res = (r.json().get("chart", {}).get("result") or [{}])[0]
        momenti = res.get("timestamp") or []
        chiusure = (res.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
        if not momenti or not chiusure:
            return None

        bersaglio = time.time() - 86400
        migliore, distanza = None, None
        for i, ts in enumerate(momenti):
            if i >= len(chiusure) or chiusure[i] is None:
                continue
            d = abs(ts - bersaglio)
            if distanza is None or d < distanza:
                migliore, distanza = chiusure[i], d
        # Se il punto più vicino dista più di tre ore dal bersaglio la serie ha
        # buchi grossi e il confronto sarebbe fuorviante: meglio non darlo.
        return migliore if distanza is not None and distanza <= 3 * 3600 else None
    except Exception as e:
        logger.warning("prezzo 24h fa per %s: %s", ticker, e)
        return None


def _yahoo_intraday(ticker: str, period: str) -> pd.DataFrame:
    """Serie a passo di minuti. Indice datetime completo, non solo la data."""
    intervallo = INTRADAY.get(period, "1m")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"

    for tentativo in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15,
                             params={"range": period, "interval": intervallo})
            if r.status_code == 429:
                time.sleep(2)
                continue
            r.raise_for_status()
            risultato = (r.json().get("chart", {}).get("result") or [])
            if not risultato:
                return pd.DataFrame()

            res = risultato[0]
            momenti = res.get("timestamp", []) or []
            q = (res.get("indicators", {}).get("quote") or [{}])[0]
            chiusure = q.get("close", []) or []

            righe = []
            for i, ts in enumerate(momenti):
                if i >= len(chiusure) or chiusure[i] is None:
                    continue   # minuti senza scambi: si saltano, non si azzerano
                righe.append({
                    "date":   datetime.utcfromtimestamp(ts),
                    "Open":   (q.get("open")   or [None])[i] if i < len(q.get("open", []))   else None,
                    "High":   (q.get("high")   or [None])[i] if i < len(q.get("high", []))   else None,
                    "Low":    (q.get("low")    or [None])[i] if i < len(q.get("low", []))    else None,
                    "Close":  chiusure[i],
                    "Volume": (q.get("volume") or [0])[i]    if i < len(q.get("volume", [])) else 0,
                })

            if not righe:
                return pd.DataFrame()
            df = pd.DataFrame(righe).set_index("date").sort_index()
            logger.info("Yahoo intraday: %d punti (%s) per %s", len(df), intervallo, ticker)
            return df

        except Exception as e:
            logger.warning("Yahoo intraday tentativo %d per %s: %s", tentativo + 1, ticker, e)
            time.sleep(1)

    return pd.DataFrame()


def _yahoo_chart(ticker: str, period: str) -> pd.DataFrame:
    days  = PERIOD_DAYS.get(period, 90)
    end   = int(datetime.now().timestamp())
    start = int((datetime.now() - timedelta(days=days)).timestamp())

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {
        "period1":  start,
        "period2":  end,
        "interval": "1d",
        "events":   "history",
    }

    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=15)
            if r.status_code == 429:
                time.sleep(2)
                continue
            r.raise_for_status()
            data = r.json()

            result = data.get("chart", {}).get("result", [])
            if not result:
                return pd.DataFrame()

            res        = result[0]
            timestamps = res.get("timestamp", [])
            indicators = res.get("indicators", {}).get("quote", [{}])[0]

            opens   = indicators.get("open",   [])
            highs   = indicators.get("high",   [])
            lows    = indicators.get("low",    [])
            closes  = indicators.get("close",  [])
            volumes = indicators.get("volume", [])

            rows = []
            for i, ts in enumerate(timestamps):
                if i >= len(closes) or closes[i] is None:
                    continue
                rows.append({
                    "date":   datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d"),
                    "Open":   opens[i]   or 0,
                    "High":   highs[i]   or 0,
                    "Low":    lows[i]    or 0,
                    "Close":  closes[i]  or 0,
                    "Volume": volumes[i] or 0,
                })

            if not rows:
                return pd.DataFrame()

            df = pd.DataFrame(rows)
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            logger.info("Yahoo Chart: %d giorni per %s", len(df), ticker)
            return df

        except Exception as e:
            logger.warning("Yahoo Chart attempt %d: %s", attempt + 1, e)
            time.sleep(1)

    return pd.DataFrame()


def _alpha_vantage_daily(ticker: str, period: str) -> pd.DataFrame:
    try:
        api_key = os.environ.get("ALPHA_VANTAGE", "")
        if not api_key:
            return pd.DataFrame()

        outputsize = "full" if period in {"6mo", "1y", "2y", "5y"} else "compact"
        r = requests.get(
            "https://www.alphavantage.co/query",
            params={
                "function":   "TIME_SERIES_DAILY",
                "symbol":     ticker,
                "outputsize": outputsize,
                "apikey":     api_key,
            },
            timeout=15,
        )
        data = r.json()
        if "Time Series (Daily)" not in data:
            return pd.DataFrame()

        ts = data["Time Series (Daily)"]
        rows = []
        cutoff = datetime.now() - timedelta(days=PERIOD_DAYS.get(period, 90))
        for date_str, values in ts.items():
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            if dt < cutoff:
                continue
            rows.append({
                "date":   dt,
                "Open":   float(values["1. open"]),
                "High":   float(values["2. high"]),
                "Low":    float(values["3. low"]),
                "Close":  float(values["4. close"]),
                "Volume": float(values["5. volume"]),
            })

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df = df.set_index("date").sort_index()
        logger.info("Alpha Vantage: %d giorni per %s", len(df), ticker)
        return df

    except Exception as e:
        logger.error("Alpha Vantage error: %s", e)
        return pd.DataFrame()


def validate_ticker(ticker: str) -> dict:
    try:
        r = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
            headers=HEADERS,
            params={"interval": "1d", "range": "5d"},
            timeout=10,
        )
        data = r.json()
        result = data.get("chart", {}).get("result", [])
        if result:
            meta = result[0].get("meta", {})
            return {
                "valid":      True,
                "ticker":     ticker.upper(),
                "nome":       meta.get("longName") or meta.get("shortName") or ticker.upper(),
                "settore":    "N/A",
                "prezzo":     meta.get("regularMarketPrice"),
                "variazione": meta.get("regularMarketChangePercent"),
            }
    except Exception as e:
        logger.error("validate_ticker error per %s: %s", ticker, e)

    # Ticker non trovato su Yahoo Finance
    return {
        "valid":      False,
        "ticker":     ticker.upper(),
        "nome":       ticker.upper(),
        "settore":    "N/A",
        "prezzo":     None,
        "variazione": None,
    }