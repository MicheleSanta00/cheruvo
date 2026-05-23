import yfinance as yf
import pandas as pd
import streamlit as st

@st.cache_data
def get_prices(ticker, period="3mo"):
    """Download prezzi"""
    try:
        prices = yf.download(ticker, period=period, progress=False, auto_adjust=True)
        if isinstance(prices.columns, pd.MultiIndex):
            prices.columns = prices.columns.droplevel(1)
        if prices.empty:
            return pd.DataFrame()
        prices.index = pd.to_datetime(prices.index).tz_localize(None)
        return prices[['Open', 'High', 'Low', 'Close', 'Volume']]
    except Exception as e:
        st.warning(f"Errore prezzi {ticker}: {str(e)[:50]}")
        return pd.DataFrame()

@st.cache_data
def validate_ticker(ticker):
    """Validazione yFinance"""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        return {
            'valid': True,
            'nome': info.get('longName', ticker),
            'settore': info.get('sector', 'N/A')
        }
    except:
        return {'valid': False, 'nome': ticker}