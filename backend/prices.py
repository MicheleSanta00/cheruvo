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


def get_prices(ticker: str, period: str = "3mo") -> pd.DataFrame:
    df = _yahoo_chart(ticker, period)
    if not df.empty:
        return df
    logger.warning("Yahoo Chart fallito per %s, provo Alpha Vantage...", ticker)
    return _alpha_vantage_daily(ticker, period)


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