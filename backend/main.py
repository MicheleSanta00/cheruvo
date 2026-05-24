"""
FinSentinel — FastAPI Backend
Sostituisce Streamlit con un'API REST pura.
"""
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import os
import psycopg2
import pandas as pd

from database import SuperNewsAnalyzer, init_database
from prices import get_prices, validate_ticker
from stripe_routes import router as stripe_router, init_subscriptions_table
from quick_fetch import quick_fetch


app = FastAPI(title="FinSentinel API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://finsentinel-three.vercel.app",
        "https://finsentinel-five.vercel.app",
        "http://localhost:5173",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stripe_router, prefix="/api")

API_KEY = {
    "ALPHA_VANTAGE": os.environ.get("ALPHA_VANTAGE", ""),
    "NEWSAPI":       os.environ.get("NEWSAPI", ""),
    "FMP":           os.environ.get("FMP", ""),
    "REDDIT": {
        "client_id":     os.environ.get("REDDIT_CLIENT_ID", ""),
        "client_secret": os.environ.get("REDDIT_CLIENT_SECRET", ""),
    },
}


# ── Startup ────────────────────────────────────────────────────────────────

@app.on_event("startup")
def startup():
    init_database()
    init_subscriptions_table()


# ── Endpoints ──────────────────────────────────────────────────────────────

@app.get("/api/validate/{ticker}")
def ticker_info(ticker: str):
    info = validate_ticker(ticker.upper())
    if not info["valid"]:
        # Ritorna comunque 200 con dati minimi invece di 404
        return {
            "valid": True,
            "ticker": ticker.upper(),
            "nome": ticker.upper(),
            "settore": "N/A",
            "prezzo": None,
            "variazione": None,
        }
    return info


@app.get("/api/news/{ticker}")
def get_news(ticker: str, days: int = 30):
    """Restituisce le news con sentiment per un ticker."""
    analyzer = SuperNewsAnalyzer(ticker.upper(), API_KEY)
    df = analyzer.get_data(days)
    if df.empty:
        return {"news": [], "total": 0, "avg_sentiment": 0,
                "max_sentiment": 0, "min_sentiment": 0, "sources_count": 0}

    df["published_date"] = pd.to_datetime(
        df["published_date"], errors="coerce"
    ).dt.strftime("%Y-%m-%d").fillna("")

    return {
        "news":           df.to_dict(orient="records"),
        "total":          len(df),
        "avg_sentiment":  round(float(df["sentiment"].mean()), 4),
        "max_sentiment":  round(float(df["sentiment"].max()), 4),
        "min_sentiment":  round(float(df["sentiment"].min()), 4),
        "sources_count":  int(df["source"].nunique()),
    }


@app.get("/api/prices/{ticker}")
def prices_endpoint(ticker: str, period: str = "3mo"):
    """OHLCV da yFinance."""
    df = get_prices(ticker.upper(), period)
    if df.empty:
        raise HTTPException(status_code=404, detail="Dati prezzi non disponibili")
    df.index = df.index.strftime("%Y-%m-%d")
    records = df.reset_index().rename(columns={"index": "date"}).to_dict(orient="records")
    return {"prices": records}


@app.get("/api/sentiment/{ticker}")
def sentiment_daily(ticker: str):
    """Sentiment medio giornaliero aggregato (per il grafico)."""
    analyzer = SuperNewsAnalyzer(ticker.upper(), API_KEY)
    df = analyzer.get_all_data()
    if df.empty:
        return {"sentiment": []}

    daily = (
        df.set_index("published_date")["sentiment"]
        .resample("D").mean()
        .fillna(0)
        .reset_index()
    )
    daily.columns = ["date", "sentiment"]
    daily["date"] = daily["date"].dt.strftime("%Y-%m-%d")
    daily["sentiment"] = daily["sentiment"].round(4)
    return {"sentiment": daily.to_dict(orient="records")}


@app.post("/api/fetch/{ticker}")
async def fetch_news(ticker: str, background_tasks: BackgroundTasks):
    """Fetch immediato con VADER in background."""
    background_tasks.add_task(quick_fetch, ticker.upper())
    return {"status": "started", "ticker": ticker.upper(),
            "message": "Fetching news in background..."}


@app.get("/api/tickers")
def list_tickers():
    """Lista tutti i ticker già nel database."""
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT ticker FROM news ORDER BY ticker")
    tickers = [r[0] for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"tickers": tickers}


@app.get("/health")
def health():
    return {"status": "ok"}
