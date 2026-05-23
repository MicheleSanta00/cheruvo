import { useState } from 'react'

const WATCHLIST = ['NVDA', 'AAPL', 'TSLA', 'MSFT', 'GOOGL', 'META', 'AMD', 'AMZN']
const PERIODS   = [{ v: '1mo', l: '1M' }, { v: '3mo', l: '3M' }, { v: '6mo', l: '6M' }, { v: '1y', l: '1A' }]

export default function Sidebar({ ticker, days, period, onLoad, onFetch, loading, fetching, onTickerChange, onDaysChange, onPeriodChange }) {
  const [input, setInput] = useState(ticker)

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

      {/* Search */}
      <div>
        <Label>Ticker</Label>
        <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
          <input
            value={input}
            onChange={e => setInput(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && submit()}
            placeholder="NVDA"
            style={{
              flex: 1, background: 'var(--dark)',
              border: '1px solid var(--border-br)',
              color: 'var(--white)', borderRadius: 7,
              padding: '8px 10px', fontSize: 13,
              outline: 'none', fontFamily: 'var(--sans)',
            }}
          />
          <button
            onClick={() => submit()}
            style={{
              background: 'var(--blue)', color: 'white',
              borderRadius: 7, padding: '0 12px', fontSize: 13,
              fontWeight: 500, transition: 'opacity .2s',
            }}
          >→</button>
        </div>
      </div>

      {/* Watchlist */}
      <div>
        <Label>Watchlist</Label>
        <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 2 }}>
          {WATCHLIST.map(t => (
            <button
              key={t}
              onClick={() => submit(t)}
              style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '8px 10px', borderRadius: 7, fontSize: 13, fontWeight: 500,
                background: ticker === t ? 'rgba(30,92,255,0.15)' : 'transparent',
                color: ticker === t ? 'var(--azure)' : 'var(--white)',
                transition: 'background .15s',
              }}
              onMouseEnter={e => { if (ticker !== t) e.currentTarget.style.background = 'rgba(255,255,255,0.05)' }}
              onMouseLeave={e => { if (ticker !== t) e.currentTarget.style.background = 'transparent' }}
            >
              <span>{t}</span>
            </button>
          ))}
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
                transition: 'all .15s',
              }}
            >{p.l}</button>
          ))}
        </div>
      </div>

      {/* Spacer */}
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
          transition: 'opacity .2s, transform .15s',
        }}
        onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-1px)' }}
        onMouseLeave={e => { e.currentTarget.style.transform = 'translateY(0)' }}
      >
        {fetching ? 'Aggiornamento...' : '↻  Aggiorna news'}
      </button>
    </aside>
  )
}

function Label({ children }) {
  return <div style={{ fontSize: 11, fontWeight: 500, color: 'var(--muted)', letterSpacing: '0.08em', textTransform: 'uppercase', padding: '0 8px' }}>{children}</div>
}
