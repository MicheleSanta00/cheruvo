# Cheruvo

Piattaforma SaaS di sentiment analysis su news finanziarie per investitori retail.

## Stack

| Layer | Tecnologia |
|-------|-----------|
| Frontend | React 18 + Vite |
| Backend | FastAPI (Python 3.11) |
| Auth | Supabase |
| Database | PostgreSQL (Supabase) |
| Pagamenti | Stripe |
| Email alert | Resend |
| Deploy frontend | Vercel |
| Deploy backend | Render |
| Cron | GitHub Actions (ogni 6h) |

## Setup locale

### Backend

```bash
cd backend
cp .env.example .env
# Compila .env con le tue chiavi
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
cp .env.production .env.local
# Imposta VITE_API_BASE=http://localhost:8000/api
npm install
npm run dev
```

## Variabili d'ambiente richieste

Vedi `backend/.env.example` per la lista completa.

Su Render: aggiungi le variabili in **Environment → Environment Variables**.  
Su GitHub Actions: aggiungi i segreti in **Settings → Secrets and variables → Actions**.

## Architettura news

1. **GitHub Actions** (ogni 6h) → `updater.py` → `quick_fetch.py` (VADER sentiment) → PostgreSQL
2. **On-demand** → `/api/fetch/{ticker}` → `quick_fetch.py` in background
3. **Alert** → dopo ogni fetch, `alerts.py` manda email agli utenti PRO con ticker in watchlist

## Tier Free vs PRO

| Feature | Free | PRO |
|---------|------|-----|
| Watchlist ticker | 3 | Illimitata |
| Periodo news | 30 giorni | 90 giorni |
| Periodo prezzi | 1M, 3M | + 6M, 1Y |
| Export CSV | ❌ | ✓ |
| Stats avanzate | ❌ | ✓ |
| Email alert | ❌ | ✓ |

## Struttura progetto

```
cheruvo/
├── backend/
│   ├── main.py          # FastAPI app, caching, rate limiting
│   ├── database.py      # Connection pool, SuperNewsAnalyzer
│   ├── quick_fetch.py   # Fetch news multi-sorgente + VADER
│   ├── alerts.py        # Sistema email alert PRO
│   ├── prices.py        # Prezzi OHLCV via yFinance
│   ├── stripe_routes.py # Checkout, webhook, subscription
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── App.jsx
│       ├── components/
│       └── hooks/
├── .github/workflows/
│   └── update_news.yml  # Cron GitHub Actions
├── updater.py           # Script cron principale
└── README.md
```