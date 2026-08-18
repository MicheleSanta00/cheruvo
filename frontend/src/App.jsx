import { useState, useEffect, useRef } from 'react'
import Auth        from './components/Auth.jsx'
import Profile     from './components/Profile.jsx'
import { supabase } from './supabase.js'
import { useLang }  from './LangContext.jsx'
import apiFetch, { onServerLento } from './apiFetch.js'

import Sidebar     from './components/Sidebar.jsx'
import KPIGrid     from './components/KPIGrid.jsx'
import TickerStrip from './components/TickerStrip.jsx'
import MarketRail  from './components/MarketRail.jsx'
import StatusBar   from './components/StatusBar.jsx'
import SummaryCard from './components/SummaryCard.jsx'
import Chart       from './components/Chart.jsx'
import TopNews     from './components/TopNews.jsx'
import Stats            from './components/Stats.jsx'
import CorrelationPanel from './components/CorrelationPanel.jsx'
import ComparePanel       from './components/ComparePanel.jsx'
import OnboardingTooltip  from './components/OnboardingTooltip.jsx'
import ChatWidget         from './components/ChatWidget.jsx'
import Icon               from './components/Icon.jsx'
import MarketToday        from './components/MarketToday.jsx'
import { useFinData } from './hooks/useFinData.js'
import { generateReport } from './utils/generatePDF.js'
import { statoCopertura, etichettaCopertura, coloreCopertura, offriScarico, PIENA, VUOTA }
  from './utils/copertura.js'
import { identifyUser, resetUser, track } from './analytics.js'
import { TICKERS } from './data/tickers.js'
import LogoCrypto, { eCrypto, nelMercato, leggiMercato, salvaMercato, PREDEFINITO }
  from './components/LogoCrypto.jsx'
import PauraAvidita from './components/PauraAvidita.jsx'
import SezioneAzioni from './components/SezioneAzioni.jsx'
import PrezzoMobile from './components/PrezzoMobile.jsx'


/**
 * Schermo stretto? Serve a smontare l'impalcatura a riquadri fissi.
 *
 * Cheruvo su desktop è una plancia: altezza bloccata a 100dvh, colonne
 * affiancate, e OGNI riquadro scorre per conto suo. È il comportamento giusto
 * su un monitor, dove vedi tutto insieme e vuoi che l'intestazione resti
 * ferma. Su un telefono lo stesso schema lascia al contenuto una finestrella
 * alta pochi centimetri, incastrata fra barra in alto e barra di stato, dentro
 * cui bisogna scorrere grafici e notizie con il pollice: impossibile.
 *
 * Su schermo stretto quindi si toglie l'impalcatura: niente altezze bloccate,
 * niente scorrimenti interni, la pagina scorre tutta insieme come una pagina
 * normale. È quello che il pollice si aspetta.
 */
function useSchermoStretto() {
  const [stretto, setStretto] = useState(
    () => typeof window !== 'undefined' && window.innerWidth <= 640
  )
  useEffect(() => {
    const su = () => setStretto(window.innerWidth <= 640)
    window.addEventListener('resize', su)
    window.addEventListener('orientationchange', su)
    return () => {
      window.removeEventListener('resize', su)
      window.removeEventListener('orientationchange', su)
    }
  }, [])
  return stretto
}

const DEFAULT_TICKER = 'NVDA'
const DEFAULT_DAYS   = 30
const DEFAULT_PERIOD = '3mo'

export default function App() {
  const { lang, t, toggleLang } = useLang()

  const [user, setUser]               = useState(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [ticker, setTicker]           = useState(() => PREDEFINITO[leggiMercato()] || DEFAULT_TICKER)
  const [days, setDays]               = useState(DEFAULT_DAYS)
  const [period, setPeriod]           = useState(DEFAULT_PERIOD)
  // Paywall spento il 6 agosto 2026: tutte le funzioni sono aperte a tutti.
  //
  // Partendo da `true` sparisce ogni lucchetto, ogni invito a pagare e ogni
  // periodo bloccato, senza dover toccare i dieci punti che leggono questa
  // variabile. Il backend fa la stessa cosa dalla sua parte (PAYWALL_ATTIVO in
  // auth.py): riaccenderlo vuol dire rimettere `false` qui e la variabile
  // d'ambiente là.
  //
  // Il motivo: gli abbonati erano zero. Quel muro non proteggeva ricavi, e
  // toglieva funzioni proprio alle persone che servono per capire cosa
  // costruire.
  const [isPro, setIsPro]             = useState(true)

  // CHI STA GUARDANDO SENZA ACCOUNT
  //
  // Il 16 agosto 2026, su r/ItaliaStartups: "Rimuovi il Login wall, voglio
  // vedere prima di iscrivermi". Aveva ragione, e la riga qui sotto era il
  // muro: `if (!user) return <Auth />` rimandava alla schermata di accesso
  // chiunque, quindi del prodotto non si vedeva niente prima di registrarsi.
  // Chi non lo prova non si registra, e nessuno si registra per scoprire se
  // valeva la pena.
  //
  // Adesso la registrazione non è più una porta, è la profondità: sette
  // giorni di storico per chi passa, trenta per chi ha un account. Il limite
  // si incontra DOPO aver visto che funziona, che è l'unico momento in cui
  // uno accetta di lasciare l'email.
  const [mostraAccesso, setMostraAccesso] = useState(false)

  /**
   * Chiede l'account per un'azione che ne ha bisogno.
   *
   * Restituisce true se l'azione va fermata. Sta in una funzione sola perché
   * i punti da proteggere sono sparsi (aggiornamento, export, chat, profilo)
   * e la scelta di quale porta chiudere non deve dipendere da chi si ricorda
   * di scrivere il controllo.
   */
  const serveAccount = () => {
    if (user) return false
    track('signup_prompted', { ticker: loadedTicker })
    setMostraAccesso(true)
    return true
  }

  const [showProfile, setShowProfile] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [loadedTicker, setLoadedTicker] = useState(null)
  const [showStats, setShowStats]     = useState(false)
  const [showHeaderMenu, setShowHeaderMenu] = useState(false)
  const [showMarket, setShowMarket]   = useState(false)
  // Mercato attivo: azioni o crypto. Filtra tutto quello che è un elenco.
  const [mercatoAttivo, setMercatoAttivo] = useState(leggiMercato)
  const stretto = useSchermoStretto()
  // LE AZIONI SONO APERTE (15 agosto 2026)
  //
  // Erano chiuse dietro ?azioni=1, un indirizzo passato a mano a chi doveva
  // provarle. Si aprono adesso perché la copertura c'è: NVDA 66 notizie nelle
  // ultime 48 ore, GOOGL 33, AAPL 32, SAP 27, TSLA 27, AMZN 25, MSFT 21, e poi
  // le italiane (Eni, UniCredit, Ferrari) e le europee (ASML, Shell). Diciassette
  // titoli con notizie vere, non una sezione vuota da riempire di promesse.
  //
  // Il flag resta come rete: `?azioni=0` le richiude, se un giorno servisse
  // spegnerle in fretta senza aspettare un deploy.
  const azioniChiuse = typeof window !== 'undefined' &&
    new URLSearchParams(window.location.search).get('azioni') === '0'

  // Le classifiche, il nastro e la colonna destra mostrano SOLO il mercato
  // attivo: un elenco che mescola Bitcoin ed Eni non si legge.
  const righeFiltrate = (righe) => (righe || []).filter(r => nelMercato(r.ticker, mercatoAttivo))

  const { tickerInfo, news, stats, prices, mercato: statoBorsa, sentiment, loading,
          fetching, error, load, triggerFetch, setFetching, refreshPrezzi } = useFinData()

  // Dati di mercato caricati UNA volta e condivisi da nastro, colonna destra,
  // dashboard e barra di stato: prima ogni pezzo se li sarebbe ripresi da solo.
  const [mercato, setMercato] = useState(null)
  const [mktStats, setMktStats] = useState(null)
  // Quanto c'è dietro ogni nome della lista. Il selettore ne offre 302,
  // l'archivio ne segue 52, e il 18 agosto 2026 ventisette arrivavano a
  // cinque notizie in 48 ore: senza questo dato chi sceglie un nome a caso
  // non ha modo di saperlo prima di cliccarci.
  const [copertura, setCopertura] = useState(null)
  // Vero quando il backend non risponde: quasi sempre significa che Render lo
  // ha spento per inattività (succede dopo un quarto d'ora) e ci mette circa un
  // minuto a ripartire. Prima l'errore veniva ingoiato in silenzio e l'utente
  // restava davanti a una fila di trattini e a un "Caricamento" che non
  // finiva mai, indistinguibile da un prodotto rotto.
  const [risveglio, setRisveglio] = useState(false)

  // L'avviso di risveglio non aspetta che una chiamata fallisca.
  //
  // Prima `risveglio` si accendeva solo dentro il catch, cioè dopo che un
  // tentativo era andato a vuoto: con la scadenza a 15 secondi e due tentativi
  // vuol dire mezzo minuto di schermo muto prima di dire qualcosa. apiFetch
  // invece segnala già dopo quattro secondi che la richiesta sta impiegando
  // troppo, e quattro secondi è la soglia oltre la quale una persona comincia
  // a pensare che il sito sia rotto.
  useEffect(() => onServerLento(setRisveglio), [])

  useEffect(() => {
    let vivo = true
    let attesa = null

    const carica = (tentativo = 0) => {
      Promise.all([
        apiFetch('/market/today'),
        apiFetch('/market/stats'),
        // Se la copertura non arriva, il selettore resta com'era prima e non
        // dice niente: peggiora, non si rompe. Per questo ha un catch suo e
        // non fa fallire le altre due.
        apiFetch('/market/copertura').catch(() => null),
      ])
        .then(([oggi, stat, cop]) => {
          if (!vivo) return
          setMercato(oggi)
          setMktStats(stat)
          if (cop) setCopertura(cop)
          setRisveglio(false)
        })
        .catch(() => {
          if (!vivo) return
          setRisveglio(true)
          // Riprova con attese crescenti: 4, 8, 12, 16 e poi 20 secondi fissi.
          // Il risveglio dura circa un minuto, quindi entro il quinto tentativo
          // di solito è tornato, e chi sta guardando lo vede comparire da solo
          // senza dover ricaricare la pagina.
          if (tentativo < 8) {
            attesa = setTimeout(() => carica(tentativo + 1),
                                Math.min(4000 * (tentativo + 1), 20000))
          }
        })
    }

    carica()
    // Il backend rigenera ogni 15 minuti: ricontrolliamo con lo stesso ritmo
    const timer = setInterval(() => carica(), 15 * 60 * 1000)
    return () => { vivo = false; clearInterval(timer); clearTimeout(attesa) }
  }, [])

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(session?.user ?? null)
      setAuthLoading(false)
    })
    supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null)
      if (!session) resetUser()  // logout: resetta identità PostHog
    })
  }, [])

  useEffect(() => {
    if (!user) return

    // L'identificazione parte SUBITO, prima di qualsiasi chiamata al backend.
    //
    // Prima stava dentro il .then() dell'abbonamento: se quella chiamata
    // falliva, e con Render che si addormenta dopo un quarto d'ora succede
    // spesso, l'utente restava anonimo per tutta la sessione. Nelle statistiche
    // comparivano profili senza nome che però avevano cercato titoli e
    // aggiornato notizie, cioè cose che si possono fare solo da registrati.
    // Il risultato era non riuscire a distinguere i propri utenti dagli
    // sconosciuti, che con pochi utenti è esattamente ciò che non ci si può
    // permettere.
    identifyUser(user.id, user.email)

    // L'abbonamento si continua a leggere, ma solo per sapere CHI è chi nelle
    // statistiche. Non decide più cosa uno può vedere: quello lo stabilisce
    // `isPro`, che parte acceso finché il paywall resta spento. Se un domani
    // si riaccende, basta rimettere `setIsPro(pro)` qui sotto.
    apiFetch(`/subscription/${user.id}`)
      .then(data => identifyUser(user.id, user.email,
                                 data.status === 'pro' ? 'pro' : 'free'))
      .catch(() => { /* senza risposta resta tutto aperto, come deve */ })
  }, [user])

  const handleLoad = async (tk, d, p, autoFetch = true, silenzioso = false) => {
    const res = await load(tk, d, p, silenzioso)
    setLoadedTicker(tk)
    setSidebarOpen(false)
    track('ticker_searched', { ticker: tk, days: d, period: p })

    // Ticker mai scaricato prima: invece di mostrare una schermata vuota (che
    // fa sembrare il sito rotto) scarichiamo le news al volo. Il server lavora
    // in background, quindi riproviamo a caricare due volte e poi lasciamo
    // perdere in silenzio. autoFetch=false evita di rientrare qui a catena.
    if (autoFetch && res && !res.error && res.newsCount === 0) {
      track('auto_fetch_triggered', { ticker: tk })
      await triggerFetch(tk)
      setFetching(true)
      try {
        for (const wait of [3000, 4000]) {
          await new Promise((r) => setTimeout(r, wait))
          const retry = await load(tk, d, p, true)
          if (retry && retry.newsCount > 0) break
        }
      } finally {
        setFetching(false)
      }
    }
  }

  const handleFetch = async (tk) => {
    // Fa partire una raccolta, e la raccolta passa da Groq: e' una delle due
    // porte da cui un visitatore potrebbe consumare il piano gratuito.
    if (serveAccount()) return
    track('news_refreshed', { ticker: tk })
    await triggerFetch(tk)
    setTimeout(() => handleLoad(tk, days, period, false, true), 3000)
  }

  // Aggiornamento automatico: il titolo aperto ricarica le notizie da solo
  // ogni 10 minuti. Prima bisognava premere un bottone, e un'app che aspetta
  // che tu le dica di lavorare è esattamente quello che sembra un tool.
  useEffect(() => {
    if (!loadedTicker) return
    const timer = setInterval(() => {
      // true = in silenzio: i dati a schermo restano finché non arrivano i nuovi
      load(loadedTicker, days, period, true)
    }, 10 * 60 * 1000)
    return () => clearInterval(timer)
  }, [loadedTicker, days, period, load])

  // Un titolo mai visto da nessuno si riempie da solo, la prima volta.
  //
  // L'11 agosto 2026 è saltato fuori che l'interfaccia offre 302 titoli mentre
  // la raccolta automatica oraria ne insegue 41. Gli altri 261 non sono morti,
  // perché `_termine_query` ricava il nome da Yahoo e il tasto "Aggiorna
  // notizie" funziona anche per loro. Il punto è che nessuno lo preme: chi
  // cerca JPM trova il grafico dei prezzi, un riquadro vuoto e un consiglio di
  // premere un bottone, e se ne va.
  //
  // Quindi lo si preme da soli. Una volta per titolo e per sessione, con
  // `giaProvati` a fare da guardia: se torna vuoto anche dopo il fetch vuol
  // dire che di quel titolo non si parla, e insistere sarebbe una richiesta
  // ogni dieci minuti per sempre.
  //
  // MA NON PER CHI NON HA UN ACCOUNT.
  //
  // Da quando l'applicazione si apre anche ai visitatori, questa scorciatoia
  // diventerebbe il modo più veloce di bruciare il piano gratuito di Groq:
  // uno che passa e prova tre ticker a caso fa partire tre raccolte, e le
  // raccolte costano. `/api/fetch` gli risponderebbe 401 comunque, quindi
  // sarebbero tre richieste respinte e un errore in console per niente.
  //
  // Il visitatore vede quello che c'è già in archivio, che è il punto: deve
  // capire se il prodotto gli serve, non riempirlo.
  const giaProvati = useRef(new Set())
  useEffect(() => {
    if (!user || !loadedTicker || loading || error) return
    if (news.length || giaProvati.current.has(loadedTicker)) return
    giaProvati.current.add(loadedTicker)
    handleFetch(loadedTicker)
  }, [user, loadedTicker, news.length, loading, error])

  // Vista "Oggi": il grafico si compone da solo, un punto ogni minuto.
  //
  // Aggiorna SOLO a borsa aperta. Fuori orario e nel fine settimana il
  // prezzo non si muove, quindi continuare a chiedere sarebbe traffico
  // sprecato verso Yahoo per ridisegnare la stessa identica linea. Lo stato
  // della borsa lo dice il backend, che lo legge dagli orari ufficiali di
  // quel mercato: Milano chiude alle 17:30, New York alle 22 ora nostra.
  useEffect(() => {
    if (period !== '1d' || !loadedTicker) return
    if (statoBorsa && statoBorsa.aperto === false) return

    const timer = setInterval(() => {
      refreshPrezzi(loadedTicker, '1d')
    }, 60 * 1000)
    return () => clearInterval(timer)
  }, [period, loadedTicker, statoBorsa?.aperto, refreshPrezzi])


  // Cambio mercato: azioni <-> crypto.
  //
  // Apre subito il titolo predefinito dell'altro mercato invece di lasciare a
  // schermo quello di prima, che non apparterrebbe più alla sezione scelta e
  // sarebbe la cosa più confusa possibile: header su Bitcoin, elenco di azioni.
  const cambiaMercato = (m) => {
    if (m === mercatoAttivo) return
    setMercatoAttivo(m)
    salvaMercato(m)
    track('mercato_cambiato', { mercato: m })
    const tk = PREDEFINITO[m]
    setTicker(tk)
    handleLoad(tk, days, period)
  }

  const handleUpgrade = async () => {
    // A un visitatore non si chiede la carta: prima l'account, il resto poi.
    if (serveAccount()) return
    track('upgrade_clicked', { ticker: loadedTicker, from: 'app' })
    const data = await apiFetch('/checkout', {
      method: 'POST',
      body: JSON.stringify({ email: user.email, user_id: user.id }),
    })
    if (data.url) window.location.href = data.url
  }

  const handlePDF = async () => {
    if (serveAccount()) return
    if (!isPro) { handleUpgrade(); return }
    if (!tickerInfo) return
    track('pdf_exported', { ticker: loadedTicker })
    let summary = null
    try { summary = await apiFetch(`/summary/${loadedTicker}`) } catch (_) {}
    await generateReport({ ticker, tickerInfo, stats, news, sentiment, prices, summary })
  }

  const handleExport = () => {
    if (serveAccount()) return
    if (!isPro) { handleUpgrade(); return }
    track('csv_exported', { ticker: loadedTicker })
    if (!news.length) return
    const headers = ['title', 'source', 'published_date', 'sentiment', 'sentiment_label', 'url']
    // Excel italiano si aspetta ';' e la virgola decimale; quello inglese ',' e il punto
    const isIt = lang === 'it'
    const SEP = isIt ? ';' : ','
    const esc = v => `"${(v ?? '').toString().replace(/"/g, '""')}"`
    const num = v => { const s = Number(v).toFixed(3); return isIt ? s.replace('.', ',') : s }
    const label = v => v == null ? '' : v > 0.1 ? 'bullish' : v < -0.1 ? 'bearish' : 'neutral'
    const rows = news.map(n => [
      esc(n.title),
      esc(n.source),
      esc((n.published_date || '').toString().slice(0, 10)),
      n.sentiment != null ? num(n.sentiment) : '',
      label(n.sentiment),
      esc(n.url),
    ].join(SEP))
    // BOM per gli accenti in Excel + CRLF
    const csv = String.fromCharCode(0xFEFF) + [headers.join(SEP), ...rows].join('\r\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url
    a.download = `${ticker}_sentiment_${new Date().toISOString().slice(0,10)}.csv`
    a.click(); URL.revokeObjectURL(url)
  }

  if (authLoading) return null
  // La schermata di accesso adesso si RAGGIUNGE, non si subisce: compare
  // quando la chiedi tu o quando tocchi qualcosa che ha bisogno di un account.
  if (!user && mostraAccesso) return (
    <Auth onLogin={(u) => { setUser(u); setMostraAccesso(false) }}
          onIndietro={() => setMostraAccesso(false)} />
  )
  if (showMarket) return (
    <MarketToday
      onExit={() => setShowMarket(false)}
      onPick={(tk) => { setTicker(tk); setShowMarket(false); handleLoad(tk, days, period) }}
      onUpgrade={handleUpgrade}
    />
  )

  const hasData = !!tickerInfo && !loading

  return (
    <div style={{ display: 'flex', height: stretto ? 'auto' : '100dvh',
                  minHeight: stretto ? '100dvh' : undefined,
                  overflow: stretto ? 'visible' : 'hidden',
                  background: 'var(--black)', position: 'relative' }}>
      <OnboardingTooltip hasData={hasData} />
      {/* Anche questa passa da Groq. Non si disabilita, non si mostra
          proprio: un pulsante che al primo clic chiede di registrarsi e'
          peggio di un pulsante che non c'e'. */}
      {user && (
        <ChatWidget
          ticker={loadedTicker}
          sentimentScore={stats?.avg}
          topNews={news}
        />
      )}

      {/* Overlay mobile */}
      {sidebarOpen && (
        <div onClick={() => setSidebarOpen(false)} style={{
          position: 'fixed', inset: 0, zIndex: 40,
          background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(2px)',
        }} />
      )}

      {showProfile && (
        <Profile
          user={user} isPro={isPro}
          onClose={() => setShowProfile(false)}
          onUpgrade={() => { setShowProfile(false); handleUpgrade() }}
        />
      )}

      {/* Sidebar */}
      <div style={{ position: 'relative', zIndex: 50 }}
        className={`sidebar-wrapper ${sidebarOpen ? 'sidebar-open' : ''}`}>
        {/* ticker={loadedTicker || ticker}: la riga evidenziata dev'essere
            quella aperta, non quella che stai digitando nella ricerca */}
        <Sidebar
          ticker={loadedTicker || ticker} days={days} period={period}
          mercatoAttivo={mercatoAttivo} onMercatoChange={cambiaMercato}
          hasTicker={!!loadedTicker}
          loading={loading} fetching={fetching} isPro={isPro}
          onTickerChange={setTicker} onDaysChange={setDays} onPeriodChange={setPeriod}
          onLoad={(tk, d, p) => handleLoad(tk, d, p)}
          onFetch={handleFetch} onUpgrade={handleUpgrade}
        />
      </div>

      {/* Main area */}
      <main style={{ flex: 1, display: 'flex', flexDirection: 'column',
                     overflow: stretto ? 'visible' : 'hidden',
                     height: stretto ? 'auto' : '100dvh', minWidth: 0 }}>

        {/* Header */}
        <header style={{
          height: 52, flexShrink: 0,
          borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center',
          padding: '0 16px', gap: 10,
          background: 'var(--near-black)',
        }}>
          <button onClick={() => setSidebarOpen(!sidebarOpen)} className="mobile-menu-btn"
            style={{ display: 'none', background: 'transparent', color: 'var(--muted)', padding: '4px', border: '1px solid var(--border)', borderRadius: 6, alignItems: 'center' }}>
            <Icon name="menu" size={18} />
          </button>

          {/* La ricerca sta SEMPRE nella barra: prima spariva appena aprivi un
              titolo, e per cercarne un altro dovevi tornare alla colonna. */}
          <HeaderSearch
            // Su schermo stretto il testo lungo veniva troncato a
            // "Inseris", che sembra un errore: meglio una parola sola.
            placeholder={typeof window !== 'undefined' && window.innerWidth <= 640
              ? (lang === 'it' ? 'Cerca' : 'Search') : t.header.enterTicker}
            mercatoAttivo={mercatoAttivo}
            days={days} period={period}
            copertura={copertura}
            onLoad={handleLoad} onTickerChange={setTicker}
          />

          {tickerInfo ? (
            <>
              <span style={{ fontSize: 15, fontWeight: 700, letterSpacing: '-0.01em', flexShrink: 0 }}>{tickerInfo.ticker}</span>
              <span style={{ fontSize: 13, color: 'var(--muted)', flexShrink: 0 }}>·</span>
              <span style={{ fontSize: 13, color: 'var(--muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{tickerInfo.nome}</span>

              {/* Prezzo e giudizio accanto al nome: in un terminale l'identità
                  di un titolo è ticker + prezzo + stato, non solo il nome. */}
              {prices?.length > 0 && (() => {
                const ultimo = prices[prices.length - 1]
                const primo = prices[0]
                const px = Number(ultimo?.Close ?? ultimo?.close)
                const px0 = Number(primo?.Close ?? primo?.close)
                if (!isFinite(px)) return null
                const varPct = isFinite(px0) && px0 ? ((px - px0) / px0) * 100 : null
                const su = varPct != null && varPct >= 0
                return (
                  <span className="hide-mobile" style={{
                    display: 'inline-flex', alignItems: 'baseline', gap: 7, flexShrink: 0,
                    fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums', marginLeft: 4,
                  }}>
                    <span style={{ fontSize: 14, fontWeight: 700 }}>{px.toFixed(2)}</span>
                    {varPct != null && (
                      <span style={{ fontSize: 11.5, fontWeight: 700, color: su ? 'var(--green)' : 'var(--red)' }}>
                        {su ? '+' : '−'}{Math.abs(varPct).toFixed(2)}%
                      </span>
                    )}
                  </span>
                )
              })()}

              {stats?.avg != null && (
                <span className="hide-mobile" style={{
                  fontSize: 10, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase',
                  flexShrink: 0, padding: '2px 8px', borderRadius: 5,
                  fontFamily: 'var(--mono)',
                  color: stats.avg > 0.08 ? 'var(--green)' : stats.avg < -0.08 ? 'var(--red)' : 'var(--muted)',
                  background: stats.avg > 0.08 ? 'rgba(52,211,153,0.10)' : stats.avg < -0.08 ? 'rgba(248,113,113,0.10)' : 'rgba(var(--rgb-contrasto), 0.04)',
                  border: '1px solid var(--border-br)',
                }}>
                  {stats.avg > 0 ? '+' : stats.avg < 0 ? '−' : ''}{Math.abs(stats.avg).toFixed(2)}
                </span>
              )}
            </>
          ) : null}

          {/* Finestra temporale accanto alla ricerca: riguarda ciò che stai
              guardando, quindi vive nella barra, non in una colonna laterale. */}
          {loadedTicker && (
            <div className="hide-mobile" style={{ display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0, marginLeft: 4 }}>
              {[7, 14, 30, 60, 90].map((g) => {
                const bloccato = !isPro && g > 30
                const attivo = days === g
                return (
                  <button
                    key={g}
                    onClick={() => { if (bloccato) { handleUpgrade(); return } setDays(g); handleLoad(loadedTicker, g, period) }}
                    title={bloccato ? (lang === 'it' ? 'Oltre 30 giorni è una funzione Pro' : 'Over 30 days is a Pro feature') : `${g} ${lang === 'it' ? 'giorni' : 'days'}`}
                    style={{
                      fontFamily: 'var(--mono)', fontSize: 10.5, fontWeight: 700,
                      padding: '3px 7px', borderRadius: 5,
                      border: '1px solid ' + (attivo ? 'rgba(30,92,255,0.5)' : 'var(--border)'),
                      background: attivo ? 'rgba(30,92,255,0.14)' : 'transparent',
                      color: attivo ? 'var(--azure)' : bloccato ? 'rgba(var(--rgb-contrasto), 0.22)' : 'var(--muted)',
                      cursor: 'pointer',
                    }}
                  >{g}g</button>
                )
              })}
            </div>
          )}

          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
            {/* Aggiornamento: ora è automatico ogni 10 minuti, questo serve solo
                a forzarlo subito. Icona sola, discreta, come le altre azioni. */}
            {loadedTicker && (
              <button
                onClick={() => handleFetch(loadedTicker)}
                disabled={fetching}
                className="hide-mobile"
                title={fetching ? t.sidebar.updating : t.sidebar.refreshNews}
                style={{
                  fontSize: 11, color: 'var(--muted)',
                  border: '1px solid var(--border)', borderRadius: 6,
                  padding: '4px 9px', background: 'transparent',
                  cursor: fetching ? 'default' : 'pointer',
                  display: 'inline-flex', alignItems: 'center', gap: 5,
                  opacity: fetching ? 0.5 : 1,
                }}
              >
                <span style={{
                  display: 'inline-block',
                  animation: fetching ? 'spin 1s linear infinite' : 'none',
                }}><Icon name="recent" size={12} /></span>
              </button>
            )}
            {news.length > 0 && (
              <>
                <button onClick={handlePDF} className="hide-mobile" style={{
                  fontSize: 11, color: isPro ? 'var(--muted)' : 'rgba(var(--rgb-contrasto), 0.2)',
                  border: '1px solid var(--border)', borderRadius: 6,
                  padding: '4px 10px', background: 'transparent', cursor: 'pointer',
                  display: 'inline-flex', alignItems: 'center', gap: 5,
                }}>
                  <Icon name={isPro ? 'pdf' : 'lock'} size={12} /> PDF
                </button>
                <button onClick={handleExport} className="hide-mobile" style={{
                  fontSize: 11, color: isPro ? 'var(--muted)' : 'rgba(var(--rgb-contrasto), 0.2)',
                  border: '1px solid var(--border)', borderRadius: 6,
                  display: 'inline-flex', alignItems: 'center', gap: 5,
                  padding: '4px 10px', background: 'transparent', cursor: 'pointer',
                }}>
                  <Icon name={isPro ? 'csv' : 'lock'} size={12} /> CSV
                </button>
              </>
            )}
            {loading && <Spinner />}
            {fetching && <Spinner color="var(--azure)" />}
            {/* Qui c'erano il distintivo PRO e il pulsante per abbonarsi.
                Con il paywall spento sono spariti entrambi, e per due motivi
                diversi: il pulsante perché non c'è più niente da comprare, il
                distintivo perché un contrassegno che hanno TUTTI non distingue
                nessuno e occupa spazio in una barra già affollata.
                Riaccendendo il paywall vanno rimessi (stanno nella storia di
                git, e le traduzioni t.header.pro / t.header.upgradePro sono
                rimaste al loro posto). */}
            {/* "Mercato" rimosso: la schermata iniziale È il mercato, il bottone
                mostrava la stessa cosa due volte. L'Academy è stata tolta
                dall'interfaccia perché fuori fuoco rispetto al prodotto: il
                codice è stato rimosso: si recupera dalla storia di git. */}
            <a href="https://cheruvo.com/guida.html" target="_blank" rel="noreferrer" className="hide-mobile" title={lang === 'it' ? 'Guida all\'uso' : 'User guide'} style={{
              display: 'inline-flex', alignItems: 'center', textDecoration: 'none',
              fontSize: 11, color: 'var(--white)', background: 'transparent',
              border: '1px solid var(--border)', borderRadius: 6, padding: '4px 10px',
              cursor: 'pointer', fontWeight: 500,
            }}><Icon name="book" size={13} /> {lang === 'it' ? 'Guida' : 'Guide'}</a>
            <BottoneTema lang={lang} />
            <BottoneSchermoIntero lang={lang} />
            <button onClick={toggleLang} className="hide-mobile" style={{
              fontSize: 13, background: 'transparent', border: '1px solid var(--border)',
              borderRadius: 6, padding: '3px 7px', cursor: 'pointer', lineHeight: 1,
            }}>
              {lang === 'it' ? '🇮🇹' : '🇬🇧'}
            </button>

            {/* Menu opzioni — solo mobile: raccoglie export, viste e lingua */}
            <div className="mobile-only" style={{ position: 'relative' }}>
              <button onClick={() => setShowHeaderMenu(v => !v)} aria-label="Menu opzioni" style={{
                color: 'var(--white)', background: 'transparent',
                border: '1px solid var(--border)', borderRadius: 6, padding: '4px 8px',
                cursor: 'pointer', display: 'inline-flex', alignItems: 'center',
              }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                  <circle cx="12" cy="5" r="1.9" /><circle cx="12" cy="12" r="1.9" /><circle cx="12" cy="19" r="1.9" />
                </svg>
              </button>
              {showHeaderMenu && (() => {
                const close = () => setShowHeaderMenu(false)
                const item = {
                  display: 'flex', alignItems: 'center', gap: 10, width: '100%',
                  padding: '10px 12px', borderRadius: 8, fontSize: 13, color: 'var(--white)',
                  background: 'transparent', border: 'none', cursor: 'pointer',
                  textAlign: 'left', textDecoration: 'none', fontFamily: 'var(--sans)',
                }
                return (
                  <>
                    <div onClick={close} style={{ position: 'fixed', inset: 0, zIndex: 98 }} />
                    <div style={{
                      position: 'absolute', top: 'calc(100% + 8px)', right: 0, zIndex: 99,
                      background: 'var(--dark2)', border: '1px solid var(--border-br)',
                      borderRadius: 12, padding: 6, minWidth: 195,
                      boxShadow: '0 14px 40px rgba(0,0,0,0.55)',
                      display: 'flex', flexDirection: 'column', gap: 2,
                    }}>
                      {news.length > 0 && (
                        <>
                          <button onClick={() => { close(); handlePDF() }} style={item}>
                            <Icon name={isPro ? 'pdf' : 'lock'} size={14} /> {lang === 'it' ? 'Report PDF' : 'PDF report'}
                          </button>
                          <button onClick={() => { close(); handleExport() }} style={item}>
                            <Icon name={isPro ? 'csv' : 'lock'} size={14} /> {lang === 'it' ? 'Esporta CSV' : 'Export CSV'}
                          </button>
                        </>
                      )}
                      {/* Mercato tolto anche dal menu mobile: la schermata iniziale È il mercato */}
                      <a href="https://cheruvo.com/guida.html" target="_blank" rel="noreferrer" onClick={close} style={item}>
                        <Icon name="book" size={14} /> {lang === 'it' ? 'Guida' : 'Guide'}
                      </a>
                      <button onClick={() => { close(); toggleLang() }} style={item}>
                        <span style={{ fontSize: 14, lineHeight: 1 }}>{lang === 'it' ? '🇬🇧' : '🇮🇹'}</span> {lang === 'it' ? 'English' : 'Italiano'}
                      </button>
                    </div>
                  </>
                )
              })()}
            </div>

            {user ? (
              <div onClick={() => setShowProfile(true)} title={user.email} style={{
                width: 28, height: 28, borderRadius: '50%', background: 'var(--blue)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 12, fontWeight: 600, cursor: 'pointer', flexShrink: 0,
              }}>
                {user.email?.[0].toUpperCase()}
              </div>
            ) : (
              <button onClick={() => setMostraAccesso(true)} style={{
                height: 28, padding: '0 12px', borderRadius: 14,
                background: 'var(--blue)', color: '#fff', border: 'none',
                fontSize: 12, fontWeight: 600, cursor: 'pointer', flexShrink: 0,
              }}>
                Entra
              </button>
            )}
          </div>
        </header>

        {/* Dice al visitatore dove si trova.
            Elenca quello che gli manca DAVVERO, cioè le cose legate a un
            account. Una prima versione diceva "vedi 7 giorni invece di 30",
            che oltre a essere una decisione di prodotto presa di straforo
            non era nemmeno vera: i dati sono gli stessi per tutti. */}
        {!user && (
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            gap: 10, flexWrap: 'wrap', padding: '7px 12px',
            background: 'var(--near-black)', borderBottom: '1px solid var(--border)',
            fontSize: 12.5, color: 'var(--dim)',
          }}>
            <span>
              Stai guardando senza account. I dati sono gli stessi: con un
              account hai watchlist, alert ed export.
            </span>
            <button onClick={() => setMostraAccesso(true)} style={{
              background: 'none', border: '1px solid var(--border)', borderRadius: 12,
              color: 'var(--text)', fontSize: 12, padding: '2px 10px', cursor: 'pointer',
            }}>
              Entra, è gratis
            </button>
          </div>
        )}

        {/* Nastro ticker: il primo segno che l'applicazione è viva */}
        <TickerStrip rows={righeFiltrate(mercato?.rows)} onPick={(tk) => { setTicker(tk); handleLoad(tk, days, period) }} />

        {/* Corpo + colonna di mercato sempre visibile a destra */}
        <div style={{ flex: 1, display: 'flex', minHeight: 0,
                      overflow: stretto ? 'visible' : 'hidden' }}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0,
                      overflow: stretto ? 'visible' : 'hidden' }}>

        {/* ── Content area ── */}
        {mercatoAttivo === 'azioni' && azioniChiuse ? (
          <SezioneAzioni lang={lang} onVaiACrypto={() => cambiaMercato('crypto')} />
        ) : (
        <>
        {!hasData && !error ? (
          /* Empty / loading state — full width */
          <div style={{ flex: 1, overflowY: stretto ? 'visible' : 'auto',
                        padding: stretto ? '14px 12px' : '20px 20px' }}>
            {error && <ErrorBanner msg={error} />}
            {!loading && !error && (
              <EmptyState t={t} onLoad={handleLoad} days={days} period={period}
                mercato={mercato && { ...mercato, rows: righeFiltrate(mercato.rows) }}
                mktStats={mktStats} risveglio={risveglio} mercatoAttivo={mercatoAttivo} />
            )}
            {loading && <LoadingState />}
          </div>
        ) : (
          /* Two-column dashboard */
          <div style={{ flex: 1, overflow: stretto ? 'visible' : 'hidden',
                        display: 'flex', flexDirection: 'column', minHeight: 0 }}>

          {/* Striscia metriche a tutta larghezza, subito sotto l'intestazione:
              è la fascia di riepilogo del titolo, come in un terminale. Prima
              stava dentro la colonna da 380px, dove sembrava un widget fra i
              tanti invece che l'identità numerica del titolo. */}
          {/* Su telefono il prezzo apre la schermata. Su desktop questo
              blocco non compare (classe mobile-only) perché lassù il prezzo
              sta già nella barra in alto. */}
          <PrezzoMobile ticker={loadedTicker || ticker} tickerInfo={tickerInfo}
                        prices={prices} statoBorsa={statoBorsa} />

          {stats && <div id="kpi-avg"><KPIGrid stats={stats} /></div>}

          {/* Solo sulle crypto: l'indice riguarda quel mercato, su un
              titolo azionario sarebbe un numero fuori posto. Riceve anche il
              NOSTRO sentiment, così può mostrare la distanza fra i due. */}
          {eCrypto(loadedTicker) && (
            <div style={{ padding: "12px 20px 0" }}>
              <PauraAvidita sentimentNostro={stats?.avg ?? null} lang={lang} />
            </div>
          )}

          {/* Una colonna sola, come in un terminale: prima il grafico, poi il
              flusso notizie, e sotto il commento AI e gli approfondimenti.
              Prima erano due colonne affiancate e lo sguardo doveva scegliere
              da che parte cominciare. */}
          <div className="dashboard-grid" style={{ flex: 1,
                        overflowY: stretto ? 'visible' : 'auto',
                        display: 'flex', flexDirection: 'column', minHeight: 0 }}>

            {/* ── Commento AI e approfondimenti: sotto i dati ── */}
            <div style={{
              order: 2, padding: '4px 20px 20px',
              display: 'flex', flexDirection: 'column', gap: 16,
            }}>
              {error && <ErrorBanner msg={error} />}

              {/* AI Summary */}
              {loadedTicker && (
                <SummaryCard ticker={loadedTicker} isPro={isPro} haAccount={!!user}
                             onUpgrade={handleUpgrade} />
              )}

              {/* Stats PRO — collassabili */}
              {news.length > 0 && isPro && (
                <div>
                  <button
                    onClick={() => setShowStats(s => !s)}
                    style={{
                      width: '100%', display: 'flex', justifyContent: 'space-between',
                      alignItems: 'center', padding: '10px 14px',
                      background: 'rgba(var(--rgb-contrasto), 0.02)', border: '1px solid var(--border)',
                      borderRadius: 8, cursor: 'pointer', fontSize: 12,
                      color: 'var(--muted)', marginBottom: showStats ? 12 : 0,
                    }}
                  >
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><Icon name="analytics" size={13} /> Analytics avanzate</span>
                    <Icon name="chevron-down" size={14} style={{ transition: 'transform .2s', transform: showStats ? 'rotate(180deg)' : 'none' }} />
                  </button>
                  {showStats && <Stats news={news} />}
                </div>
              )}

              {/* Upgrade banner FREE */}
              {news.length > 0 && !isPro && (
                <div style={{
                  background: 'rgba(30,92,255,0.04)', border: '1px solid rgba(30,92,255,0.15)',
                  borderRadius: 10, padding: '16px',
                }}>
                  <div style={{ fontSize: 13, color: 'var(--white)', marginBottom: 6, fontWeight: 500 }}>
                    {t.main.advancedTitle}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 12, lineHeight: 1.6 }}>
                    {t.main.advancedDesc}
                  </div>
                  <button onClick={handleUpgrade} style={{
                    background: 'var(--blue)', color: 'white', border: 'none',
                    borderRadius: 7, padding: '8px 18px', fontSize: 13,
                    fontWeight: 500, cursor: 'pointer', width: '100%',
                  }}>{t.main.upgradeBtn}</button>
                </div>
              )}

              <div style={{ height: 8 }} />
            </div>

            {/* ── Dati: grafico e notizie, per primi ── */}
            <div style={{ order: 1, padding: '16px 20px 4px', display: 'flex', flexDirection: 'column', gap: 16 }}>

              {/* Grafico dentro un pannello con intestazione a barra, come
                  nel resto dell'interfaccia: etichetta in maiuscoletto a
                  sinistra, contesto a destra, bordi netti da un pixel. */}
              {/* Niente `overflow: hidden` su questo pannello.
                  C'era, e serviva solo a far rispettare gli angoli arrotondati
                  alla barra d'intestazione, che ha un fondo pieno. Però
                  tagliava anche il tooltip del grafico sentiment: quel grafico
                  è alto 120px e sta in fondo al pannello, quindi qualunque
                  tooltip più alto di così finiva mozzato a metà frase.
                  L'arrotondamento adesso se lo fa la barra da sola. */}
              {(prices.length > 0 || news.length > 0) && (
                <div style={{ border: '1px solid var(--border-br)', borderRadius: 8 }}>
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 10, padding: '7px 12px',
                    background: 'var(--near-black)', borderBottom: '1px solid var(--border)',
                    borderRadius: '7px 7px 0 0',
                  }}>
                    <span style={{ fontSize: 10, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--muted)', fontWeight: 700 }}>
                      {/* Prima qui c'era "· {days} giorni", che però è la finestra
                          delle NOTIZIE, non quella dei prezzi: si leggeva
                          "30 giorni" con il grafico impostato su 3M. I due
                          selettori sono entrambi visibili e bastano da soli. */}
                      {lang === 'it' ? 'Prezzo e sentiment' : 'Price and sentiment'}
                    </span>
                    {/* Periodo dei prezzi: sta qui perché è il grafico che
                        governa, non la colonna laterale. 6M e 1A restano Pro. */}
                    <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div style={{ display: 'flex', gap: 3 }}>
                        {/* "Oggi" è la vista al minuto: resta gratuita perché è
                            l'unica cosa che si muove sotto gli occhi, e
                            nasconderla dietro il Pro vorrebbe dire nascondere
                            proprio il motivo per cui uno torna. */}
                        {[['1d','OGGI'], ['1mo','1M'], ['3mo','3M'], ['6mo','6M'], ['1y','1A']].map(([v, etichetta]) => {
                          const bloccato = !isPro && (v === '6mo' || v === '1y')
                          const attivo = period === v
                          return (
                            <button
                              key={v}
                              onClick={() => { if (bloccato) { handleUpgrade(); return } setPeriod(v); handleLoad(loadedTicker || ticker, days, v) }}
                              title={bloccato ? (lang === 'it' ? 'Funzione Pro' : 'Pro feature') : etichetta}
                              style={{
                                fontFamily: 'var(--mono)', fontSize: 10, fontWeight: 700,
                                padding: '2px 7px', borderRadius: 4,
                                border: '1px solid ' + (attivo ? 'rgba(30,92,255,0.5)' : 'var(--border)'),
                                background: attivo ? 'rgba(30,92,255,0.14)' : 'transparent',
                                color: attivo ? 'var(--azure)' : bloccato ? 'rgba(var(--rgb-contrasto), 0.22)' : 'var(--muted)',
                                cursor: 'pointer',
                              }}
                            >{etichetta}</button>
                          )
                        })}
                      </div>
                      <div className="hide-mobile" style={{ display: 'flex', gap: 6 }}>
                        <Legend color="var(--azure)"  label={t.main.price} />
                        <Legend color="var(--green)"  label={t.main.positive} />
                        <Legend color="var(--red)"    label={t.main.negative} />
                      </div>
                    </div>
                  </div>
                  <div id="chart-area" style={{ padding: '12px 14px 6px' }}>
                    {/* loadedTicker, non ticker: il primo è il titolo che sta
                        DAVVERO a schermo, il secondo è quello che stai
                        scrivendo nella ricerca. Usando ticker, l'etichetta del
                        grafico annunciava NVDA mentre i dati erano di AMZN. */}
                    <Chart prices={prices} sentiment={sentiment} ticker={loadedTicker || ticker} stats={stats}
                      intraday={period === '1d'} statoBorsa={statoBorsa} />
                  </div>
                </div>
              )}

              {/* No news notice */}
              {tickerInfo && !loading && !news.length && !error && (
                <div style={{
                  background: 'rgba(96,165,250,0.06)', border: '1px solid rgba(96,165,250,0.15)',
                  borderRadius: 12, padding: '24px', textAlign: 'center',
                }}>
                  {/* Se la ricerca automatica è appena partita si dice quello,
                      invece di consigliare un bottone che si sta già premendo
                      da solo. Il consiglio resta per il secondo giro, quando
                      vuol dire che di questo titolo non si è trovato niente. */}
                  {giaProvati.current.has(loadedTicker) ? (
                    <>
                      <div style={{ fontSize: 14, color: 'var(--azure)', marginBottom: 8 }}>{t.main.noNews}</div>
                      {/* PERCHE' e' vuoto, non solo che e' vuoto.
                          Chi arriva qui ha scelto un nome dalla lista dei 302
                          o l'ha scritto a mano, e senza questa riga pensa che
                          il prodotto sia rotto invece che non seguire quel
                          titolo. Il 17 agosto 2026 la sessione piu' attiva
                          mai registrata ha scritto ADIL e BB, che nella
                          lista non ci sono nemmeno. */}
                      {offriScarico(statoCopertura(copertura, loadedTicker)) && (
                        <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 8 }}>
                          {lang === 'it'
                            ? 'Questo titolo non è fra quelli raccolti di continuo, quindi in archivio non c\'è niente di suo.'
                            : 'This ticker is not one of those collected continuously, so there is nothing of its own in the archive.'}
                        </div>
                      )}
                      <button
                        onClick={() => handleFetch(loadedTicker)}
                        disabled={fetching}
                        style={{
                          fontSize: 12.5, padding: '7px 14px', borderRadius: 7,
                          border: '1px solid var(--border-br)',
                          background: 'rgba(var(--rgb-contrasto), 0.04)',
                          color: 'var(--white)',
                          cursor: fetching ? 'default' : 'pointer',
                          opacity: fetching ? 0.6 : 1,
                        }}
                      >
                        {fetching ? t.sidebar.updating : t.main.refreshNews}
                      </button>
                      <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 8 }}>
                        {lang === 'it'
                          ? 'Cerca adesso su questo titolo. Può non trovare niente.'
                          : 'Searches for this ticker now. It may find nothing.'}
                      </div>
                    </>
                  ) : (
                    <div style={{ fontSize: 14, color: 'var(--azure)' }}>
                      {lang === 'it'
                        ? 'Sto cercando le notizie su questo titolo…'
                        : 'Looking for news on this ticker…'}
                    </div>
                  )}
                </div>
              )}

              {/* Flusso notizie subito sotto il grafico: sono le due cose che
                  si guardano davvero, il resto è approfondimento. */}
              {news.length > 0 && (
                <div id="top-news">
                  <TopNews news={news} isPro={isPro} onUpgrade={handleUpgrade} />
                </div>
              )}

              {/* Confronto multi-ticker */}
              {sentiment.length > 0 && (
                <ComparePanel
                  primaryTicker={ticker}
                  primarySentiment={sentiment}
                  isPro={isPro}
                  onUpgrade={handleUpgrade}
                />
              )}

              {/* Correlazione sentiment/prezzo */}
              {prices.length > 0 && sentiment.length > 0 && (
                <CorrelationPanel
                  prices={prices}
                  sentiment={sentiment}
                  isPro={isPro}
                  onUpgrade={handleUpgrade}
                />
              )}

              <div style={{ height: 12 }} />
            </div>
          </div>
          </div>
        )}
        </>
        )}

        </div>
        {/* La colonna destra compare solo quando sei dentro un titolo. Nella
            schermata iniziale il centro mostra già "Più rialzisti / Più
            ribassisti": tenerla accesa significava stampare la stessa
            classifica due volte, affiancata a sé stessa. */}
        {hasData && (
          <MarketRail
            rows={righeFiltrate(mercato?.rows)} stats={mktStats} attivo={loadedTicker}
            onPick={(tk) => { setTicker(tk); handleLoad(tk, days, period) }}
          />
        )}
        </div>

        <StatusBar stats={mktStats} updatedAt={mercato?.updated_at} />
      </main>
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

// ── Ricerca ticker nell'header (con suggerimenti, come la sidebar) ─────────
function HeaderSearch({ placeholder, days, period, onLoad, onTickerChange, mercatoAttivo, copertura }) {
  const [q, setQ] = useState('')
  const [sugg, setSugg] = useState([])
  const [open, setOpen] = useState(false)
  const campo = useRef(null)
  const { lang } = useLang()

  // Ctrl+K (o Cmd+K) porta il cursore qui da qualunque punto dell'app: è il
  // gesto che chi usa strumenti professionali si aspetta di trovare.
  useEffect(() => {
    const tasto = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        campo.current?.focus()
        campo.current?.select()
      }
    }
    window.addEventListener('keydown', tasto)
    return () => window.removeEventListener('keydown', tasto)
  }, [])

  const change = (e) => {
    const v = e.target.value.toUpperCase()
    setQ(v)
    if (v.length >= 1) {
      const f = TICKERS.filter(tk =>
        (tk.symbol.startsWith(v) || tk.name.toUpperCase().includes(v)) &&
        nelMercato(tk.symbol, mercatoAttivo)
      ).slice(0, 6)
      setSugg(f)
      setOpen(f.length > 0)
    } else {
      setOpen(false)
    }
  }

  const go = (sym) => {
    const v = (sym || q).trim().toUpperCase()
    if (!v) return
    setOpen(false)
    setQ(v)
    onTickerChange?.(v)
    onLoad(v, days, period)
  }

  return (
    /* id usato dal tour del primo accesso per sapere dove puntare */
    <div id="header-search" style={{ position: 'relative', flex: 1, maxWidth: 380, minWidth: 0 }}>
      <input
        ref={campo}
        value={q}
        onChange={change}
        onKeyDown={e => { if (e.key === 'Enter') go(); if (e.key === 'Escape') { setOpen(false); e.currentTarget.blur() } }}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onFocus={() => q.length >= 1 && setOpen(sugg.length > 0)}
        placeholder={placeholder}
        style={{
          width: '100%', background: 'var(--dark)',
          border: '1px solid var(--border-br)', color: 'var(--white)',
          borderRadius: 7, padding: '7px 52px 7px 12px', fontSize: 13,
          outline: 'none', fontFamily: 'var(--sans)',
        }}
      />
      {/* Promemoria della scorciatoia, come nei terminali */}
      <span className="hide-mobile" style={{
        position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)',
        fontFamily: 'var(--mono)', fontSize: 9.5, color: 'var(--muted)',
        border: '1px solid var(--border-br)', borderRadius: 4,
        padding: '1px 5px', pointerEvents: 'none', letterSpacing: '.04em',
      }}>Ctrl K</span>
      {open && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 6px)', left: 0, right: 0,
          background: 'var(--dark)', border: '1px solid var(--border)',
          borderRadius: 8, zIndex: 100, overflow: 'hidden',
          boxShadow: 'var(--ombra)',
        }}>
          {sugg.map(tk => {
            // Quanto c'è dietro questo nome, detto PRIMA del clic. Finché il
            // dato non è arrivato l'etichetta è vuota: uno "0 notizie"
            // mostrato per un secondo fa scartare un titolo che ne ha novanta.
            const c = statoCopertura(copertura, tk.symbol)
            const etichetta = etichettaCopertura(c, lang)
            return (
            <div
              key={tk.symbol}
              onMouseDown={() => go(tk.symbol)}
              style={{
                padding: '9px 12px', fontSize: 13, cursor: 'pointer',
                display: 'flex', gap: 8, alignItems: 'baseline',
              }}
            >
              {eCrypto(tk.symbol) && <LogoCrypto ticker={tk.symbol} size={15} />}
              <b>{eCrypto(tk.symbol) ? tk.symbol.replace('-USD', '') : tk.symbol}</b>
              <span style={{ color: 'var(--muted)', fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{tk.name}</span>
              {etichetta && (
                <span style={{
                  marginLeft: 'auto', flexShrink: 0, display: 'flex',
                  alignItems: 'center', gap: 5,
                  fontFamily: 'var(--mono)', fontSize: 10,
                  color: c.stato === PIENA ? 'var(--white)' : 'var(--muted)',
                }}>
                  <span style={{
                    width: 5, height: 5, borderRadius: '50%',
                    background: coloreCopertura(c.stato),
                    // Il vuoto ha il cerchio solo contornato: si distingue
                    // dallo scarso anche senza leggere il testo.
                    boxShadow: c.stato === VUOTA
                      ? 'inset 0 0 0 1px var(--muted)' : 'none',
                  }} />
                  {etichetta}
                </span>
              )}
            </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── Tema chiaro / scuro ───────────────────────────────────────────────────
// La scelta viene scritta su <html data-tema="...">, e da lì tutto il resto
// segue le variabili CSS. Al primo accesso non decidiamo noi: seguiamo
// l'impostazione del sistema operativo, perché chi tiene il computer in
// chiaro non si aspetta di trovarsi una schermata nera in faccia.
export function applicaTemaSalvato() {
  try {
    // Si parte SEMPRE dallo scuro, anche se il sistema operativo è in chiaro.
    // Cheruvo è nato come plancia da terminale finanziario e quello è il suo
    // aspetto: il chiaro è un'alternativa che si sceglie, non il punto di
    // partenza. Una volta scelto, la preferenza resta.
    const salvato = localStorage.getItem('cheruvo_tema')
    document.documentElement.setAttribute('data-tema', salvato || 'scuro')
  } catch (_) {
    document.documentElement.setAttribute('data-tema', 'scuro')
  }
}

function BottoneTema({ lang }) {
  const [tema, setTema] = useState(
    () => (typeof document !== 'undefined'
      && document.documentElement.getAttribute('data-tema')) || 'scuro'
  )

  const commuta = () => {
    const nuovo = tema === 'scuro' ? 'chiaro' : 'scuro'
    setTema(nuovo)
    document.documentElement.setAttribute('data-tema', nuovo)
    try { localStorage.setItem('cheruvo_tema', nuovo) } catch (_) {}
    track('tema_cambiato', { tema: nuovo })
  }

  const etichetta = tema === 'scuro'
    ? (lang === 'it' ? 'Passa al tema chiaro' : 'Switch to light theme')
    : (lang === 'it' ? 'Passa al tema scuro' : 'Switch to dark theme')

  return (
    <button onClick={commuta} title={etichetta} aria-label={etichetta}
      className="hide-mobile" style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        background: 'transparent', border: '1px solid var(--border)',
        borderRadius: 6, padding: '4px 8px', cursor: 'pointer',
        color: 'var(--white)', lineHeight: 1,
      }}>
      <svg width="13" height="13" viewBox="0 0 16 16" fill="none"
        stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        {tema === 'scuro' ? (
          /* luna: sei nel tema scuro */
          <path d="M13.5 9.5A5.6 5.6 0 0 1 6.5 2.5a5.8 5.8 0 1 0 7 7Z" />
        ) : (
          /* sole: sei nel tema chiaro */
          <>
            <circle cx="8" cy="8" r="3" />
            <path d="M8 1v1.5M8 13.5V15M1 8h1.5M13.5 8H15M3 3l1 1M12 12l1 1M13 3l-1 1M4 12l-1 1" />
          </>
        )}
      </svg>
    </button>
  )
}

// ── Schermo intero ────────────────────────────────────────────────────────
// Usa l'API del browser, la stessa di F11. Lo stato non si tiene in memoria
// ma si legge da document.fullscreenElement e si aggiorna sull'evento: se
// l'utente esce con Esc o con F11 l'icona resta comunque coerente. Tenendo un
// useState scollegato dall'evento, l'icona finirebbe per mentire.
function BottoneSchermoIntero({ lang }) {
  const [pieno, setPieno] = useState(false)
  const [disponibile] = useState(
    () => typeof document !== 'undefined' && !!document.documentElement.requestFullscreen
  )

  useEffect(() => {
    const cambio = () => setPieno(!!document.fullscreenElement)
    document.addEventListener('fullscreenchange', cambio)
    return () => document.removeEventListener('fullscreenchange', cambio)
  }, [])

  // Safari su iPhone non espone l'API: meglio non mostrare un tasto che non fa nulla.
  if (!disponibile) return null

  const commuta = async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen()
      else await document.documentElement.requestFullscreen()
    } catch (_) {
      // Alcuni browser rifiutano se la richiesta non parte da un click:
      // qui parte da un click, ma se rifiutano lasciamo perdere in silenzio.
    }
  }

  const etichetta = pieno
    ? (lang === 'it' ? 'Esci da schermo intero (Esc)' : 'Exit full screen (Esc)')
    : (lang === 'it' ? 'Schermo intero' : 'Full screen')

  return (
    <button onClick={commuta} title={etichetta} aria-label={etichetta}
      className="hide-mobile" style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        background: 'transparent', border: '1px solid var(--border)',
        borderRadius: 6, padding: '4px 8px', cursor: 'pointer',
        color: 'var(--white)', lineHeight: 1,
      }}>
      <svg width="13" height="13" viewBox="0 0 16 16" fill="none"
        stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        {pieno ? (
          /* frecce che rientrano */
          <>
            <path d="M6.5 1.5v5h-5" /><path d="M9.5 14.5v-5h5" />
            <path d="M14.5 6.5h-5v-5" /><path d="M1.5 9.5h5v5" />
          </>
        ) : (
          /* frecce che escono verso i quattro angoli */
          <>
            <path d="M1.5 5.5v-4h4" /><path d="M14.5 10.5v4h-4" />
            <path d="M10.5 1.5h4v4" /><path d="M5.5 14.5h-4v-4" />
          </>
        )}
      </svg>
    </button>
  )
}

function Spinner({ color = 'var(--muted)' }) {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" style={{ animation: 'spin 0.8s linear infinite' }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <circle cx="7" cy="7" r="5.5" stroke={color} strokeWidth="1.5" strokeDasharray="20 14" strokeLinecap="round"/>
    </svg>
  )
}

function Legend({ color, label }) {
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--muted)' }}>
      <span style={{ width: 8, height: 8, background: color, borderRadius: 2, display: 'inline-block', opacity: 0.8 }}/>
      {label}
    </span>
  )
}

function ErrorBanner({ msg }) {
  return (
    <div style={{
      background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)',
      borderRadius: 10, padding: '12px 16px', fontSize: 13, color: 'var(--red)',
    }}>{msg}</div>
  )
}

function LoadingState() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh', gap: 10, color: 'var(--muted)', fontSize: 13 }}>
      <svg width="16" height="16" viewBox="0 0 14 14" fill="none" style={{ animation: 'spin 0.8s linear infinite' }}>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        <circle cx="7" cy="7" r="5.5" stroke="var(--muted)" strokeWidth="1.5" strokeDasharray="20 14" strokeLinecap="round"/>
      </svg>
      Caricamento...
    </div>
  )
}

// Suggerimenti di partenza, diversi per mercato: proporre NVIDIA dentro la
// sezione crypto mandava l'utente fuori dalla sezione in cui si trovava.
const SUGGERITI = {
  azioni: [
    { symbol: 'NVDA',    name: 'NVIDIA',    flag: '🇺🇸' },
    { symbol: 'AAPL',    name: 'Apple',     flag: '🇺🇸' },
    { symbol: 'TSLA',    name: 'Tesla',     flag: '🇺🇸' },
    { symbol: 'ENI.MI',  name: 'Eni',       flag: '🇮🇹' },
    { symbol: 'MSFT',    name: 'Microsoft', flag: '🇺🇸' },
    { symbol: 'ENEL.MI', name: 'Enel',      flag: '🇮🇹' },
  ],
  crypto: [
    { symbol: 'BTC-USD',  name: 'Bitcoin',   flag: '' },
    { symbol: 'ETH-USD',  name: 'Ethereum',  flag: '' },
    { symbol: 'SOL-USD',  name: 'Solana',    flag: '' },
    { symbol: 'XRP-USD',  name: 'XRP',       flag: '' },
    { symbol: 'DOGE-USD', name: 'Dogecoin',  flag: '' },
    { symbol: 'LINK-USD', name: 'Chainlink', flag: '' },
  ],
}

// ── Schermata iniziale: una PLANCIA, non un cartello di benvenuto ───────────
// Prima qui c'era un orb animato con "Benvenuto": bello ma vuoto, e faceva
// sembrare Cheruvo un tool in attesa di comandi. Ora chi apre l'app vede
// subito lo stato del mercato, come in un terminale professionale.

// Numeri sempre monospaziati e tabulari: è il dettaglio che più distingue
// un terminale finanziario da un sito qualsiasi.
const numStyle = {
  fontFamily: 'var(--mono, ui-monospace, monospace)',
  fontVariantNumeric: 'tabular-nums',
  fontWeight: 700,
}
const segno = (v) => (v > 0.08 ? 'var(--green, #2ee6a8)' : v < -0.08 ? 'var(--red, #f87171)' : 'var(--muted)')
const fmt = (v) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(Number(v)).toFixed(2)}`

function Pannello({ titolo, extra, children }) {
  return (
    <div style={{
      border: '1px solid var(--border-br)', borderRadius: 10,
      background: 'rgba(var(--rgb-contrasto), 0.015)', overflow: 'hidden',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '8px 12px', borderBottom: '1px solid var(--border-br)',
        background: 'rgba(var(--rgb-contrasto), 0.02)',
      }}>
        <span style={{ fontSize: 10.5, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--muted)', fontWeight: 700 }}>
          {titolo}
        </span>
        {extra && <span style={{ fontSize: 10.5, color: 'var(--muted)', ...numStyle, fontWeight: 500 }}>{extra}</span>}
      </div>
      {children}
    </div>
  )
}

function EmptyState({ t, onLoad, days, period, mercato, mktStats, risveglio, mercatoAttivo = 'crypto' }) {
  const cripto = mercatoAttivo === 'crypto'
  const { lang } = useLang()
  // I dati arrivano già da App: una sola chiamata condivisa con nastro,
  // colonna destra e barra di stato, invece di quattro richieste uguali.
  const stats = mktStats
  const errore = mercato === null && mktStats === null ? false : !mercato

  const righe = mercato?.rows || []
  const rialzisti = righe.filter((r) => r.sentiment > 0).slice(0, 6)
  const ribassisti = righe.filter((r) => r.sentiment <= 0).slice(-6).reverse()
  const ora = mercato?.updated_at
    ? new Date(mercato.updated_at).toLocaleTimeString(lang === 'it' ? 'it-IT' : 'en-US', { hour: '2-digit', minute: '2-digit' })
    : null

  const Riga = ({ r, i }) => (
    <button
      onClick={() => onLoad(r.ticker, days, period)}
      style={{
        display: 'grid', gridTemplateColumns: '18px 1fr auto auto', gap: 10,
        alignItems: 'center', width: '100%', padding: '7px 12px',
        borderBottom: '1px solid var(--border-br)', background: 'transparent',
        border: 'none', borderRadius: 0, cursor: 'pointer', textAlign: 'left',
        color: 'var(--white)', fontSize: 13,
      }}
      onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(var(--rgb-contrasto), 0.04)' }}
      onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
    >
      <span style={{ ...numStyle, fontWeight: 500, fontSize: 10.5, color: 'var(--muted)' }}>{i + 1}</span>
      <span style={{ fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: 5 }}>
        {eCrypto(r.ticker) && <LogoCrypto ticker={r.ticker} size={14} />}
        {eCrypto(r.ticker) ? r.ticker.replace('-USD', '') : r.ticker}
      </span>
      <span style={{ fontSize: 10.5, color: 'var(--muted)' }}>{r.news} {t.empty.newsShort}</span>
      <span style={{ ...numStyle, color: segno(r.sentiment) }}>{fmt(r.sentiment)}</span>
    </button>
  )

  const Metrica = ({ etichetta, valore }) => (
    <div style={{ padding: '10px 14px', borderRight: '1px solid var(--border-br)', flex: 1, minWidth: 110 }}>
      <div style={{ fontSize: 10, letterSpacing: '0.11em', textTransform: 'uppercase', color: 'var(--muted)', fontWeight: 700 }}>
        {etichetta}
      </div>
      <div style={{ ...numStyle, fontSize: 18, marginTop: 3 }}>{valore ?? '—'}</div>
    </div>
  )

  return (
    <div style={{ flex: 1, overflow: 'auto', padding: '18px 20px 28px' }}>
      {/* intestazione */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap', marginBottom: 14 }}>
        <h2 style={{ fontFamily: 'var(--serif)', fontSize: 21, fontWeight: 400, letterSpacing: '-0.01em' }}>
          {t.empty.boardTitle}
        </h2>
        <span style={{ fontSize: 12.5, color: 'var(--muted)' }}>{t.empty.boardSub}</span>
        {ora && (
          <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--muted)', ...numStyle, fontWeight: 500 }}>
            {t.empty.updatedAt} {ora}
          </span>
        )}
      </div>

      {/* fascia metriche */}
      <div style={{
        display: 'flex', flexWrap: 'wrap', border: '1px solid var(--border-br)',
        borderRadius: 10, overflow: 'hidden', marginBottom: 16,
        background: 'rgba(var(--rgb-contrasto), 0.015)',
      }}>
        {/* Le prime due venivano da /market/stats, che conta TUTTO l'archivio:
            dentro la sezione crypto scrivevano "36 titoli seguiti" e "33.055
            notizie", numeri veri ma di un altro mercato. Ora si calcolano
            sulle righe effettivamente mostrate. */}
        <Metrica etichetta={cripto ? 'Monete seguite' : t.empty.kTickers}
                 valore={righe.length || null} />
        <Metrica etichetta={cripto ? 'Notizie in 48 ore' : t.empty.kNews}
                 valore={cripto
                   ? righe.reduce((s, r) => s + (r.news || 0), 0) || null
                   : stats?.news_total?.toLocaleString(lang === 'it' ? 'it-IT' : 'en-US')} />
        <Metrica etichetta={cripto ? 'Con notizie oggi' : t.empty.k24h}
                 valore={cripto
                   ? righe.filter(r => r.news > 0).length || null
                   : stats?.news_today} />
        <Metrica etichetta={t.empty.kRanked} valore={righe.length || null} />
      </div>

      {/* classifiche */}
      {!mercato && !errore && (
        <div style={{
          color: risveglio ? 'var(--azure)' : 'var(--muted)', fontSize: 13,
          padding: '16px 14px', lineHeight: 1.6,
          border: risveglio ? '1px solid rgba(96,165,250,0.25)' : 'none',
          borderRadius: risveglio ? 8 : 0,
          background: risveglio ? 'rgba(96,165,250,0.05)' : 'transparent',
        }}>
          {risveglio ? (
            <>
              <strong>{t.empty.wakingTitle}</strong>
              <div style={{ color: 'var(--muted)', fontSize: 12.5, marginTop: 4 }}>
                {t.empty.wakingDesc}
              </div>
            </>
          ) : t.empty.loading}
        </div>
      )}
      {(errore || (mercato && !righe.length)) && (
        <div style={{ color: 'var(--muted)', fontSize: 13, padding: '20px 0' }}>{t.empty.offline}</div>
      )}
      {righe.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 14 }}>
          <Pannello titolo={t.empty.bulls} extra={`${rialzisti.length}`}>
            {rialzisti.map((r, i) => <Riga key={r.ticker} r={r} i={i} />)}
            {!rialzisti.length && <div style={{ padding: 12, color: 'var(--muted)', fontSize: 12.5 }}>—</div>}
          </Pannello>
          <Pannello titolo={t.empty.bears} extra={`${ribassisti.length}`}>
            {ribassisti.map((r, i) => <Riga key={r.ticker} r={r} i={i} />)}
            {!ribassisti.length && <div style={{ padding: 12, color: 'var(--muted)', fontSize: 12.5 }}>—</div>}
          </Pannello>
        </div>
      )}

      {/* ticker suggeriti, in forma compatta */}
      <div style={{ marginTop: 20 }}>
        <div style={{ fontSize: 10.5, color: 'var(--muted)', letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 9, fontWeight: 700 }}>
          {t.empty.suggestions}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
          {(SUGGERITI[mercatoAttivo] || SUGGERITI.azioni).map(tk => (
            <button
              key={tk.symbol}
              onClick={() => onLoad(tk.symbol, days, period)}
              style={{
                padding: '6px 11px', borderRadius: 7, fontSize: 12.5,
                border: '1px solid var(--border-br)',
                background: 'rgba(var(--rgb-contrasto), 0.03)',
                color: 'var(--white)', cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: 6,
                transition: 'border-color 0.15s, background 0.15s',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.borderColor = 'rgba(30,92,255,0.5)'
                e.currentTarget.style.background = 'rgba(30,92,255,0.08)'
              }}
              onMouseLeave={e => {
                e.currentTarget.style.borderColor = 'var(--border-br)'
                e.currentTarget.style.background = 'rgba(var(--rgb-contrasto), 0.03)'
              }}
            >
              {eCrypto(tk.symbol)
                ? <LogoCrypto ticker={tk.symbol} size={15} />
                : tk.flag ? <span>{tk.flag}</span> : null}
              <span style={{ fontWeight: 700 }}>
                {eCrypto(tk.symbol) ? tk.symbol.replace('-USD', '') : tk.symbol}
              </span>
              <span style={{ fontSize: 11, color: 'var(--muted)' }}>{tk.name}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}