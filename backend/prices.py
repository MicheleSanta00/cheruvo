"""prices.py — senza dipendenze Streamlit."""
import yfinance as yf
import pandas as pd
from functools import lru_cache


def get_prices(ticker: str, period: str = "3mo") -> pd.DataFrame:
    try:
        df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        if df.empty:
            return pd.DataFrame()
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df[["Open", "High", "Low", "Close", "Volume"]]
    except Exception as e:
        print(f"Errore prezzi {ticker}: {e}")
        return pd.DataFrame()


def validate_ticker(ticker: str) -> dict:
    try:
        info = yf.Ticker(ticker).info
        return {
            "valid":   True,
            "ticker":  ticker.upper(),
            "nome":    info.get("longName", ticker),
            "settore": info.get("sector", "N/A"),
            "prezzo":  info.get("regularMarketPrice") or info.get("currentPrice"),
            "variazione": info.get("regularMarketChangePercent"),
        }
    except Exception:
        return {"valid": False, "ticker": ticker, "nome": ticker}
