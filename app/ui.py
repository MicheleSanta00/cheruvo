import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

from config import API_KEY, DEFAULT_TICKER
from data.database import SuperNewsAnalyzer
from data.prices import get_prices, validate_ticker
from app.components import show_kpi, show_top_news, show_stats
from pathlib import Path  
from data import list_databases  


def run_app():
    """Funzione principale UI"""
    st.set_page_config(layout="wide", page_title="Sentiment Analyzer", page_icon="📈")
    
    st.markdown("""
    # Sentiment Analyzer
    **News + Prezzi + Sentiment in tempo reale**  
    *NVDA, AAPL, TSLA, MSFT e 1000+ titoli*
    """)
    
    # Sidebar
    setup_sidebar()
    
    # Main content
    if st.session_state.get('ticker'):
        show_main_content()

def setup_sidebar():
    """Sidebar controls"""
    st.sidebar.header("Controlli")
    ticker = st.sidebar.text_input("Ticker", value=DEFAULT_TICKER)
    st.session_state.ticker = ticker
    
    days_filter = st.sidebar.slider("News ultimi giorni", 7, 90, 30)
    st.session_state.days_filter = days_filter
    
    periodo_prezzi = st.sidebar.selectbox("Periodo prezzi", ["1mo", "3mo", "6mo", "1y"], index=1)
    st.session_state.periodo_prezzi = periodo_prezzi

    if st.sidebar.button("MEGA UPDATE", type="primary", use_container_width=True):
        analyzer = SuperNewsAnalyzer(ticker, API_KEY)
        with st.spinner("Scaricando da 2+ API..."):
            count = analyzer.mega_fetch()
        if count > 0:
            st.balloons()
            st.rerun()

    if st.sidebar.button("Pulisci Cache"):
        st.cache_data.clear()
        st.rerun()

    dbs = list_databases()
    st.sidebar.markdown(f"**Database:** {len(dbs)} ticker")
    if st.sidebar.button("Pulisci tutti DB"):
        db_folder = Path("data/news_databases")
        for db_file in db_folder.glob("*.db"):
            db_file.unlink(missing_ok=True)
        st.success("🧹 DB puliti!")
        st.rerun()

def show_main_content():
    """Contenuto principale"""
    ticker = st.session_state.ticker
    days_filter = st.session_state.days_filter
    periodo_prezzi = st.session_state.periodo_prezzi
    
    ticker_info = validate_ticker(ticker)
    if not ticker_info['valid']:
        st.error(f"**{ticker}** non trovato!")
        st.info("Prova: AAPL, TSLA, NVDA, MSFT, GOOGL")
        return
    
    
    st.markdown(f"## {ticker} - {ticker_info['nome']}")
    st.info(f"Settore: {ticker_info.get('settore', 'N/A')}")
    
    try:
        analyzer = SuperNewsAnalyzer(ticker, API_KEY)
        df = analyzer.get_data(days_filter)

        if df.empty:
            st.info("Clicca MEGA UPDATE per caricare news!")
            return

        df['published_date'] = pd.to_datetime(df['published_date'], errors='coerce')
        df = df.dropna(subset=['published_date']).sort_values('published_date')
        
        # Mostra sezioni
        show_kpi(df)
        show_charts(df, ticker, periodo_prezzi)
        show_top_news(df)
        show_stats(df)
        
    except Exception as e:
        st.error(f"Errore: {str(e)}")

def show_charts(df, ticker, periodo_prezzi):
    prices = get_prices(ticker, periodo_prezzi)
    if prices.empty:
        return
    
    analyzer = SuperNewsAnalyzer(ticker, API_KEY)
    all_news = analyzer.get_all_data()
    
    if all_news.empty:
        st.warning("Nessuna news storica valida")
        return
    
    # 🔧 Sentiment con date SICURE
    sentiment_daily = (all_news
                      .assign(published_date=pd.to_datetime(all_news['published_date'], errors='coerce'))
                      .dropna(subset=['published_date'])
                      .set_index('published_date')['sentiment']
                      .resample('D').mean()
                      .fillna(0))
    
    # Allinea con prezzi
    sentiment_aligned = sentiment_daily.reindex(prices.index, fill_value=0).ffill().fillna(0)
    
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                       subplot_titles=(f'{ticker} ({periodo_prezzi})', 'Sentiment'),
                       vertical_spacing=0.1, row_heights=[0.7, 0.3])
    
    fig.add_trace(go.Candlestick(x=prices.index, open=prices['Open'], 
                                high=prices['High'], low=prices['Low'], 
                                close=prices['Close'], name='Prezzo'), row=1, col=1)
    
    colori = ['#ff4444' if x < 0 else '#ffaa00' if x < 0.1 else '#00ff88' 
              for x in sentiment_aligned.values]
    
    fig.add_trace(go.Bar(x=sentiment_aligned.index, y=sentiment_aligned.values,
                        marker_color=colori, name='Sentiment', opacity=0.9), row=2, col=1)
    
    fig.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.5, row=2, col=1)
    
    fig.update_layout(height=750, hovermode='x unified', template='plotly_dark',
                     xaxis_rangeslider_visible=False)
    fig.update_yaxes(title_text="Prezzo ($)", row=1, col=1)
    fig.update_yaxes(title_text="Sentiment", range=[-1, 1], row=2, col=1)
    
    st.plotly_chart(fig, use_container_width=True)

