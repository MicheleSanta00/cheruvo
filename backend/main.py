"""
Cheruvo — FastAPI Backend
"""
from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from auth import get_current_user, get_current_user_optional, require_pro, get_user_tier
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import jwt as pyjwt
import os
import pandas as pd
import time
import logging

from database import SuperNewsAnalyzer, init_database, get_pool
from prices import get_prices, validate_ticker
from stripe_routes import router as stripe_router, init_subscriptions_table
from quick_fetch import quick_fetch
from summary import genera_summary, _fallback

# ── Logging ───────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Rate limiter ───────────────────────────────────────────────────────────
def get_user_identifier(request: Request) -> str:
    """
    Chiave per il rate limiter: estrae lo user_id dal JWT senza verifica
    (la verifica vera la fa già get_current_user via Supabase). Usare l'ID
    utente invece dell'IP evita che utenti dietro NAT si blocchino a vicenda
    e impedisce il bypass del limite cambiando IP o VPN.
    Fallback sull'IP per endpoint pubblici o token malformati.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            # decode_without_verification: serve solo il campo 'sub' come chiave
            payload = pyjwt.decode(token, options={"verify_signature": False})
            sub = payload.get("sub")
            if sub:
                return f"user:{sub}"
        except Exception:
            pass
    return get_remote_address(request)

limiter = Limiter(key_func=get_user_identifier, default_limits=["60/minute"])

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_database()
    init_subscriptions_table()
    get_pool()
    yield

app = FastAPI(title="Cheruvo API", version="2.1.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://appcheruvo.vercel.app",
        "https://cheruvo.vercel.app",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

app.add_middleware(SecurityHeadersMiddleware)
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

# ── In-memory cache ────────────────────────────────────────────────────────
_cache: dict = {}
CACHE_TTL = 300  # 5 minuti

def cache_get(key: str):
    entry = _cache.get(key)
    if entry and time.time() - entry["ts"] < CACHE_TTL:
        return entry["data"]
    return None

def cache_set(key: str, data):
    _cache[key] = {"data": data, "ts": time.time()}



# ── Endpoints ──────────────────────────────────────────────────────────────

@app.get("/api/validate/{ticker}")
@limiter.limit("30/minute")
def ticker_info(ticker: str, request: Request,
                user: dict | None = Depends(get_current_user_optional)):
    cached = cache_get(f"validate:{ticker}")
    if cached:
        return cached
    info = validate_ticker(ticker.upper())
    if not info["valid"]:
        result = {
            "valid": False,
            "ticker": ticker.upper(),
            "nome": ticker.upper(),
            "settore": "N/A",
            "prezzo": None,
            "variazione": None,
        }
        cache_set(f"validate:{ticker}", result)
        return result
    cache_set(f"validate:{ticker}", info)
    return info


@app.get("/api/news/{ticker}")
@limiter.limit("20/minute")
def get_news(ticker: str, request: Request, days: int = 30,
             user: dict = Depends(get_current_user)):
    # Enforce limite giorni lato server in base al tier
    tier = get_user_tier(user["sub"])
    if tier != "pro":
        days = min(days, 30)
    cache_key = f"news:{ticker}:{days}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    analyzer = SuperNewsAnalyzer(ticker.upper(), API_KEY)
    df = analyzer.get_data(days)
    if df.empty:
        result = {"news": [], "total": 0, "avg_sentiment": 0,
                  "max_sentiment": 0, "min_sentiment": 0, "sources_count": 0}
        cache_set(cache_key, result)
        return result

    df["published_date"] = pd.to_datetime(
        df["published_date"], errors="coerce"
    ).dt.strftime("%Y-%m-%d").fillna("")

    result = {
        "news":          df.to_dict(orient="records"),
        "total":         len(df),
        "avg_sentiment": round(float(df["sentiment"].mean()), 4),
        "max_sentiment": round(float(df["sentiment"].max()), 4),
        "min_sentiment": round(float(df["sentiment"].min()), 4),
        "sources_count": int(df["source"].nunique()),
    }
    cache_set(cache_key, result)
    return result


@app.get("/api/prices/{ticker}")
@limiter.limit("20/minute")
def prices_endpoint(ticker: str, request: Request, period: str = "3mo",
                    user: dict = Depends(get_current_user)):
    # Enforce periodi disponibili in base al tier
    tier = get_user_tier(user["sub"])
    FREE_PERIODS = {"1mo", "3mo"}
    if tier != "pro" and period not in FREE_PERIODS:
        raise HTTPException(
            status_code=403,
            detail=f"Il periodo '{period}' richiede un abbonamento PRO"
        )
    cache_key = f"prices:{ticker}:{period}"
    cached = cache_get(cache_key)
    if cached:
        return cached
    df = get_prices(ticker.upper(), period)
    if df.empty:
        raise HTTPException(status_code=404, detail="Dati prezzi non disponibili")
    df.index = df.index.strftime("%Y-%m-%d")
    records = df.reset_index().rename(columns={"index": "date"}).to_dict(orient="records")
    result = {"prices": records}
    cache_set(cache_key, result)
    return result


@app.get("/api/sentiment/{ticker}")
@limiter.limit("20/minute")
def sentiment_daily(ticker: str, request: Request,
                    user: dict = Depends(get_current_user)):
    cache_key = f"sentiment:{ticker}"
    cached = cache_get(cache_key)
    if cached:
        return cached

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
    result = {"sentiment": daily.to_dict(orient="records")}
    cache_set(cache_key, result)
    return result


@app.post("/api/fetch/{ticker}")
@limiter.limit("5/minute")
async def fetch_news(ticker: str, request: Request, background_tasks: BackgroundTasks,
                     user: dict = Depends(get_current_user)):
    # Invalida la cache per questo ticker dopo il fetch
    for key in list(_cache.keys()):
        if f":{ticker.upper()}:" in key or f":{ticker.upper()}" in key:
            _cache.pop(key, None)
    background_tasks.add_task(quick_fetch, ticker.upper())
    return {"status": "started", "ticker": ticker.upper(),
            "message": "Fetching news in background..."}


@app.get("/api/tickers")
@limiter.limit("10/minute")
def list_tickers(request: Request, user: dict = Depends(get_current_user)):
    cached = cache_get("tickers:all")
    if cached:
        return cached
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT ticker FROM news ORDER BY ticker")
        tickers = [r[0] for r in cur.fetchall()]
        cur.close()
    finally:
        pool.putconn(conn)
    result = {"tickers": tickers}
    cache_set("tickers:all", result)
    return result


@app.get("/health")
def health():
    return {"status": "ok", "cache_entries": len(_cache)}

# ── AI Summary ─────────────────────────────────────────────────────────────

SUMMARY_TTL = 6 * 3600  # 6 ore

@app.get("/api/summary/{ticker}")
@limiter.limit("20/minute")
def get_summary(ticker: str, request: Request,
                user: dict = Depends(require_pro)):
    ticker = ticker.upper()
    cache_key = f"summary:{ticker}"

    # Cache con TTL 6 ore (override del TTL globale di 5 min)
    entry = _cache.get(cache_key)
    if entry and time.time() - entry["ts"] < SUMMARY_TTL:
        return entry["data"]

    # Recupera news dal DB
    pool = get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT title, sentiment FROM news
            WHERE ticker = %s
            AND published_date >= NOW() - INTERVAL '7 days'
            ORDER BY published_date DESC
            LIMIT 60""",
            (ticker,)
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        pool.putconn(conn)

    if not rows:
        result = _fallback(0.0)
        result["ticker"] = ticker
        result["avg_sentiment"] = 0.0
        result["news_analizzate"] = 0
        return result

    headlines = [r[0] for r in rows if r[0]]
    sentiments = [r[1] for r in rows if r[1] is not None]
    avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0.0

    # Recupera nome azienda dalla cache validate
    ticker_info = cache_get(f"validate:{ticker}") or {}
    company = ticker_info.get("nome", ticker)

    # Chiama Groq
    try:
        result = genera_summary(ticker, company, headlines, avg_sentiment)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    result["ticker"] = ticker
    result["avg_sentiment"] = round(avg_sentiment, 4)
    result["news_analizzate"] = len(headlines)

    # Salva in cache con TTL 6h
    _cache[cache_key] = {"data": result, "ts": time.time()}
    return result