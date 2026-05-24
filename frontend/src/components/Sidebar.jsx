import { useState, useEffect, useRef } from 'react'
import { supabase } from '../supabase.js'
import { TICKERS } from '../data/tickers.js'

const PERIODS_FREE = [{ v: '1mo', l: '1M' }, { v: '3mo', l: '3M' }]
const PERIODS_PRO  = [{ v: '1mo', l: '1M' }, { v: '3mo', l: '3M' }, { v: '6mo', l: '6M' }, { v: '1y', l: '1Y' }]

const MAX_WATCHLIST_FREE = 3
const MAX_DAYS_FREE = 30
const MAX_DAYS_PRO = 90

export default function Sidebar({ ticker, days, period, onLoad, onFetch, loading, fetching, onTickerChange, onDaysChange, onPeriodChange, isPro, onUpgrade }) {
  const [input, setInput] = useState(ticker)
  const [watchlist, setWatchlist] = useState(['NVDA', 'AAPL', 'TSLA'])
  const [saving, setSaving] = useState(false)
  const [suggestions, setSuggestions] = useState([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const inputRef = useRef(null)

  const PERIODS = isPro ? PERIODS_PRO : PERIODS_FREE
  const maxDays = isPro ? MAX_DAYS_PRO : MAX_DAYS_FREE
  const maxWatchlist = isPro ? Infinity : MAX_WATCHLIST_FREE

  const handleInputChange = (e) => {
    const val = e.target.value.toUpperCase()
    setInput(val)
    if (val.length >= 1) {
      const filtered = TICKERS.filter(t =>
        t.symbol.startsWith(val) || t.name.toUpperCase().includes(val)
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

  useEffect(() => { loadWatchlist() }, [])

  const loadWatchlist = async () => {
    const { data, error } = await supabase
      .from('watchlist').select('ticker').order('created_at', { ascending: true })
    if (!error && data?.length > 0) setWatchlist(data.map(r => r.ticker))
  }

  const addTicker = async (t) => {
    const v = t.toUpperCase().trim()
    if (!v || watchlist.includes(v)) return
    if (!isPro && watchlist.length >= MAX_WATCHLIST_FREE) {
      onUpgrade()
      return
    }
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

  const handleDaysChange = (val) => {
    const capped = Math.min(val, maxDays)
    onDaysChange(capped)
  }

  const handlePeriodChange = (p) => {
    if (!isPro && !PERIODS_FREE.find(x => x.v === p.v)) {
      onUpgrade()
      return
    }
    onPeriodChange(p.v)
    onLoad(ticker, days, p.v)
  }

  return (
    <aside style={{
      width: 220, flexShrink: 0,
      background: 'var(--near-black)',
      borderRight: '1px solid var(--border)',
      display: 'flex', flexDirection: 'column',
      height: '100%', overflowY: 'auto',
      padding: '20px 12px', gap: 24,
    }}>

      {/* Logo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '0 8px', marginBottom: 4 }}>
        <div style={{
          width: 28, height: 28, background: 'var(--blue)',
          borderRadius: 7, display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M1.5 10.5L5 6.5L8 9L12.5 4" stroke="white" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
            <circle cx="12.5" cy="4" r="1.2" fill="white"/>
          </svg>
        </div>
        <span style={{ fontSize: 14, fontWeight: 500, letterSpacing: '-0.01em' }}>FinSentinel</span>
      </div>

      {/* Search */}
      <div style={{ position: 'relative' }}>
        <Label>Ticker</Label>
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
            placeholder="NVDA, AAPL..."
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
            style={{ background: 'var(--blue)', color: 'white', borderRadius: 7, padding: '0 12px', fontSize: 13, fontWeight: 500 }}
          >→</button>
        </div>

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
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0 8px', marginBottom: 8 }}>
          <Label style={{ padding: 0 }}>Watchlist</Label>
          {!isPro && (
            <span style={{ fontSize: 10, color: 'var(--muted)' }}>{watchlist.length}/{MAX_WATCHLIST_FREE}</span>
          )}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {watchlist.map(t => (
            <div key={t} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '8px 10px', borderRadius: 7,
              background: ticker === t ? 'rgba(30,92,255,0.15)' : 'transparent',
            }}>
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
                style={{ fontSize: 11, color: 'var(--muted)', background: 'transparent', padding: '2px 4px', opacity: 0.5 }}
              >✕</button>
            </div>
          ))}

          {!isPro && watchlist.length >= MAX_WATCHLIST_FREE ? (
            <button
              onClick={onUpgrade}
              style={{
                marginTop: 6, padding: '7px 10px', borderRadius: 7,
                fontSize: 12, color: 'var(--azure)',
                border: '1px dashed rgba(96,165,250,0.3)',
                background: 'rgba(96,165,250,0.05)', textAlign: 'left',
              }}
            >
              ⚡ Pro for unlimited watchlist
            </button>
          ) : (
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
              {saving ? 'Saving...' : '+ Add to watchlist'}
            </button>
          )}
        </div>
      </div>

      {/* Days slider */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0 8px', marginBottom: 4 }}>
          <Label style={{ padding: 0 }}>Last {days}d of news</Label>
          {!isPro && <span style={{ fontSize: 10, color: 'var(--muted)' }}>🔒 max 30d</span>}
        </div>
        <input
          type="range" min={7} max={maxDays} value={Math.min(days, maxDays)}
          onChange={e => handleDaysChange(Number(e.target.value))}
          onMouseUp={() => onLoad(ticker, days, period)}
          style={{ width: '100%', marginTop: 4, accentColor: 'var(--blue)' }}
        />
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>
          <span>7d</span>
          <span>{maxDays}d {!isPro && '(Pro: 90d)'}</span>
        </div>
      </div>

      {/* Periods */}
      <div>
        <Label>Price range</Label>
        <div style={{ display: 'flex', gap: 4, marginTop: 6, flexWrap: 'wrap' }}>
          {PERIODS_PRO.map(p => {
            const isLocked = !isPro && !PERIODS_FREE.find(x => x.v === p.v)
            const isActive = period === p.v
            return (
              <button
                key={p.v}
                onClick={() => handlePeriodChange(p)}
                style={{
                  padding: '5px 10px', borderRadius: 6, fontSize: 12, fontWeight: 500,
                  border: '1px solid',
                  borderColor: isActive ? 'rgba(30,92,255,0.5)' : isLocked ? 'rgba(255,255,255,0.04)' : 'var(--border-br)',
                  background: isActive ? 'rgba(30,92,255,0.15)' : 'transparent',
                  color: isActive ? 'var(--azure)' : isLocked ? 'rgba(255,255,255,0.2)' : 'var(--muted)',
                  cursor: isLocked ? 'default' : 'pointer',
                  position: 'relative',
                }}
                title={isLocked ? 'Available with Pro' : ''}
              >
                {isLocked ? '🔒' : ''}{p.l}
              </button>
            )
          })}
        </div>
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
            ⚡ Upgrade to Pro
          </div>
          <div style={{ fontSize: 11, color: 'var(--muted)', lineHeight: 1.5 }}>
            Unlimited watchlist · 90 days<br/>
            Email alerts · CSV export
          </div>
          <div style={{ fontSize: 12, color: 'var(--white)', marginTop: 8, fontWeight: 500 }}>
            €9/month →
          </div>
        </button>
      )}

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
        {fetching ? 'Updating...' : '↻  Refresh news'}
      </button>
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
