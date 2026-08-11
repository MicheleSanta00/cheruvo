import { useState, useEffect, useRef } from 'react'
import { supabase } from '../supabase.js'
import { TICKERS } from '../data/tickers.js'
import { useLang } from '../LangContext.jsx'
import apiFetch from '../apiFetch.js'
import Icon from './Icon.jsx'
import LogoCrypto, { eCrypto, nelMercato } from './LogoCrypto.jsx'

const PERIODS_FREE = [{ v: '1mo', l: '1M' }, { v: '3mo', l: '3M' }]
const PERIODS_PRO  = [{ v: '1mo', l: '1M' }, { v: '3mo', l: '3M' }, { v: '6mo', l: '6M' }, { v: '1y', l: '1A' }]

// Nomi brevi per la watchlist: il ticker da solo dice poco a chi inizia
const NOMI_BREVI = {
  NVDA:'NVIDIA', AAPL:'Apple', TSLA:'Tesla', MSFT:'Microsoft', GOOGL:'Alphabet',
  META:'Meta', AMD:'AMD', AMZN:'Amazon', MU:'Micron', INTC:'Intel', NFLX:'Netflix',
  GE:'GE', 'ENI.MI':'Eni', 'ENEL.MI':'Enel', 'ISP.MI':'Intesa', 'UCG.MI':'UniCredit',
  'STMMI.MI':'STMicro', 'RACE.MI':'Ferrari', 'LVMH.PA':'LVMH', 'SAP.DE':'SAP',
  'ASML.AS':'ASML', 'SHEL.L':'Shell',
}

// Quanti titoli mettere da soli nella watchlist di chi arriva per la prima
// volta: l'app non deve mai presentarsi vuota.
const PRECARICATI = 3

// Tetto del piano gratuito. Alzato da 3 a 5 perché con 3 preinseriti un nuovo
// utente sarebbe già al limite e non potrebbe aggiungere nemmeno un titolo suo:
// la prima cosa che vedrebbe sarebbe un muro. Con 5 restano due posti liberi,
// e "watchlist illimitata" resta comunque un argomento del piano Pro.
const MAX_WATCHLIST_FREE = 5
const MAX_DAYS_FREE = 30
const MAX_DAYS_PRO = 90

export default function Sidebar({ ticker, days, period, hasTicker, onLoad, onFetch, loading, fetching, onTickerChange, onDaysChange, onPeriodChange, isPro, onUpgrade, mercatoAttivo = 'azioni', onMercatoChange }) {
  const { t } = useLang()
  // Campo "aggiungi": parte vuoto. Prima ereditava il ticker aperto e
  // compariva una riga fantasma con dentro NVDA.
  const [input, setInput] = useState('')
  const [watchlist, setWatchlist] = useState([])
  const [saving, setSaving] = useState(false)
  const [suggestions, setSuggestions] = useState([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [verificando, setVerificando] = useState(false)
  const [errore, setErrore] = useState('')
  const inputRef = useRef(null)

  // Sentiment di ogni titolo in watchlist. Una sola chiamata all'endpoint
  // pubblico (già in cache lato server), non una per ticker.
  const [sentimenti, setSentimenti] = useState({})
  const [conteggi, setConteggi] = useState({})
  const [righeMercato, setRigheMercato] = useState(null)
  useEffect(() => {
    let vivo = true
    apiFetch('/market/today')
      .then((d) => {
        if (!vivo) return
        const s = {}, c = {}
        for (const r of d?.rows || []) { s[r.ticker] = r.sentiment; c[r.ticker] = r.news }
        setSentimenti(s); setConteggi(c); setRigheMercato(d?.rows || [])
      })
      .catch(() => { if (vivo) setRigheMercato([]) })
    return () => { vivo = false }
  }, [])

  // La classifica contiene solo i titoli con almeno due notizie nelle ultime
  // 48 ore: gli altri restavano senza punteggio, con un puntino al posto del
  // numero. Per quelli chiediamo la media a 7 giorni, una richiesta ciascuno
  // e solo per i mancanti (al massimo una manciata, ed è tutto in cache lato
  // server). Meglio un dato più lento che una casella vuota.
  useEffect(() => {
    if (righeMercato === null || !watchlist.length) return
    const mancanti = watchlist.filter((tk) => sentimenti[tk] === undefined)
    if (!mancanti.length) return
    let vivo = true
    Promise.all(mancanti.map((tk) =>
      apiFetch(`/news/${tk}?days=7`)
        .then((d) => ({ tk, s: d?.avg_sentiment, n: d?.total }))
        .catch(() => null)
    )).then((esiti) => {
      if (!vivo) return
      const s = {}, c = {}
      for (const e of esiti) {
        if (!e) continue
        // Zero notizie non significa "sentiment neutro": significa che non
        // sappiamo. Mostrare 0.00 sarebbe un numero inventato.
        if (!e.n) { c[e.tk] = 0; continue }
        if (e.s == null) continue
        s[e.tk] = e.s
        c[e.tk] = e.n
      }
      if (Object.keys(s).length) {
        setSentimenti((p) => ({ ...s, ...p }))
        setConteggi((p) => ({ ...c, ...p }))
      }
    })
    return () => { vivo = false }
  }, [righeMercato, watchlist])

  // I titoli della watchlist che appartengono al mercato attivo: sono
  // quelli che si vedono, quindi sono quelli che vanno contati.
  const visibili = watchlist.filter(tk => nelMercato(tk, mercatoAttivo))

  const PERIODS = isPro ? PERIODS_PRO : PERIODS_FREE
  const maxDays = isPro ? MAX_DAYS_PRO : MAX_DAYS_FREE

  // Suggerimenti mentre scrivi, come nella ricerca in alto. Chi già segue un
  // titolo non se lo ritrova proposto una seconda volta.
  const handleInputChange = (e) => {
    const val = e.target.value.toUpperCase()
    setInput(val)
    setErrore('')
    if (val.length >= 1) {
      const filtered = TICKERS.filter(tk =>
        (tk.symbol.startsWith(val) || tk.name.toUpperCase().includes(val)) &&
        !watchlist.includes(tk.symbol) && nelMercato(tk.symbol, mercatoAttivo)
      ).slice(0, 5)
      setSuggestions(filtered)
      setShowSuggestions(filtered.length > 0)
    } else {
      setSuggestions([])
      setShowSuggestions(false)
    }
  }

  // Cliccando un suggerimento lo si AGGIUNGE alla watchlist. Prima apriva il
  // titolo e basta, che è il gesto della ricerca, non di questo campo.
  const selectSuggestion = (tk) => {
    setShowSuggestions(false)
    setInput('')
    addTicker(tk.symbol)
  }

  useEffect(() => { loadWatchlist() }, [])

  const [letta, setLetta] = useState(false)   // watchlist già letta dal database

  const loadWatchlist = async () => {
    const { data, error } = await supabase
      .from('watchlist').select('ticker').order('created_at', { ascending: true })
    if (!error && data?.length > 0) setWatchlist(data.map(r => r.ticker))
    setLetta(true)
  }

  // Primo accesso: la watchlist si riempie da sola coi titoli col sentiment
  // più alto del momento. Un'app che si presenta vuota costringe l'utente a
  // capire da solo da dove cominciare, ed è lì che la maggior parte se ne va.
  const seminato = useRef(false)
  useEffect(() => {
    if (seminato.current) return
    if (!letta || watchlist.length || !righeMercato?.length) return
    seminato.current = true

    const migliori = [...righeMercato]
      .filter((r) => r.sentiment > 0 && nelMercato(r.ticker, mercatoAttivo))
      .sort((a, b) => b.sentiment - a.sentiment)
      .slice(0, PRECARICATI)
      .map((r) => r.ticker)
    if (!migliori.length) return

    ;(async () => {
      try {
        const { data: { user } } = await supabase.auth.getUser()
        if (!user) return
        await supabase.from('watchlist').insert(
          migliori.map((tk) => ({ user_id: user.id, ticker: tk }))
        )
        setWatchlist(migliori)
      } catch (_) {
        // Se il salvataggio fallisce li mostriamo comunque: meglio una
        // watchlist non persistente che una schermata vuota.
        setWatchlist(migliori)
      }
    })()
  }, [letta, watchlist.length, righeMercato])

  // Salva SOLO ticker che esistono davvero.
  //
  // Prima bastava scrivere una parola qualsiasi e finiva dritta nel database:
  // la watchlist si riempiva di righe inventate, per sempre senza prezzo e
  // senza notizie, e l'utente non capiva se fosse colpa sua o del prodotto.
  //
  // Il controllo è a due livelli. I 294 titoli dell'elenco locale passano
  // subito, senza rete. Per tutto il resto si chiede a /validate, che
  // interroga Yahoo: così restano ammessi anche i titoli fuori elenco (sono
  // decine di migliaia), ma solo se esistono per davvero.
  const addTicker = async (tk) => {
    const v = (tk || '').toUpperCase().trim()
    if (!v) return
    if (watchlist.includes(v)) { setErrore(t.sidebar.giaPresente(v)); return }
    if (!isPro && watchlist.length >= MAX_WATCHLIST_FREE) { onUpgrade(); return }

    setErrore('')
    if (!TICKERS.some(x => x.symbol === v)) {
      setVerificando(true)
      try {
        const info = await apiFetch(`/validate/${encodeURIComponent(v)}`)
        if (!info?.valid) { setErrore(t.sidebar.nonTrovato(v)); return }
      } catch (_) {
        // Rete o backend giù: meglio non salvare che salvare alla cieca.
        setErrore(t.sidebar.nonTrovato(v))
        return
      } finally {
        setVerificando(false)
      }
    }

    setSaving(true)
    try {
      const { data: { user } } = await supabase.auth.getUser()
      await supabase.from('watchlist').insert({ user_id: user.id, ticker: v })
      setWatchlist(prev => [...prev, v])
      setInput('')
      setShowSuggestions(false)
    } finally {
      setSaving(false)
    }
  }

  const removeTicker = async (tk) => {
    const { data: { user } } = await supabase.auth.getUser()
    await supabase.from('watchlist').delete().eq('ticker', tk).eq('user_id', user.id)
    setWatchlist(prev => prev.filter(x => x !== tk))
}

  const submit = (tk) => {
    const v = (tk || input).toUpperCase()
    // Niente setInput qui: il campo in fondo serve ad AGGIUNGERE un titolo,
    // non è più la casella di ricerca. Scrivendoci dentro il ticker appena
    // aperto compariva una riga fantasma con scritto "NVDA" sotto la lista.
    onTickerChange(v)
    onLoad(v, days, period)
  }

  const handleDaysChange = (val) => {
    onDaysChange(Math.min(val, maxDays))
  }

  const handlePeriodChange = (p) => {
    if (!isPro && !PERIODS_FREE.find(x => x.v === p.v)) { onUpgrade(); return }
    onPeriodChange(p.v)
    onLoad(ticker, days, p.v)
  }

  return (
    <aside style={{
      width: 244, flexShrink: 0,
      background: 'var(--black)',
      borderRight: '1px solid var(--border)',
      display: 'flex', flexDirection: 'column',
      height: '100%', overflowY: 'auto',
    }}>

      {/* Logo: stessa altezza della barra in alto, così le due si allineano */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 9, height: 52, flexShrink: 0,
        padding: '0 14px', borderBottom: '1px solid var(--border)',
      }}>
        {/* Il logo è disegnato in chiaro, pensato per il fondo nero: sul tema
            chiaro spariva quasi del tutto. Il cerchio è FISSO scuro, non una
            variabile: sul tema scuro coincide con lo sfondo e resta invisibile,
            sul chiaro diventa un disco nero che restituisce al logo il fondo
            per cui era stato disegnato. Una riga, e vale per entrambi. */}
        <span style={{
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: 30, height: 30, borderRadius: '50%',
          background: '#06070a', flexShrink: 0,
        }}>
          <img src="/logo-v2.png" alt="Cheruvo" style={{ width: 19, height: 19, objectFit: 'contain' }} />
        </span>
        <span style={{ fontSize: 15, fontWeight: 700, letterSpacing: '-0.01em' }}>Cheruvo</span>
      </div>


      {/* Sezione: azioni o crypto. Sta qui, sopra ogni altra cosa, perché
          è la domanda a cui l'utente deve poter rispondere per primo:
          "che cosa sto guardando". */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--border)' }}>
        {[['azioni', 'Azioni'], ['crypto', 'Crypto']].map(([v, etichetta]) => {
          const attivo = mercatoAttivo === v
          return (
            <button key={v} onClick={() => onMercatoChange?.(v)} style={{
              flex: 1, padding: '9px 0', fontSize: 11, fontWeight: 700,
              letterSpacing: '.1em', textTransform: 'uppercase',
              background: attivo ? 'var(--near-black)' : 'transparent',
              color: attivo ? 'var(--azure)' : 'var(--muted)',
              borderBottom: attivo ? '2px solid var(--blue)' : '2px solid transparent',
              cursor: 'pointer',
            }}>{etichetta}</button>
          )
        })}
      </div>

      {/* Watchlist: intestazione a barra e righe a tutta larghezza con
          divisori da un pixel, esattamente come i pannelli del terminale. */}
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '7px 12px', background: 'var(--near-black)',
          borderBottom: '1px solid var(--border)',
        }}>
          <span style={{ fontSize: 10, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--muted)', fontWeight: 700 }}>
            {t.sidebar.watchlist}
          </span>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--muted)', fontWeight: 700 }}>
            {isPro ? visibili.length : `${visibili.length}/${MAX_WATCHLIST_FREE}`}
          </span>
        </div>

        {visibili.length === 0 && (
          <div style={{ padding: '14px 12px', fontSize: 12, color: 'var(--muted)', lineHeight: 1.6 }}>
            {t.sidebar.watchlistEmpty}
          </div>
        )}

        {watchlist.filter(tk => nelMercato(tk, mercatoAttivo)).map(tk => {
          const s = sentimenti[tk]
          const attivo = ticker === tk
          return (
            <div key={tk} className="wl-row" style={{
              display: 'grid', gridTemplateColumns: '1fr auto auto', gap: 8,
              alignItems: 'center', padding: '8px 12px',
              borderBottom: '1px solid var(--border)',
              background: attivo ? 'rgba(30,92,255,0.10)' : 'transparent',
              boxShadow: attivo ? 'inset 2px 0 0 var(--blue)' : 'none',
            }}>
              <button
                onClick={() => submit(tk)}
                style={{
                  textAlign: 'left', background: 'transparent', padding: 0,
                  display: 'block', minWidth: 0, overflow: 'hidden',
                  color: attivo ? 'var(--azure)' : 'var(--white)',
                }}
              >
                {/* Il simbolo compare SOLO sulle crypto. Sui titoli azionari
                    servirebbe un servizio esterno di loghi, con i suoi
                    obblighi di attribuzione e il rischio che chiuda: qui il
                    disco è disegnato in casa e non dipende da nessuno. */}
                <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  {eCrypto(tk) && <LogoCrypto ticker={tk} size={16} />}
                  <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: '.01em' }}>
                    {eCrypto(tk) ? tk.replace('-USD', '') : tk}
                  </span>
                </span>
                <span style={{
                  fontSize: 10.5, color: 'var(--muted)', display: 'block', lineHeight: 1.35,
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                }}>
                  {NOMI_BREVI[tk] || tk}
                  {/* "0 news" non aggiunge niente: si scrive solo se ce ne sono */}
                  {conteggi[tk] ? ` · ${conteggi[tk]} news` : ''}
                </span>
              </button>
              <span
                title={s === undefined ? (t.sidebar.watchlistEmpty ? 'Nessuna notizia recente' : '') : ''}
                style={{
                  fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums',
                  fontSize: 12.5, fontWeight: 700, textAlign: 'right',
                  color: s === undefined ? 'var(--muted)'
                    : s > 0.08 ? 'var(--green)' : s < -0.08 ? 'var(--red)' : 'var(--muted)',
                }}>
                {/* Trattino, non zero: senza notizie il sentiment non esiste */}
                {s === undefined ? '—' : `${s > 0 ? '+' : s < 0 ? '−' : ''}${Math.abs(s).toFixed(2)}`}
              </span>
              <button
                onClick={() => removeTicker(tk)}
                className="wl-del"
                title={t.sidebar.watchlist}
                style={{ background: 'transparent', padding: '2px 2px', display: 'flex', alignItems: 'center', color: 'var(--muted)', opacity: 0 }}
              ><Icon name="close" size={11} /></button>
            </div>
          )
        })}

        {/* Aggiungi: una riga come le altre, non un bottone tratteggiato */}
        {(!isPro && watchlist.length >= MAX_WATCHLIST_FREE) ? (
          <button onClick={onUpgrade} style={{
            padding: '9px 12px', textAlign: 'left', fontSize: 12,
            color: 'var(--azure)', background: 'transparent',
            borderBottom: '1px solid var(--border)',
          }}>{t.sidebar.proWatchlist}</button>
        ) : (
          /* Campo inline invece di una finestra di sistema: scrivi e premi
             Invio, senza che il browser interrompa il flusso con un popup. */
          <>
            <input
              ref={inputRef}
              value={input}
              onChange={handleInputChange}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  // Invio senza aver scelto nulla: prende il primo
                  // suggerimento, che è quasi sempre quello voluto.
                  const scelto = showSuggestions && suggestions.length
                    ? suggestions[0].symbol : input.trim()
                  if (scelto) { setShowSuggestions(false); addTicker(scelto) }
                }
                if (e.key === 'Escape') { setInput(''); setShowSuggestions(false); setErrore('') }
              }}
              onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
              onFocus={() => setShowSuggestions(suggestions.length > 0)}
              disabled={saving || verificando}
              placeholder={t.sidebar.addWatchlist}
              style={{
                padding: '9px 12px', fontSize: 12, width: '100%',
                color: 'var(--white)', background: 'transparent',
                border: 'none', borderBottom: '1px solid var(--border)',
                outline: 'none', fontFamily: 'var(--sans)',
              }}
            />

            {/* Suggerimenti come righe piene, non come pannello che galleggia:
                la colonna è stretta e un menu sospeso verrebbe tagliato dal
                bordo. Così sono righe come le altre della watchlist. */}
            {showSuggestions && suggestions.map((tk) => (
              <button
                key={tk.symbol}
                onMouseDown={(e) => { e.preventDefault(); selectSuggestion(tk) }}
                className="wl-row"
                style={{
                  display: 'grid', gridTemplateColumns: '1fr auto', gap: 8,
                  alignItems: 'baseline', width: '100%', textAlign: 'left',
                  padding: '7px 12px', background: 'var(--near-black)',
                  border: 'none', borderBottom: '1px solid var(--border)',
                  borderRadius: 0, cursor: 'pointer', color: 'var(--white)',
                }}
              >
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  <span style={{ fontWeight: 700, fontSize: 12 }}>{tk.symbol}</span>
                  <span style={{ color: 'var(--muted)', fontSize: 10.5, marginLeft: 6 }}>{tk.name}</span>
                </span>
                <span style={{ color: 'var(--azure)', fontSize: 13, lineHeight: 1 }}>+</span>
              </button>
            ))}

            {(verificando || errore) && (
              <div style={{
                padding: '7px 12px', fontSize: 10.5, lineHeight: 1.45,
                borderBottom: '1px solid var(--border)',
                color: errore ? 'var(--red)' : 'var(--muted)',
              }}>
                {errore || t.sidebar.verificando}
              </div>
            )}
          </>
        )}
      </div>

      <div style={{ flex: 1 }} />

      {/* Upgrade banner */}
      {!isPro && (
        <button
          onClick={onUpgrade}
          style={{
            padding: '12px', borderRadius: 10,
            background: 'linear-gradient(135deg, rgba(30,92,255,0.15), rgba(96,165,250,0.08))',
            border: '1px solid rgba(30,92,255,0.25)',
            cursor: 'pointer', textAlign: 'left',
          }}
        >
          <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--azure)', marginBottom: 4 }}>
            {t.sidebar.upgradeBanner.title}
          </div>
          <div style={{ fontSize: 11, color: 'var(--muted)', lineHeight: 1.5, whiteSpace: 'pre-line' }}>
            {t.sidebar.upgradeBanner.desc}
          </div>
          <div style={{ fontSize: 12, color: 'var(--white)', marginTop: 8, fontWeight: 500 }}>
            {t.sidebar.upgradeBanner.price}
          </div>
        </button>
      )}

    </aside>
  )
}

function Label({ children, style }) {
  return (
    <div style={{
      fontSize: 11, fontWeight: 500, color: 'var(--muted)',
      letterSpacing: '0.08em', textTransform: 'uppercase',
      padding: '0 8px', ...style,
    }}>{children}</div>
  )
}