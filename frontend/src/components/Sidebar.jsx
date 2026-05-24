import { useState, useEffect } from 'react'
import { supabase } from '../supabase.js'
import { useState, useEffect, useRef } from 'react'
import { supabase } from '../supabase.js'
import { TICKERS } from '../data/tickers.js'

const DEFAULT_WATCHLIST = ['NVDA', 'AAPL', 'TSLA', 'MSFT', 'GOOGL']
const PERIODS = [{ v: '1mo', l: '1M' }, { v: '3mo', l: '3M' }, { v: '6mo', l: '6M' }, { v: '1y', l: '1A' }]

export default function Sidebar({ ticker, days, period, onLoad, onFetch, loading, fetching, onTickerChange, onDaysChange, onPeriodChange }) {
  const [input, setInput] = useState(ticker)
  const [watchlist, setWatchlist] = useState(DEFAULT_WATCHLIST)
  const [saving, setSaving] = useState(false)
  const [suggestions, setSuggestions] = useState([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const inputRef = useRef(null)

  const handleInputChange = (e) => {
    const val = e.target.value.toUpperCase()
    setInput(val)
    if (val.length >= 1) {
      const filtered = TICKERS.filter(t =>
        t.symbol.startsWith(val) ||
        t.name.toUpperCase().includes(val)
      ).slice(0, 6)
      setSuggestions(filtered)
      setShowSuggestions(filtered.length > 0)
    } else {
      setShowSuggestions(false)
    }
  }

  const selectSuggestion = (t) => {
    setInput(t.symbol)
    setShowSuggestions(false)
    submit(t.symbol)
  }


  useEffect(() => {
    loadWatchlist()
  }, [])

  const loadWatchlist = async () => {
    const { data, error } = await supabase
      .from('watchlist')
      .select('ticker')
      .order('created_at', { ascending: true })
    if (!error && data.length > 0) {
      setWatchlist(data.map(r => r.ticker))
    }
  }

  const addTicker = async (t) => {
    const v = t.toUpperCase().trim()
    if (!v || watchlist.includes(v)) return
    setSaving(true)
    const { data: { user } } = await supabase.auth.getUser()
    await supabase.from('watchlist').insert({ user_id: user.id, ticker: v })
    setWatchlist(prev => [...prev, v])
    setSaving(false)
  }

  const removeTicker = async (t) => {
    await supabase.from('watchlist').delete().eq('ticker', t)
    setWatchlist(prev => prev.filter(x => x !== t))
  }

  const submit = (t) => {
    const v = (t || input).toUpperCase()
    setInput(v)
    onTickerChange(v)
    onLoad(v, days, period)
  }

  return (
    <aside style={{
      width: 220, flexShrink: 0,
      background: 'var(--near-black)',
      borderRight: '1px solid var(--border)',
      display: 'flex', flexDirection: 'column',
      height: '100%', overflowY: 'auto',
      padding: '20px 12px',
      gap: 24,
    }}>

      {/* Logo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '0 8px', marginBottom: 4 }}>
        <div style={{
          width: 28, height: 28, background: 'var(--blue)',
          borderRadius: 7, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        }}>
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M1.5 10.5L5 6.5L8 9L12.5 4" stroke="white" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
            <circle cx="12.5" cy="4" r="1.2" fill="white"/>
          </svg>
        </div>
        <span style={{ fontSize: 14, fontWeight: 500, letterSpacing: '-0.01em' }}>FinSentinel</span>
      </div>

      {/* Search con autocomplete */}
      <div style={{ position: 'relative' }}>
        <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
          <input
            ref={inputRef}
            value={input}
            onChange={handleInputChange}
            onKeyDown={e => {
              if (e.key === 'Enter') { setShowSuggestions(false); submit() }
              if (e.key === 'Escape') setShowSuggestions(false)
            }}
            onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
            onFocus={() => input.length >= 1 && setShowSuggestions(suggestions.length > 0)}
            placeholder="NVDA, ENI.MI..."
            style={{
              flex: 1, background: 'var(--dark)',
              border: '1px solid var(--border-br)',
              color: 'var(--white)', borderRadius: 7,
              padding: '8px 10px', fontSize: 13,
              outline: 'none', fontFamily: 'var(--sans)',
            }}
          />
          <button
            onClick={() => { setShowSuggestions(false); submit() }}
            style={{
              background: 'var(--blue)', color: 'white',
              borderRadius: 7, padding: '0 12px', fontSize: 13,
              fontWeight: 500,
            }}
          >→</button>
        </div>

        {/* Dropdown suggerimenti */}
        {showSuggestions && (
          <div style={{
            position: 'absolute', top: '100%', left: 0, right: 0,
            background: 'var(--dark)', border: '1px solid var(--border)',
            borderRadius: 8, marginTop: 4, zIndex: 100,
            overflow: 'hidden', boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
          }}>
            {suggestions.map(t => (
              <div
                key={t.symbol}
                onMouseDown={() => selectSuggestion(t)}
                style={{
                  padding: '8px 12px', cursor: 'pointer',
                  display: 'flex', justifyContent: 'space-between',
                  alignItems: 'center', fontSize: 13,
                  borderBottom: '1px solid var(--border)',
                  transition: 'background 0.1s',
                }}
                onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.05)'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <div>
                  <span style={{ fontWeight: 500, color: 'var(--white)' }}>{t.symbol}</span>
                  <span style={{ fontSize: 11, color: 'var(--muted)', marginLeft: 8 }}>{t.name}</span>
                </div>
                <span style={{
                  fontSize: 10, color: 'var(--azure)',
                  background: 'rgba(96,165,250,0.08)',
                  border: '1px solid rgba(96,165,250,0.15)',
                  padding: '2px 6px', borderRadius: 4,
                }}>{t.exchange}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Watchlist */}
      <div>
        <Label>Watchlist</Label>
        <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 2 }}>
          {watchlist.map(t => (
            <div
              key={t}
              style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '8px 10px', borderRadius: 7,
                background: ticker === t ? 'rgba(30,92,255,0.15)' : 'transparent',
              }}
            >
              <button
                onClick={() => submit(t)}
                style={{
                  fontSize: 13, fontWeight: 500, flex: 1, textAlign: 'left',
                  color: ticker === t ? 'var(--azure)' : 'var(--white)',
                  background: 'transparent',
                }}
              >{t}</button>
              <button
                onClick={() => removeTicker(t)}
                style={{
                  fontSize: 11, color: 'var(--muted)',
                  background: 'transparent', padding: '2px 4px',
                  opacity: 0.5,
                }}
                title="Rimuovi"
              >✕</button>
            </div>
          ))}

          {/* Aggiungi ticker */}
          <button
            onClick={() => { if (input) addTicker(input) }}
            disabled={saving}
            style={{
              marginTop: 6, padding: '7px 10px', borderRadius: 7,
              fontSize: 12, color: 'var(--muted)',
              border: '1px dashed rgba(255,255,255,0.1)',
              background: 'transparent', textAlign: 'left',
              opacity: saving ? 0.5 : 1,
            }}
          >
            {saving ? 'Salvando...' : '+ Aggiungi alla watchlist'}
          </button>
        </div>
      </div>

      {/* Days */}
      <div>
        <Label>News ultimi {days} giorni</Label>
        <input
          type="range" min={7} max={90} value={days}
          onChange={e => onDaysChange(Number(e.target.value))}
          onMouseUp={() => onLoad(ticker, days, period)}
          style={{ width: '100%', marginTop: 8, accentColor: 'var(--blue)' }}
        />
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>
          <span>7g</span><span>90g</span>
        </div>
      </div>

      {/* Period */}
      <div>
        <Label>Periodo prezzi</Label>
        <div style={{ display: 'flex', gap: 4, marginTop: 6, flexWrap: 'wrap' }}>
          {PERIODS.map(p => (
            <button
              key={p.v}
              onClick={() => { onPeriodChange(p.v); onLoad(ticker, days, p.v) }}
              style={{
                padding: '5px 10px', borderRadius: 6, fontSize: 12, fontWeight: 500,
                border: '1px solid',
                borderColor: period === p.v ? 'rgba(30,92,255,0.5)' : 'var(--border-br)',
                background: period === p.v ? 'rgba(30,92,255,0.15)' : 'transparent',
                color: period === p.v ? 'var(--azure)' : 'var(--muted)',
              }}
            >{p.l}</button>
          ))}
        </div>
      </div>

      <div style={{ flex: 1 }} />

      {/* Fetch button */}
      <button
        onClick={() => onFetch(ticker)}
        disabled={fetching}
        style={{
          background: 'var(--blue)', color: 'white',
          borderRadius: 8, padding: '11px 0',
          fontSize: 13, fontWeight: 500,
          opacity: fetching ? 0.6 : 1,
        }}
      >
        {fetching ? 'Aggiornamento...' : '↻  Aggiorna news'}
      </button>
    </aside>
  )
}

function Label({ children }) {
  return <div style={{ fontSize: 11, fontWeight: 500, color: 'var(--muted)', letterSpacing: '0.08em', textTransform: 'uppercase', padding: '0 8px' }}>{children}</div>
}