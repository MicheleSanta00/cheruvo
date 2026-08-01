import { useState, useEffect, useRef } from 'react'
import { supabase } from '../supabase.js'
import { TICKERS } from '../data/tickers.js'
import { useLang } from '../LangContext.jsx'
import apiFetch from '../apiFetch.js'
import Icon from './Icon.jsx'

const PERIODS_FREE = [{ v: '1mo', l: '1M' }, { v: '3mo', l: '3M' }]
const PERIODS_PRO  = [{ v: '1mo', l: '1M' }, { v: '3mo', l: '3M' }, { v: '6mo', l: '6M' }, { v: '1y', l: '1A' }]

// Nomi brevi per la watchlist: il ticker da solo dice poco a chi inizia
const NOMI_BREVI = {
  NVDA:'NVIDIA', AAPL:'Apple', TSLA:'Tesla', MSFT:'Microsoft', GOOGL:'Alphabet',
  META:'Meta', AMD:'AMD', AMZN:'Amazon', MU:'Micron', INTC:'Intel', NFLX:'Netflix',
  GE:'GE', 'ENI.MI':'Eni', 'ENEL.MI':'Enel', 'ISP.MI':'Intesa', 'UCG.MI':'UniCredit',
  'STM.MI':'STMicro', 'RACE.MI':'Ferrari', 'LVMH.PA':'LVMH', 'SAP.DE':'SAP',
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

export default function Sidebar({ ticker, days, period, hasTicker, onLoad, onFetch, loading, fetching, onTickerChange, onDaysChange, onPeriodChange, isPro, onUpgrade }) {
  const { t } = useLang()
  // Campo "aggiungi": parte vuoto. Prima ereditava il ticker aperto e
  // compariva una riga fantasma con dentro NVDA.
  const [input, setInput] = useState('')
  const [watchlist, setWatchlist] = useState([])
  const [saving, setSaving] = useState(false)
  const [suggestions, setSuggestions] = useState([])
  const [showSuggestions, setShowSuggestions] = useState(false)
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

  const PERIODS = isPro ? PERIODS_PRO : PERIODS_FREE
  const maxDays = isPro ? MAX_DAYS_PRO : MAX_DAYS_FREE

  const handleInputChange = (e) => {
    const val = e.target.value.toUpperCase()
    setInput(val)
    if (val.length >= 1) {
      const filtered = TICKERS.filter(tk =>
        tk.symbol.startsWith(val) || tk.name.toUpperCase().includes(val)
      ).slice(0, 6)
      setSuggestions(filtered)
      setShowSuggestions(filtered.length > 0)
    } else {
      setShowSuggestions(false)
    }
  }

  const selectSuggestion = (tk) => {
    setInput(tk.symbol)
    setShowSuggestions(false)
    submit(tk.symbol)
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
      .filter((r) => r.sentiment > 0)
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

  const addTicker = async (tk) => {
    const v = tk.toUpperCase().trim()
    if (!v || watchlist.includes(v)) return
    if (!isPro && watchlist.length >= MAX_WATCHLIST_FREE) { onUpgrade(); return }
    setSaving(true)
    const { data: { user } } = await supabase.auth.getUser()
    await supabase.from('watchlist').insert({ user_id: user.id, ticker: v })
    setWatchlist(prev => [...prev, v])
    setSaving(false)
  }

  const removeTicker = async (tk) => {
    const { data: { user } } = await supabase.auth.getUser()
    await supabase.from('watchlist').delete().eq('ticker', tk).eq('user_id', user.id)
    setWatchlist(prev => prev.filter(x => x !== tk))
}

  const submit = (tk) => {
    const v = (tk || input).toUpperCase()
    setInput(v)
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
        <img src="/logo-v2.png" alt="Cheruvo" style={{ width: 24, height: 24, objectFit: 'contain' }} />
        <span style={{ fontSize: 15, fontWeight: 700, letterSpacing: '-0.01em' }}>Cheruvo</span>
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
            {isPro ? watchlist.length : `${watchlist.length}/${MAX_WATCHLIST_FREE}`}
          </span>
        </div>

        {watchlist.length === 0 && (
          <div style={{ padding: '14px 12px', fontSize: 12, color: 'var(--muted)', lineHeight: 1.6 }}>
            {t.sidebar.watchlistEmpty}
          </div>
        )}

        {watchlist.map(tk => {
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
                <span style={{ fontSize: 13, fontWeight: 700, display: 'block', letterSpacing: '.01em' }}>{tk}</span>
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
          <input
            value={input}
            onChange={(e) => setInput(e.target.value.toUpperCase())}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && input.trim()) { addTicker(input); setInput('') }
              if (e.key === 'Escape') setInput('')
            }}
            disabled={saving}
            placeholder={t.sidebar.addWatchlist}
            style={{
              padding: '9px 12px', fontSize: 12, width: '100%',
              color: 'var(--white)', background: 'transparent',
              border: 'none', borderBottom: '1px solid var(--border)',
              outline: 'none', fontFamily: 'var(--sans)',
            }}
          />
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