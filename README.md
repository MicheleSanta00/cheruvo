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

### Licenze delle fonti

Girano solo tre fonti: **GDELT** (licenza libera anche commerciale), **SEC
EDGAR** (pubblico dominio) e **Alpha Vantage** (dietro `AV_ENABLED`, con
autorizzazione scritta del supporto). NewsAPI, Google News RSS e i feed
Yahoo/Sole24Ore restano nel codice come riferimento ma **non vengono chiamati**:
nessuno dei tre consente l'uso commerciale.

Il censimento del 5 agosto 2026 ha però contato **32.675 righe su 33.126** (il
98,6%) rimaste in archivio da prima che quei rubinetti venissero chiusi.
Due strumenti manuali, entrambi da Actions:

- `.github/workflows/backfill_gdelt.yml` ricostruisce lo storico da GDELT
- `.github/workflows/pulizia_licenze.yml` censisce e poi elimina l'arretrato

L'ordine conta: prima si ricostruisce, poi si cancella. Al contrario il sito
resterebbe con 451 notizie per settimane.

Una trappola da non ricreare: Alpha Vantage salva in `source` il **nome della
testata**, non il proprio. Per mesi questo ha reso indistinguibile una riga
Alpha Vantage (lecita) da una NewsAPI (vietata), e al momento del censimento
non è stato possibile salvare le prime. Ora la provenienza viaggia in
`score_source='av'`, scritta dalla fonte e non dedotta dal nome.

## Sveglia del backend e ore gratuite

Il backend sta sul piano gratuito di Render, che **si addormenta dopo 15 minuti**
senza richieste e ci mette circa un minuto a ripartire. Per evitare che il primo
visitatore aspetti quel minuto, un servizio esterno chiama `/ping` a intervalli
regolari.

Il vincolo da tenere a mente è il monte ore, e non è banale:

| | ore consumate in un mese da 31 giorni |
|---|---|
| Incluse nel piano | **750** |
| Sveglio 24 ore su 24 | 744, cioè **6 ore di margine** |
| Sveglio 07:00–01:00 | 558, circa **190 ore di margine** |
| Nessuna sveglia (solo traffico vero) | ~340 |

Le ore sono **per workspace, non per servizio**, quindi un secondo servizio
gratuito attinge dallo stesso monte. E siccome non c'è una carta registrata,
sforare non genera una fattura: **sospende i servizi fino al mese successivo**.
Tenerlo acceso troppo è il modo più rapido per farlo sparire davvero.

Per questo la sveglia è limitata alla fascia 07:00–01:00 (fuso Europe/Rome), che
copre le ore in cui un visitatore può plausibilmente arrivare e lascia margine
abbondante. Consumo reale controllabile su Render in **Billing → Monthly Included
Usage → Free Instance Hours**.

Nota: la prima chiamata della giornata trova il servizio addormentato e impiega
più dei 30 secondi oltre i quali cron-job.org considera fallita una richiesta.
**Un segno rosso alle 07:00 è previsto e innocuo**, la chiamata sveglia comunque
il servizio. Un rosso a metà giornata invece è un problema vero.

### Perché non UptimeRobot

C'era, e per 21 giorni ha segnato "down" mentre il servizio rispondeva 200. Non
era un difetto di visualizzazione: nello stesso periodo Render contava circa
metà delle ore trascorse, cioè il servizio si addormentava regolarmente e quei
controlli **non arrivavano proprio**. In più il loro pannello non finiva mai di
caricare e ogni azione rispondeva "something went wrong". Abbandonato invece che
riparato.

Vale la pena ricordare che l'allarme più importante non è questo: è
`backend/salute.py`, che a ogni giro del cron confronta la copertura news con la
media dei 7 giorni precedenti e manda una mail se crolla. Un server raggiungibile
che serve dati fermi è un guasto peggiore di un server irraggiungibile.

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