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
from auth import (get_current_user, get_current_user_optional, require_pro,
                  get_user_tier, tier_di)
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from pydantic import BaseModel, Field
import os
import pandas as pd
import asyncio
import logging
import time

# Istante in cui il processo è partito. Serve a una domanda sola, ma che senza
# di lui costa venti minuti di attesa ogni volta: l'istanza si sta spegnendo?
# Il piano gratuito di Render mette in pausa dopo quindici minuti senza
# traffico, e riaccenderla prende circa un minuto. A pagamento non si spegne
# mai. Con zero visitatori le due cose sono indistinguibili dall'esterno, a
# meno di aspettare e riprovare. Qui invece basta una richiesta: se l'uptime
# è di ore mentre nessuno ha aperto il sito, l'istanza non si sta spegnendo.
AVVIO = time.monotonic()

from database import SuperNewsAnalyzer, init_database, get_pool
from giornaliero import aggrega_giornaliero, media_senza_riprese
from payload import righe_per_json
from sentiment_groq import MODELLO_PUNTEGGIO, MODELLO_VELOCE
from prices import get_prices, validate_ticker, e_intraday, stato_mercato
from paura_avidita import router as fng_router
from stripe_routes import router as stripe_router, init_subscriptions_table
from quick_fetch import quick_fetch
from summary import genera_summary, _fallback
from onboarding import init_onboarding_table, send_welcome
# Academy, Classroom e Book rimossi il 3 agosto 2026: erano 4.772 righe, il 27%
# del progetto, e non avevano nulla a che vedere col sentiment finanziario.
# Le tabelle restano nel database e le migrazioni in supabase/migrations: se un
# giorno servissero, il codice si recupera dalla storia di git.
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
# La chiave del limite, il controllo del simbolo e dei periodi stanno in
# `richieste.py`: sono funzioni pure, e una funzione pura in main.py si prova
# solo tirandosi dietro l'app intera (la lezione di giornaliero.py).
from richieste import get_user_identifier, ticker_valido, PERIODI_AMMESSI  # noqa: E402

limiter = Limiter(key_func=get_user_identifier, default_limits=["60/minute"])

async def _prepara_tabelle():
    """
    Le creazioni di tabella, in sottofondo e non sulla strada del primo visitatore.

    PERCHE', misurato il 18 settembre 2026.

    Render spegne il servizio gratuito dopo quindici minuti senza traffico e
    dichiara circa SESSANTA secondi per riaccenderlo. Aprendo il sito se ne
    aspettavano due o tre: la differenza è tutta roba nostra che parte.

    Una parte è inevitabile (pandas e yfinance costano, e su una CPU condivisa
    costano molto di più che sul portatile). Questa invece no: `lifespan`
    eseguiva in fila CINQUE funzioni di inizializzazione, per un totale di una
    trentina fra CREATE TABLE IF NOT EXISTS, CREATE INDEX e ALTER TABLE ADD
    COLUMN, ognuna con la sua connessione a Supabase.

    E FastAPI non serve NESSUNA richiesta finché lifespan non arriva allo
    `yield`. Quindi chi apriva il sito aspettava anche quelle, ogni volta, per
    creare tabelle che esistono da luglio.

    È lo stesso difetto che sta scritto in cima a `visite.py`, spostato di un
    livello: là era DDL dentro ogni richiesta, qui è DDL dentro ogni avvio.
    `CREATE TABLE IF NOT EXISTS` sembra gratis perché di solito non fa niente,
    ma resta una richiesta di lock sullo schema.

    Ora il servizio risponde subito e le tabelle si preparano dietro. Sono
    tutte idempotenti e il database è in piedi da tre mesi, quindi non c'è
    niente da creare davvero: se un domani servisse una tabella nuova, la
    prima richiesta che la cerca potrebbe trovarla per un attimo assente, e
    per quello ogni errore qui viene scritto nel log invece di essere
    ingoiato.
    """
    def tutte():
        for nome, funzione in (("database", init_database),
                               ("subscriptions", init_subscriptions_table),
                               ("onboarding", init_onboarding_table),
                               ("digest", init_digest_tables),
                               ("earnings", init_earnings_tables)):
            try:
                funzione()
            except Exception as e:
                logger.error("init %s non riuscita: %s", nome, e)

    await asyncio.to_thread(tutte)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Il pool sì, prima di servire: è una connessione sola e senza di lui la
    # prima richiesta se la creerebbe comunque, pagandola per intera.
    get_pool()
    asyncio.create_task(_prepara_tabelle())
    yield

    # ── SPEGNIMENTO ──────────────────────────────────────────────────────
    #
    # L'ULTIMO VISITATORE DI OGNI GIORNATA NON VENIVA CONTATO.
    #
    # `visite.registra()` accumula in memoria e scrive sul database solo
    # quando arriva la richiesta successiva a sessanta secondi dall'ultima
    # scrittura. Lo scarico non ha un timer suo: lo innesca il traffico.
    #
    # E il traffico, qui, è cinque sessioni in ventun giorni. Quando una
    # persona arriva, guarda e se ne va, dopo di lei non arriva nessuno:
    # quello che ha fatto resta in memoria. Nemmeno la sveglia esterna la
    # salva, perché `/ping` e `/health` escono da `registra` PRIMA del
    # controllo sullo scarico, quindi non innescano niente.
    #
    # Poi il processo muore, sul piano gratuito dopo quindici minuti di
    # silenzio, e quei conteggi non sono mai esistiti. Su un sito affollato
    # sarebbe una perdita invisibile; su un sito con cinque visite in tre
    # settimane l'ultimo visitatore è una fetta enorme di tutti i visitatori.
    #
    # Render manda SIGTERM prima di spegnere, quindi qui c'è il tempo di
    # scrivere. In un thread, perché è I/O bloccante.
    try:
        import visite
        scritte = await asyncio.to_thread(visite.scarica_su_database)
        if scritte:
            logger.info("spegnimento: salvate %d righe di visite", scritte)
    except Exception as e:
        logger.error("spegnimento: scarico visite non riuscito: %s", e)

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

class ConteggioVisiteMiddleware(BaseHTTPMiddleware):
    """
    Conta quante sessioni distinte arrivano ogni giorno.

    Esiste perché l'8 agosto 2026 una persona ha scritto di aver provato il
    sito e non compariva da nessuna parte: PostHog non parte senza il consenso
    ai cookie, rispetta il Do Not Track e viene bloccato dagli ad blocker, e su
    Supabase finisce solo chi si registra. Tre filtri in fila, e ne basta uno.

    Qui invece si conta lato server, dove nessun blocco arriva. Non perché
    aggirare i blocchi sia furbo, ma perché queste sono richieste FUNZIONALI:
    contarle non è tracciare una persona, è sapere quante ne sono passate.

    Il dettaglio che rende la cosa lecita e onesta insieme: l'identificativo è
    un numero casuale generato dal browser per la singola sessione, che muore
    quando si chiude la scheda. Non segue nessuno da un giorno all'altro, non
    è legato a un account, non è ricavato dal dispositivo. Non salviamo IP,
    user agent, referrer né pagine viste.

    E non deve MAI far fallire una richiesta vera: se il conteggio si rompe,
    l'utente non se ne accorge.
    """
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        try:
            import visite
            sessione = request.headers.get(visite.INTESTAZIONE)
            if sessione and not visite.e_bot(request.headers.get("user-agent", "")):
                visite.registra(sessione, request.url.path)
        except Exception:
            pass
        return response


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(ConteggioVisiteMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=500)  # comprime risposte > 500 bytes
app.include_router(stripe_router, prefix="/api")
app.include_router(market_router, prefix="/api")
app.include_router(digest_router, prefix="/api")
app.include_router(earnings_router, prefix="/api")

# Questo dizionario viene passato a SuperNewsAnalyzer, che lo salva in
# self.api_key e non lo legge MAI: verificato il 6 agosto 2026, `self.api_key`
# compare una volta sola in tutto database.py, nell'assegnazione. È un residuo
# della versione Streamlit del progetto.
#
# Lo lascio perché toglierlo tocca la firma di SuperNewsAnalyzer e non è il
# momento, ma NEWSAPI è stata rimossa: quella chiave era in chiaro nella storia
# di git, il suo rubinetto è staccato da luglio, e newsapi.org non offre un modo
# di rigenerarla. Meglio non averla affatto che averne una che non si può
# cambiare.
API_KEY = {
    "ALPHA_VANTAGE": os.environ.get("ALPHA_VANTAGE", ""),
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
    # Chiave in maiuscolo: "aapl" e "AAPL" erano due voci di cache diverse, e
    # /summary cerca il nome dell'azienda proprio sotto quella maiuscola.
    ticker = ticker_valido(ticker)
    cached = cache_get(f"validate:{ticker}", ttl=VALIDATE_TTL)
    if cached:
        return cached
    info = validate_ticker(ticker)
    if not info["valid"]:
        result = {
            "valid": False,
            "ticker": ticker,
            "nome": ticker,
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
             user: dict | None = Depends(get_current_user_optional)):
    # SI LEGGE ANCHE SENZA ACCOUNT
    #
    # Il 16 agosto 2026 un utente su Reddit ha scritto "rimuovi il login wall,
    # voglio vedere prima di iscrivermi". Aveva ragione: dell'applicazione non
    # si vedeva niente senza registrarsi, e chi non l'ha provata non si
    # registra.
    #
    # Le notizie sono titoli GDELT con licenza aperta, gia' mostrati in home
    # senza account: aprirle non regala niente che non fosse gia' visibile.
    # Quello che resta chiuso e' cio' che SPENDE (/api/fetch e /api/chat
    # passano da Groq) e cio' che e' personale (watchlist, alert, export).
    #
    # Il limite dei giorni e' quello di prima, invariato: `tier_di` tratta chi
    # non ha un account come un iscritto senza abbonamento.
    ticker = ticker_valido(ticker)
    tier = tier_di(user)
    # Un tetto anche per chi vede tutto: prima `days` non ne aveva, e
    # ?days=100000 chiedeva al database l'intero archivio del titolo. Un
    # anno copre ogni vista che l'interfaccia offre. Sotto 1 non ha senso.
    days = max(1, min(days, 365))
    if tier != "pro":
        days = min(days, 30)
    cache_key = f"news:{ticker}:{days}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    analyzer = SuperNewsAnalyzer(ticker, API_KEY)
    df = analyzer.get_data(days)
    if df.empty:
        # Zero notizie non e' un sentiment neutro: e' un "non lo so". Il
        # frontend mostra gia' un trattino quando avg_sentiment e' null.
        result = {"news": [], "total": 0, "distinte": 0, "avg_sentiment": None,
                  "max_sentiment": None, "min_sentiment": None, "sources_count": 0}
        cache_set(cache_key, result)
        return result

    # L'ORA SI TIENE (24 settembre 2026)
    #
    # Qui si tagliava a "%Y-%m-%d". Il frontend (TopNews.jsx) mostra l'ora per
    # le notizie di oggi e la data per le altre: con la sola data ogni notizia
    # di oggi diventava la mezzanotte UTC, cioe' "02:00" in Italia d'estate, e
    # l'elenco "Recenti" metteva in fila a caso quelle dello stesso giorno.
    # Nell'archivio l'ora c'e' (V2.1DATE di GDELT, al quarto d'ora): ora arriva
    # fino al browser, in UTC con la Z, cosi' ogni fuso la converte da se'.
    # CSV e PDF prendono i primi dieci caratteri, quindi non cambiano.
    df["published_date"] = pd.to_datetime(
        df["published_date"], errors="coerce", utc=True
    ).dt.strftime("%Y-%m-%dT%H:%M:%SZ").fillna("")

    # La media con le riprese fuse, come il grafico e la classifica: vedi
    # `giornaliero.media_senza_riprese`. Massimo e minimo restano sulle righe,
    # perche' sono singole notizie e non una media.
    media, distinte = media_senza_riprese(df)
    punteggi = df["sentiment"].dropna()

    result = {
        "news":          righe_per_json(df),
        "total":         len(df),
        "distinte":      distinte,
        "avg_sentiment": round(media, 4) if media is not None else None,
        "max_sentiment": round(float(punteggi.max()), 4) if len(punteggi) else None,
        "min_sentiment": round(float(punteggi.min()), 4) if len(punteggi) else None,
        "sources_count": int(df["source"].nunique()),
    }
    cache_set(cache_key, result)
    return result


@app.get("/api/prices/{ticker}")
@limiter.limit("20/minute")
def prices_endpoint(ticker: str, request: Request, period: str = "3mo",
                    user: dict | None = Depends(get_current_user_optional)):
    # Enforce periodi disponibili in base al tier.
    # "1d" (la vista Oggi) resta gratuita di proposito: è quello che fa
    # sembrare il prodotto vivo appena lo apri, e metterlo dietro il paywall
    # significherebbe nascondere l'unica cosa che si muove.
    ticker = ticker_valido(ticker)
    # Solo i periodi che `prices.py` conosce davvero: prima una stringa
    # qualsiasi passava, diventava una chiave di cache nuova e ripiegava in
    # silenzio su tre mesi.
    if period not in PERIODI_AMMESSI:
        raise HTTPException(status_code=400, detail="Periodo non valido")
    tier = tier_di(user)
    FREE_PERIODS = {"1d", "1mo", "3mo"}
    if tier != "pro" and period not in FREE_PERIODS:
        raise HTTPException(
            status_code=403,
            detail=f"Il periodo '{period}' richiede un abbonamento PRO"
        )

    intraday = e_intraday(period)
    # La cache normale dura 5 minuti: troppo per un grafico che deve muoversi
    # sotto gli occhi. Sull'intraday scende a 45 secondi, che è comunque
    # abbastanza da non tempestare Yahoo se più utenti guardano lo stesso titolo.
    ttl = 45 if intraday else CACHE_TTL

    cache_key = f"prices:{ticker}:{period}"
    cached = cache_get(cache_key, ttl=ttl)
    if cached:
        return cached

    df = get_prices(ticker.upper(), period)
    if df.empty:
        raise HTTPException(status_code=404, detail="Dati prezzi non disponibili")

    # Sull'intraday serve anche l'ora, non solo la data: è tutta la differenza
    # fra un punto al giorno e un punto al minuto.
    df.index = df.index.strftime("%Y-%m-%d %H:%M" if intraday else "%Y-%m-%d")
    records = df.reset_index().rename(columns={"index": "date"}).to_dict(orient="records")

    result = {"prices": records}
    if intraday:
        # Lo stato del mercato viaggia insieme ai prezzi: il frontend deve
        # sapere se la borsa è aperta (per decidere se continuare a
        # ricaricare) e quando è avvenuto l'ultimo scambio (per scriverlo
        # accanto al prezzo invece di far credere che sia adesso).
        result["mercato"] = stato_mercato(ticker.upper())

    cache_set(cache_key, result, ttl=ttl)
    return result


@app.get("/api/sentiment/{ticker}")
@limiter.limit("20/minute")
def sentiment_daily(ticker: str, request: Request,
                    user: dict | None = Depends(get_current_user_optional)):
    ticker = ticker_valido(ticker)
    cache_key = f"sentiment:{ticker}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    analyzer = SuperNewsAnalyzer(ticker, API_KEY)
    df = analyzer.get_all_data()
    if df.empty:
        return {"sentiment": []}

    result = {"sentiment": aggrega_giornaliero(df)}
    cache_set(cache_key, result)
    return result


@app.post("/api/fetch/{ticker}")
@limiter.limit("5/minute")
async def fetch_news(ticker: str, request: Request, background_tasks: BackgroundTasks,
                     user: dict = Depends(get_current_user)):
    ticker = ticker_valido(ticker)
    # Invalida la cache per questo ticker dopo il fetch
    cache_delete_pattern(ticker)
    background_tasks.add_task(quick_fetch, ticker)
    return {"status": "started", "ticker": ticker,
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


app.include_router(fng_router, prefix="/api")


@app.get("/ping")
def ping():
    """
    Endpoint per il servizio che tiene sveglio Render, e nient'altro.

    Esiste separato da /health perché /health interroga Redis due volte per
    riportare le statistiche della cache. Su un controllo ogni cinque minuti
    fanno quasi seicento chiamate al giorno spese per rispondere a un robot
    che vuole solo sapere se il server è acceso. Questo non tocca niente.

    Riporta anche da quanto è acceso, perché è il modo più economico di sapere
    se l'istanza si sta ancora spegnendo da sola. Non è un dato personale e non
    costa una query: è una sottrazione.
    """
    su_da = time.monotonic() - AVVIO
    return {
        "ok": True,
        "uptime_secondi": round(su_da),
        "uptime_leggibile": f"{int(su_da // 3600)}h {int(su_da % 3600 // 60)}m",
    }

# ── AI Summary ─────────────────────────────────────────────────────────────


@app.get("/api/summary/{ticker}")
@limiter.limit("20/minute")
def get_summary(ticker: str, request: Request,
                user: dict = Depends(require_pro)):
    ticker = ticker_valido(ticker)
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
    # Riprese fuse anche qui, come nel resto del prodotto: altrimenti il
    # giudizio del riassunto poteva nascere da un lancio d'agenzia copiato
    # sessanta volte (vedi giornaliero.media_senza_riprese).
    media, _ = media_senza_riprese(pd.DataFrame(rows, columns=["title", "sentiment"]))
    avg_sentiment = media if media is not None else 0.0

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
def onboarding_welcome(request: Request, user: dict = Depends(get_current_user)):
    """
    Chiamato dal frontend al primo accesso di un utente.
    Registra l'utente nella tabella onboarding e invia l'email di benvenuto (giorno 0).
    Idempotente: se l'email di benvenuto e' gia' partita non ne manda un'altra
    (vedi `onboarding.send_welcome`, che prima non lo era affatto).

    `def` e non `async def`, dal 24 settembre 2026: dentro c'e' una query
    psycopg2 e una chiamata HTTP a Resend, tutte e due bloccanti. In una
    funzione async fermavano l'intero ciclo di eventi, cioe' ogni altro
    utente, finche' l'email non era partita. FastAPI esegue le funzioni
    sincrone in un thread a parte, che e' quello che serve.
    """
    try:
        send_welcome(user["sub"], user["email"])
    except Exception as e:
        logger.error("Errore onboarding welcome per %s: %s", user.get("email"), e)
    return {"status": "ok"}


# ── AI Chat ────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    # I tetti non sono estetica: senza, un messaggio da un megabyte andava
    # dritto a Groq e si mangiava in una volta la quota gratuita del giorno.
    message: str = Field(..., min_length=1, max_length=2000)
    ticker: str | None = Field(default=None, max_length=20)
    sentiment_score: float | None = None
    top_news: list[str] | None = Field(default=None, max_length=10)

@app.post("/api/chat")
@limiter.limit("20/minute")
def chat(body: ChatRequest, request: Request,
         user: dict = Depends(get_current_user)):
    # Sincrona per lo stesso motivo di onboarding_welcome: la chiamata a Groq
    # e' bloccante e dura secondi, e dentro una funzione async teneva fermo il
    # server per tutti gli altri mentre il modello scriveva.
    from sentiment_groq import _get_groq
    groq_client = _get_groq()

    # Costruisce il contesto del ticker se disponibile
    context = ""
    if body.ticker:
        score = body.sentiment_score
        label = "positivo (mercato ottimista)" if score and score > 0.1 else \
                "negativo (mercato pessimista)" if score and score < -0.1 else "neutro"
        context = f"\n\nContesto attuale: l'utente sta analizzando {body.ticker} con sentiment score {score} ({label})."
        if body.top_news:
            titoli = [str(t)[:300] for t in body.top_news[:3]]
            context += f"\nUltime notizie: {'; '.join(titoli)}"

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
            model=MODELLO_PUNTEGGIO,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": body.message},
            ],
            # Era 600, tarato su Llama che rispondeva e basta. Dal 16 agosto
            # 2026 il modello e' un GPT-OSS, che RAGIONA prima di rispondere e
            # paga quel ragionamento con lo stesso tetto: con 600 poteva
            # finire il budget prima di scrivere una parola, e la chat
            # tornava una risposta vuota. Un tetto piu' alto non consuma
            # quota: si contano i token generati, non quelli concessi (la
            # nota completa sta in sentiment_groq.py, sopra BATCH_PROMPT).
            max_tokens=2000,
            temperature=0.7,
        )
        reply = (response.choices[0].message.content or "").strip()
    except Exception as e:
        logger.error("Chat error: %s", e)
        raise HTTPException(status_code=503, detail="Servizio AI momentaneamente non disponibile")
    if not reply:
        logger.warning("Chat: il modello ha restituito una risposta vuota")
        raise HTTPException(status_code=503, detail="Servizio AI momentaneamente non disponibile")
    return {"reply": reply}