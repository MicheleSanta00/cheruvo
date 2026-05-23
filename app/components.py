import streamlit as st
import plotly.graph_objects as go
import pandas as pd

def show_kpi(df):
    """Mostra KPI metrics"""
    col1, col2, col3, col4, col5 = st.columns(5)
    avg_sentiment = df['sentiment'].mean()
    col1.metric("News", f"{len(df):,}")
    col2.metric("Sentiment", f"{avg_sentiment:.3f}", f"{avg_sentiment*100:.1f}%")
    col3.metric("Max", f"{df.sentiment.max():.3f}")
    col4.metric("Min", f"{df.sentiment.min():.3f}")
    col5.metric("Fonti", df.source.nunique())

def show_top_news(df):
    """Mostra top news positive/negative"""
    st.subheader("TOP 15 NEWS")
    top_positive = df.nlargest(10, 'sentiment')
    top_negative = df.nsmallest(5, 'sentiment')
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Migliori (Ottimismo)")
        for _, row in top_positive.iterrows():
            st.markdown(f"""
            <div style="padding: 12px; border-left: 5px solid #00ff88; 
            background: linear-gradient(90deg, #f0fff5 0%, #e8f8e8 100%); 
            margin: 8px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <b style="color: #00aa44;">{row.sentiment:.3f}</b> 
                <span style="color: #333; font-weight: 500;">{row.title[:70]}...</span>
                <br><small style="color: #666;">{row.source} | {row.published_date.strftime('%d/%m/%Y')}</small>
                <br><a href="{row.url}" target="_blank" style="color: #00aa44;">Link</a>
            </div>
            """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("### Peggiori (Pessimismo)")
        for _, row in top_negative.iterrows():
            st.markdown(f"""
            <div style="padding: 12px; border-left: 5px solid #ff4444; 
            background: linear-gradient(90deg, #fff5f5 0%, #f8e8e8 100%); 
            margin: 8px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <b style="color: #aa0000;">{row.sentiment:.3f}</b> 
                <span style="color: #333; font-weight: 500;">{row.title[:70]}...</span>
                <br><small style="color: #666;">{row.source} | {row.published_date.strftime('%d/%m/%Y')}</small>
                <br><a href="{row.url}" target="_blank" style="color: #aa0000;">Link</a>
            </div>
            """, unsafe_allow_html=True)

def show_stats(df):
    """Mostra statistiche"""
    st.subheader("Statistiche")
    col1, col2 = st.columns(2)
    
    with col1:
        source_counts = df['source'].value_counts().head(8)
        fig_pie = go.Figure(data=[go.Pie(
            labels=source_counts.index, values=source_counts.values,
            hole=0.4, marker_colors=['#00ff88', '#ffaa00', '#ff4444']
        )])
        fig_pie.update_layout(height=350, title="Fonti News")
        st.plotly_chart(fig_pie, use_container_width=True)
    
    with col2:
        fig_hist = go.Figure(data=[go.Histogram(
            x=df['sentiment'], nbinsx=20, marker_color='#00ff88', opacity=0.7
        )])
        fig_hist.update_layout(height=350, title="Distribuzione Sentiment")
        st.plotly_chart(fig_hist, use_container_width=True)