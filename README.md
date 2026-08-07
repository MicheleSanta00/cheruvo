# Cheruvo

**[cheruvo.com](https://cheruvo.com)** · Il sentiment delle criptovalute, letto dalle notizie.

Cheruvo legge la stampa finanziaria mondiale, assegna un punteggio a ogni
articolo su venti criptovalute e lo mette accanto all'indice di paura e avidità
del mercato. Serve a rispondere a una domanda sola: **che aria tira su questa
moneta, senza leggere settanta articoli.**

Tutto in italiano, gratis, senza account a pagamento.

## Cosa NON è

Vale la pena scriverlo prima del resto, perché è il modo in cui prodotti come
questo di solito mentono.

**Non prevede il prezzo.** Nessuno ha ancora dimostrato che il sentiment delle
notizie anticipi il mercato, e finché non è dimostrato qui dentro non viene
promesso. `backend/verifica_segnale.py` è lo strumento che serve a rispondere a
quella domanda in modo onesto: usa un test di permutazione, soglie fissate
prima di guardare i dati e un confronto con compra-e-tieni, e sa dire "non lo
so" quando i giorni disponibili sono pochi.

**Non è affidabile su tutte le monete allo stesso modo.** Il numero vale quanto
le notizie che lo sostengono: su Bitcoin ce ne sono a sufficienza, su una
alt-coin con tre articoli al giorno una media è rumore. Il conteggio è sempre
mostrato accanto al punteggio, apposta, e in classifica una moneta entra solo
con almeno `MIN_NEWS` notizie nelle 48 ore (`backend/market.py`). Era 2, ed è
il difetto che il 7 agosto 2026 apriva la home con "ADA +0,34 su 3 news": con
tre articoli l'incertezza sulla media è ±0,26, cioè più larga di tutta la scala
della classifica, e il primo posto era sorteggiato.

**Non è consulenza finanziaria.**

## Cosa mostra, e perché non è un livello

Un livello non è un'informazione. "BTC −0,08" non dice a nessuno se quel numero
è normale per Bitcoin, e chi lo legge non può farci niente.

`backend/anomalie.py` misura invece lo **scarto dalla normalità della moneta
stessa**: volume e tono delle ultime 24 ore contro le quattro settimane
precedenti. "Il sentiment su SOL sta quattro deviazioni sotto la sua norma, col
quadruplo delle notizie del solito" è un'affermazione sulle **notizie**, che
sappiamo dimostrare, non sul **prezzo**, che non sappiamo ancora.

Tre scelte statistiche, ognuna col suo motivo scritto accanto alla costante:

- **mediana e MAD** invece di media e deviazione standard, perché un solo picco
  passato gonferebbe la sigma abbastanza da nascondere tutti i picchi futuri;
- **un pavimento di Poisson** sul volume, perché un conteggio che vale 8
  oscilla di ±2,8 anche quando non succede niente;
- **si confronta la quota di attenzione**, non il conteggio nudo, altrimenti
  ogni sabato sarebbe un crollo per tutte le monete insieme.

La soglia è **4σ**, ed è stata misurata e non scelta: a 2σ la simulazione
produceva 34 avvisi falsi a settimana su quaranta monete, a 4σ ne produce meno
di uno. Resta sensibile a quello che conta: su una moneta media un ×3 di volume
viene visto il 97% delle volte, su Bitcoin basta un ×2.

Sotto **14 giorni di storico** il modulo non stima niente e dichiara di stare
ancora imparando. L'archivio riparte dal 6 agosto 2026 e le regole di raccolta
sono cambiate il 7, quindi una normalità calcolata prima di fine agosto
descriverebbe le nostre modifiche e non il mercato.

## Da dove vengono i dati

Solo fonti con diritto d'uso commerciale verificato:

| Fonte | Licenza | Uso |
|---|---|---|
| **GDELT** (API + file grezzi ogni 15 min) | libera, anche commerciale, con ridistribuzione | fonte principale |
| **SEC EDGAR** | pubblico dominio (atti USA) | depositi societari |
| **Alpha Vantage** | autorizzazione scritta del supporto | opzionale, dietro interruttore |
| **alternative.me** | libera per uso commerciale | indice paura e avidità |

NewsAPI, Google News RSS e i feed Yahoo sono stati **staccati**: nessuno dei tre
consente l'uso in produzione. Il codice che li chiamava resta come riferimento,
spento, con i motivi scritti accanto.

## Stack

| Layer | Tecnologia |
|-------|-----------|
| Frontend | React 18 + Vite → Vercel |
| Backend | FastAPI (Python 3.11) → Render |
| Auth e database | Supabase (PostgreSQL) |
| Punteggi | GDELT tone, VADER, Groq/Llama |
| Pagamenti | Stripe (attualmente disattivato) |
| Email | Resend |
| Automazioni | GitHub Actions |

## Licenza

Il codice è **pubblicamente consultabile ma non libero**: vedi
[`LICENSE`](./LICENSE). Il repository è pubblico per una ragione pratica, cioè i
minuti di GitHub Actions illimitati che servono a raccogliere le notizie, non
perché i diritti siano stati ceduti. I dati raccolti non fanno parte del
repository.

## Setup locale

### Backend

```bash
cd backend
cp ../.env.example .env
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

Vedi [`.env.example`](./.env.example) nella radice del progetto.

Su Render: aggiungi le variabili in **Environment → Environment Variables**.  
Su GitHub Actions: aggiungi i segreti in **Settings → Secrets and variables → Actions**.

## Architettura news

Due canali di raccolta, che si completano invece di sovrapporsi.

**1. File grezzi di GDELT** — `.github/workflows/ingest_grezzo.yml`, ogni 6 ore
   → `backend/ingest_grezzo.py` → PostgreSQL

   È il canale principale per volume. GDELT pubblica un file ogni 15 minuti su
   un server statico: niente rate limit, niente tetto di 250 risultati, e un
   feed separato per il resto del mondo tradotto. Il punteggio lo porta il file
   stesso, calcolato da GDELT sul **testo integrale** dell'articolo.

   Questi file contengono la cronaca del mondo intero, quindi il filtro conta
   quanto la raccolta. Due regole, entrambe in `serve_contesto`:

   - **le azioni pretendono una parola di mercato nel titolo**, le monete no.
     Il nome di una moneta è già un termine finanziario, il nome di
     un'azienda no: nella prima giornata piena di raccolta GOOGL e MSFT da
     soli valevano 816 righe su 1.541, quasi tutte aggiornamenti di prodotto
     e disservizi. Il prezzo di questa regola è che una notizia societaria
     come "Eni firma un accordo in Libia" resta fuori;
   - **un articolo vale per ogni asset che nomina.** Prima ci si fermava al
     primo, e le azioni vengono prima delle monete nel dizionario: "Microsoft
     mette Bitcoin in tesoreria" veniva archiviata solo come MSFT.

   Le sigle sono state provate e quasi tutte bocciate. Su 98.243 righe ne
   avrebbero portate 61 in più, ma DOGE è il Department of Government
   Efficiency (12 su 12), OP è l'operazione chirurgica in tedesco, SOL è il
   sole in spagnolo, ISP è il fornitore di connettività. Sopravvivono
   **BTC ed ETH**, e solo col contesto obbligatorio: circa 28 articoli al
   giorno, quasi tutti su Bitcoin. L'elenco sta in `SIGLE_AMMESSE` e la
   misura si rilancia con `gdelt_grezzo.py --modo sigle`.

   I titoli arrivano da GDELT con i caratteri non inglesi codificati in
   entità HTML. Fino al 7 agosto 2026 nessuno le decodificava, quindi ogni
   titolo non inglese finiva in archivio come `H&#xFC;fte verschlissen` ed è
   così che l'utente lo leggeva. `backend/ripara_titoli.py` sistema
   l'arretrato, con censimento prima della riscrittura.

**2. API di GDELT** — `.github/workflows/update_news.yml`, ogni 6 ore
   → `updater.py` → `backend/quick_fetch.py` → PostgreSQL

   Più mirato ma limitato: 250 risultati per interrogazione e un rate limit
   severo. Qui il punteggio nasce da VADER sul titolo e viene poi riclassificato
   da Groq. Serve anche al fetch a richiesta, quando un utente cerca un titolo
   che non abbiamo ancora.

**Alert** — dopo ogni giro, `backend/alerts.py` manda le email a chi ha quel
titolo in watchlist.

I tre punteggi convivono nella stessa tabella e si distinguono con
`score_source`: `gdelt` (testo integrale), `llm2` (Groq sul titolo), `av`
(Alpha Vantage), `vader` (ripiego). Groq **non tocca** le righe `gdelt` e `av`:
sostituirebbe un punteggio migliore con uno peggiore.

### Licenze delle fonti

L'elenco delle fonti ammesse è in cima a questo file. Qui sotto sta la storia
dell'arretrato, perché è finita.

Il censimento del 5 agosto 2026 aveva contato **32.675 righe su 33.126**, il
98,6%, rimaste in archivio da prima che i rubinetti vietati venissero chiusi.
Cancellarle subito avrebbe lasciato il sito con 451 notizie, quindi prima si è
ricostruito lo storico da GDELT.

Il **7 agosto 2026** le 32.675 righe sono state eliminate. L'archivio è passato
da 36.702 a **4.027 notizie**, tutte da fonti con diritto d'uso verificato. Il
censimento fatto poche ore prima della cancellazione contava ancora 32.675
righe vietate, lo stesso identico numero di due giorni prima: da quando le
fonti sono state staccate non ne è nata nemmeno una nuova, ed è la prova che i
rubinetti sono chiusi davvero e non solo nelle intenzioni.

Gli strumenti restano, entrambi manuali da Actions:

- `.github/workflows/backfill_gdelt.yml` ricostruisce lo storico da GDELT
- `.github/workflows/pulizia_licenze.yml` censisce e, con l'altra voce del
  menu, elimina

Il censimento non modifica niente e si può rilanciare quando si vuole: se un
giorno tornasse a contare più di zero, vorrebbe dire che una fonte vietata è
rientrata da qualche parte.

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

Lato app, quel minuto va detto e non subito in silenzio. `apiFetch.js` dà una
scadenza a ogni chiamata e, se supera i quattro secondi, avvisa l'interfaccia
che il server sta ripartendo (`onServerLento`). Fino al 7 agosto 2026 non
c'era né scadenza né avviso: la fetch restava appesa, quindi il meccanismo di
riprova che `App.jsx` aveva già scritto non veniva MAI raggiunto, e la pagina
mostrava "Caricamento dati di mercato..." all'infinito finché non ricaricavi a
mano. Chi arrivava per la prima volta vedeva un sito rotto.

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

## Piani

**Nessuno.** Il 6 agosto 2026 il muro a pagamento è stato spento e tutte le
funzioni sono aperte: watchlist senza limiti, storico completo, export, alert.

Non è generosità, è aritmetica: gli abbonati erano zero, quindi quel muro non
proteggeva nessun ricavo e toglieva funzioni proprio alle persone da cui si
può imparare qualcosa. La domanda a cui serve rispondere adesso non è "quanto
pagano" ma "chi lo usa e perché".

Stripe e la tabella `subscriptions` sono rimasti al loro posto e funzionanti.
Riaccendere il muro è **un interruttore**: la variabile d'ambiente
`PAYWALL_ATTIVO` per il backend (vedi `backend/auth.py`) e `isPro` in
`frontend/src/App.jsx`.

## Struttura progetto

```
cheruvo/
├── backend/
│   ├── main.py               # FastAPI, caching, rate limiting
│   ├── auth.py               # Supabase + interruttore PAYWALL_ATTIVO
│   ├── database.py           # connection pool
│   │
│   ├── gdelt_grezzo.py       # lettore dei file GDELT (misura, non scrive)
│   ├── ingest_grezzo.py      # raccolta dai file GDELT  ← canale principale
│   ├── gdelt_source.py       # API GDELT
│   ├── quick_fetch.py        # orchestrazione fonti + salvataggio
│   ├── sec_source.py         # SEC EDGAR
│   ├── sentiment_groq.py     # riclassificazione con Llama
│   │
│   ├── backfill_gdelt.py     # ricostruzione storico
│   ├── verifica_segnale.py   # il sentiment anticipa il prezzo?
│   ├── pulizia_licenze.py    # censimento e rimozione righe senza licenza
│   ├── ripara_titoli.py      # decodifica le entita HTML nei titoli
│   ├── salute.py             # allarme sul crollo di copertura
│   │
│   ├── prices.py             # prezzi OHLCV
│   ├── paura_avidita.py      # indice paura e avidità
│   ├── alerts.py             # email
│   └── tests/                # 149 test
│
├── frontend/src/
│   ├── App.jsx
│   └── components/
│
├── .github/workflows/
│   ├── ingest_grezzo.yml     # raccolta, 4 volte al giorno
│   ├── update_news.yml       # API GDELT + alert, 4 volte al giorno
│   ├── backfill_gdelt.yml    # manuale
│   ├── verifica_segnale.yml  # manuale
│   ├── pulizia_licenze.yml   # manuale
│   └── ripara_titoli.yml     # manuale
│
├── docs/                     # landing su cheruvo.com
├── updater.py
└── LICENSE
```