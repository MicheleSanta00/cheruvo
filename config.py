import streamlit as st

API_KEY = {
    'ALPHA_VANTAGE': st.secrets["ALPHA_VANTAGE"],
    'NEWSAPI': st.secrets["NEWSAPI"],
    'FMP': st.secrets["FMP"]
}

DEFAULT_TICKER = "NVDA"