"""prices.py — usa Alpha Vantage se yFinance è bloccato."""
import os
import requests
import pandas as pd
from datetime import datetime, timedelta


def get_prices(ticker: str, period: str = "3mo") -> pd.DataFrame:
    """Prova yFinance, se fallisce usa Alpha Vantage."""
    df = _try_yfinance(ticker, period)
    if not df.empty:
        return df
    print(f"yFinance bloccato per {ticker}, provo Alpha Vantage...")
    return _try_alpha_vantage(ticker, period)


def _try_yfinance(ticker: str, period: str) -> pd.DataFrame:
    import time
    try:
        import yfinance as yf
        for attempt in range(2):
            try:
                df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.droplevel(1)
                if not df.empty:
                    df.index = pd.to_datetime(df.index).tz_localize(None)
                    return df[["Open", "High", "Low", "Close", "Volume"]]
                time.sleep(1)
            except Exception as e:
                print(f"yFinance attempt {attempt+1}: {e}")
                time.sleep(1)
    except Exception:
        pass
    return pd.DataFrame()


def _try_alpha_vantage(ticker: str, period: str) -> pd.DataFrame:
    try:
        api_key = os.environ.get("ALPHA_VANTAGE", "")
        if not api_key:
            return pd.DataFrame()

        # Determina outputsize in base al periodo
        long_periods = {"6mo", "1y", "2y", "5y"}
        outputsize = "full" if period in long_periods else "compact"

        r = requests.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "TIME_SERIES_DAILY_ADJUSTED",
                "symbol": ticker,
                "outputsize": outputsize,
                "apikey": api_key,
            },
            timeout=15,
        )
        data = r.json()

        if "Time Series (Daily)" not in data:
            print(f"Alpha Vantage prezzi: {data.get('Note') or data.get('Information') or 'nessun dato'}")
            return pd.DataFrame()

        ts = data["Time Series (Daily)"]
        rows = []
        for date_str, values in ts.items():
            rows.append({
                "date": date_str,
                "Open":   float(values["1. open"]),
                "High":   float(values["2. high"]),
                "Low":    float(values["3. low"]),
                "Close":  float(values["5. adjusted close"]),
                "Volume": float(values["6. volume"]),
            })

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()

        # Filtra per periodo
        cutoff = _period_to_date(period)
        df = df[df.index >= cutoff]

        print(f"Alpha Vantage prezzi: {len(df)} giorni per {ticker}")
        return df

    except Exception as e:
        print(f"Alpha Vantage prezzi error: {e}")
        return pd.DataFrame()


def _period_to_date(period: str) -> datetime:
    now = datetime.now()
    mapping = {
        "1mo":  now - timedelta(days=30),
        "3mo":  now - timedelta(days=90),
        "6mo":  now - timedelta(days=180),
        "1y":   now - timedelta(days=365),
        "2y":   now - timedelta(days=730),
        "5y":   now - timedelta(days=1825),
    }
    return mapping.get(period, now - timedelta(days=90))


def validate_ticker(ticker: str) -> dict:
    """Valida il ticker — fallback sicuro se yFinance dà 429."""
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info
        nome = info.get("longName") or info.get("shortName") or ticker
        if nome and nome != ticker:
            return {
                "valid":      True,
                "ticker":     ticker.upper(),
                "nome":       nome,
                "settore":    info.get("sector", "N/A"),
                "prezzo":     info.get("regularMarketPrice") or info.get("currentPrice"),
                "variazione": info.get("regularMarketChangePercent"),
            }
    except Exception:
        pass

    # Fallback: verifica tramite Alpha Vantage
    try:
        api_key = os.environ.get("ALPHA_VANTAGE", "")
        if api_key:
            r = requests.get(
                "https://www.alphavantage.co/query",
                params={"function": "SYMBOL_SEARCH", "keywords": ticker, "apikey": api_key},
                timeout=10,
            )
            matches = r.json().get("bestMatches", [])
            for m in matches:
                if m.get("1. symbol", "").upper() == ticker.upper():
                    return {
                        "valid":      True,
                        "ticker":     ticker.upper(),
                        "nome":       m.get("2. name", ticker),
                        "settore":    "N/A",
                        "prezzo":     None,
                        "variazione": None,
                    }
    except Exception:
        pass

    # Fallback finale — accetta comunque il ticker
    return {
        "valid":      True,
        "ticker":     ticker.upper(),
        "nome":       ticker.upper(),
        "settore":    "N/A",
        "prezzo":     None,
        "variazione": None,
    }