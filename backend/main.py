"""
Cheruvo — FastAPI Backend
"""
from dotenv import load_dotenv
load_dotenv()

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

sentry_sdk.init(
    dsn=__import__("os").environ.get("SENTRY_DSN", ""),
    integrations=[StarletteIntegration(), FastApiIntegration()],
    traces_sample_rate=0.2,   # campiona il 20% delle request per performance tracing
    environment=__import__("os").environ.get("ENVIRONMENT", "production"),
    send_default_pii=False,   # non inviare dati personali (email, IP) a Sentry
)

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware
from auth import get_current_user, get_current_user_optional, require_pro, get_user_tier
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import jwt as pyjwt
import os
import pandas as pd
import logging

from database import SuperNewsAnalyzer, init_database, get_pool
from prices import get_prices, validate_ticker
from stripe_routes import router as stripe_router, init_subscriptions_table
from quick_fetch import quick_fetch
from summary import genera_summary, _fallback
from onboarding import init_onboarding_table, send_welcome
from academy import router as academy_router, init_academy_tables
from classroom import router as classroom_router, init_classroom_tables
from book import router as book_router, init_book_tables
from market import router as market_router
from digest import router as digest_router, init_digest_tables
from earnings import router as earnings_router, init_earnings_tables
from cache import cache_get, cache_set, cache_delete_pattern, cache_stats, CACHE_TTL, SUMMARY_TTL, VALIDATE_TTL, TICKERS_TTL

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
    init_onboarding_table()
    init_academy_tables()
    init_classroom_tables()
    init_book_tables()
    init_digest_tables()
    init_earnings_tables()
    get_pool()
    yield

app = FastAPI(title="Cheruvo API", version="2.1.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://app.cheruvo.com",
        "https://cheruvo.com",
        "https://www.cheruvo.com",
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
app.add_middleware(GZipMiddleware, minimum_size=500)  # comprime risposte > 500 bytes
app.include_router(stripe_router, prefix="/api")
app.include_router(academy_router, prefix="/api")
app.include_router(classroom_router, prefix="/api")
app.include_router(book_router, prefix="/api")
app.include_router(market_router, prefix="/api")
app.include_router(digest_router, prefix="/api")
app.include_router(earnings_router, prefix="/api")

API_KEY = {
    "ALPHA_VANTAGE": os.environ.get("ALPHA_VANTAGE", ""),
    "NEWSAPI":       os.environ.get("NEWSAPI", ""),
    "FMP":           os.environ.get("FMP", ""),
    "REDDIT": {
        "client_id":     os.environ.get("REDDIT_CLIENT_ID", ""),
        "client_secret": os.environ.get("REDDIT_CLIENT_SECRET", ""),
    },
}

# Cache: importata da cache.py (Redis con fallback in-memory)



# ── Endpoints ──────────────────────────────────────────────────────────────

@app.get("/api/validate/{ticker}")
@limiter.limit("30/minute")
def ticker_info(ticker: str, request: Request,
                user: dict | None = Depends(get_current_user_optional)):
    cached = cache_get(f"validate:{ticker}", ttl=VALIDATE_TTL)
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
        cache_set(f"validate:{ticker}", result, ttl=VALIDATE_TTL)
        return result
    cache_set(f"validate:{ticker}", info, ttl=VALIDATE_TTL)
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
    cache_delete_pattern(ticker.upper())
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
    cache_set("tickers:all", result, ttl=TICKERS_TTL)
    return result


@app.get("/health")
def health():
    return {"status": "ok", **cache_stats()}

# ── AI Summary ─────────────────────────────────────────────────────────────


@app.get("/api/summary/{ticker}")
@limiter.limit("20/minute")
def get_summary(ticker: str, request: Request,
                user: dict = Depends(require_pro)):
    ticker = ticker.upper()
    cache_key = f"summary:{ticker}"

    # Cache con TTL 6 ore
    cached = cache_get(cache_key, ttl=SUMMARY_TTL)
    if cached:
        return cached

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
    cache_set(cache_key, result, ttl=SUMMARY_TTL)
    return result


# ── Onboarding ────────────────────────────────────────────────────────────

@app.post("/api/onboarding/welcome")
@limiter.limit("3/minute")
async def onboarding_welcome(request: Request, user: dict = Depends(get_current_user)):
    """
    Chiamato dal frontend subito dopo la registrazione.
    Registra l'utente nella tabella onboarding e invia l'email di benvenuto (giorno 0).
    Idempotente: se l'utente è già registrato, non invia una seconda email.
    """
    try:
        send_welcome(user["sub"], user["email"])
    except Exception as e:
        logger.error("Errore onboarding welcome per %s: %s", user.get("email"), e)
    return {"status": "ok"}


# ── AI Chat ────────────────────────────────────────────────────────────────

from pydantic import BaseModel
from groq import Groq

class ChatRequest(BaseModel):
    message: str
    ticker: str | None = None
    sentiment_score: float | None = None
    top_news: list[str] | None = None

@app.post("/api/chat")
@limiter.limit("20/minute")
async def chat(body: ChatRequest, request: Request,
               user: dict = Depends(get_current_user)):

    groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))

    # Costruisce il contesto del ticker se disponibile
    context = ""
    if body.ticker:
        score = body.sentiment_score
        label = "positivo (mercato ottimista)" if score and score > 0.1 else \
                "negativo (mercato pessimista)" if score and score < -0.1 else "neutro"
        context = f"\n\nContesto attuale: l'utente sta analizzando {body.ticker} con sentiment score {score} ({label})."
        if body.top_news:
            context += f"\nUltime notizie: {'; '.join(body.top_news[:3])}"

    system_prompt = f"""Sei un assistente finanziario integrato in Cheruvo, una piattaforma di analisi del sentiment delle notizie finanziarie.

Il tuo ruolo è:
- Spiegare concetti finanziari in modo semplice e accessibile
- Aiutare l'utente a capire i dati di sentiment che vede
- Rispondere a domande su azioni, mercati, indicatori
- Contestualizzare i dati del ticker analizzato

Regole:
- Rispondi sempre in italiano (a meno che l'utente scriva in inglese)
- Sii chiaro, conciso e accessibile anche a chi non è esperto
- Non dare mai consigli di investimento diretti
- Aggiungi sempre un disclaimer se la domanda implica decisioni finanziarie
- Usa esempi pratici per spiegare concetti complessi
{context}"""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": body.message},
            ],
            max_tokens=600,
            temperature=0.7,
        )
        reply = response.choices[0].message.content
        return {"reply": reply}
    except Exception as e:
        logger.error("Chat error: %s", e)
        raise HTTPException(status_code=503, detail="Servizio AI momentaneamente non disponibile")