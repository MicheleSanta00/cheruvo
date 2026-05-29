import { useState, useCallback } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Legend,
} from 'recharts'
import apiFetch from '../apiFetch.js'
import { TICKERS } from '../data/tickers.js'

const MAX_COMPARE = 3

const PALETTE = ['#60a5fa', '#a78bfa', '#fb923c', '#34d399']
// Il primo colore (blu) è per il ticker principale

// ── Tooltip ───────────────────────────────────────────────────────────────────
function CompareTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: '#0f1117', border: '1px solid rgba(255,255,255,0.1)',
      borderRadius: 8, padding: '10px 14px', fontSize: 12,
      minWidth: 160,
    }}>
      <div style={{ color: '#94a3b8', marginBottom: 8, fontWeight: 500 }}>{label}</div>
      {payload.map((p, i) => {
        const v = p.value
        const color = p.color
        const label = v == null ? '—'
          : v > 0.1 ? `▲ ${v.toFixed(3)}` : v < -0.1 ? `▼ ${v.toFixed(3)}` : `─ ${v.toFixed(3)}`
        return (
          <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: 16, marginBottom: 3 }}>
            <span style={{ color }}>{p.name}</span>
            <span style={{ color, fontWeight: 600 }}>{label}</span>
          </div>
        )
      })}
    </div>
  )
}

// ── Merge dei dati per data ───────────────────────────────────────────────────
function mergeByDate(tickersData) {
  // tickersData: [{ticker, sentiment: [{date, sentiment}]}]
  const dateMap = {}
  tickersData.forEach(({ ticker, sentiment }) => {
    sentiment.forEach(({ date, sentiment: s }) => {
      if (!dateMap[date]) dateMap[date] = { date }
      dateMap[date][ticker] = s
    })
  })
  return Object.values(dateMap)
    .sort((a, b) => new Date(a.date) - new Date(b.date))
}

// ── Componente principale ─────────────────────────────────────────────────────
export default function ComparePanel({ primaryTicker, primarySentiment, isPro, onUpgrade }) {
  const [extraTickers, setExtraTickers]   = useState([])  // [{ticker, sentiment, loading}]
  const [input, setInput]                 = useState('')
  const [inputError, setInputError]       = useState(null)
  const [suggestions, setSuggestions]     = useState([])
  const [showSuggestions, setShowSuggestions] = useState(false)

  const allTickers = [
    { ticker: primaryTicker, sentiment: primarySentiment },
    ...extraTickers,
  ]

  const mergedData = mergeByDate(allTickers.filter(t => t.sentiment?.length > 0))

  const handleInputChange = (e) => {
    const val = e.target.value.toUpperCase()
    setInput(val)
    setInputError(null)
    if (val.length >= 1) {
      const filtered = TICKERS.filter(tk =>
        tk.symbol.startsWith(val) || tk.name.toUpperCase().includes(val)
      ).slice(0, 5)
      setSuggestions(filtered)
      setShowSuggestions(filtered.length > 0)
    } else {
      setShowSuggestions(false)
    }
  }

  const addTicker = useCallback(async (symbol) => {
    const tk = symbol.toUpperCase().trim()
    if (!tk) return
    if (tk === primaryTicker) { setInputError('Ticker già nel grafico principale'); return }
    if (extraTickers.find(t => t.ticker === tk)) { setInputError('Ticker già aggiunto'); return }
    if (extraTickers.length >= MAX_COMPARE - 1) { setInputError(`Massimo ${MAX_COMPARE} ticker`); return }

    // Aggiunge con loading
    setExtraTickers(prev => [...prev, { ticker: tk, sentiment: [], loading: true }])
    setInput('')
    setShowSuggestions(false)
    setInputError(null)

    try {
      const data = await apiFetch(`/sentiment/${tk}`)
      const sent = data.sentiment || []
      if (sent.length === 0) {
        // Nessuna news — rimuovi e spiega all'utente
        setExtraTickers(prev => prev.filter(t => t.ticker !== tk))
        setInputError(`${tk} non ha ancora news nel database. Cercalo nella sidebar e clicca "Aggiorna news" prima di aggiungerlo al confronto.`)
      } else {
        setExtraTickers(prev => prev.map(t =>
          t.ticker === tk ? { ticker: tk, sentiment: sent, loading: false } : t
        ))
      }
    } catch (e) {
      setExtraTickers(prev => prev.filter(t => t.ticker !== tk))
      setInputError(`Ticker non trovato: ${tk}`)
    }
  }, [primaryTicker, extraTickers])

  const removeTicker = (tk) => {
    setExtraTickers(prev => prev.filter(t => t.ticker !== tk))
  }

  const selectSuggestion = (tk) => {
    setShowSuggestions(false)
    addTicker(tk.symbol)
  }

  // Locked per free
  if (!isPro) return (
    <div style={panelStyle}>
      <Header />
      <div style={{
        background: 'rgba(30,92,255,0.04)', border: '1px solid rgba(30,92,255,0.15)',
        borderRadius: 10, padding: '20px', textAlign: 'center',
      }}>
        <div style={{ fontSize: 22, marginBottom: 8 }}>📊</div>
        <div style={{ fontSize: 13, color: 'var(--off-white)', fontWeight: 500, marginBottom: 6 }}>
          Confronto multi-ticker disponibile con Pro
        </div>
        <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 14, lineHeight: 1.6 }}>
          Sovrapponi il sentiment di fino a 3 ticker sullo stesso grafico.<br/>
          Es: NVDA vs AMD, ENI vs ENEL, AAPL vs MSFT.
        </div>
        <button onClick={onUpgrade} style={{
          fontSize: 12, color: '#60a5fa', fontWeight: 600,
          padding: '8px 20px', background: 'rgba(96,165,250,0.1)',
          borderRadius: 100, border: '1px solid rgba(96,165,250,0.3)',
          cursor: 'pointer',
        }}>⚡ Passa a Pro — €9/mese</button>
      </div>
    </div>
  )

  return (
    <div style={panelStyle}>
      <Header />

      {/* Ticker attivi */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 }}>
        {allTickers.map(({ ticker, loading }, i) => (
          <div key={ticker} style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '4px 10px', borderRadius: 100,
            background: `${PALETTE[i]}18`,
            border: `1px solid ${PALETTE[i]}40`,
            fontSize: 12, fontWeight: 500, color: PALETTE[i],
          }}>
            {loading
              ? <span style={{ animation: 'spin 0.8s linear infinite', display: 'inline-block' }}>⟳</span>
              : <span style={{ width: 8, height: 8, borderRadius: '50%', background: PALETTE[i], display: 'inline-block' }} />
            }
            {ticker}
            {i > 0 && (
              <button onClick={() => removeTicker(ticker)} style={{
                background: 'transparent', color: PALETTE[i],
                fontSize: 11, padding: '0 2px', opacity: 0.7,
                lineHeight: 1,
              }}>✕</button>
            )}
          </div>
        ))}

        {/* Input aggiungi ticker */}
        {allTickers.length < MAX_COMPARE && (
          <div style={{ position: 'relative' }}>
            <div style={{ display: 'flex', gap: 4 }}>
              <input
                value={input}
                onChange={handleInputChange}
                onKeyDown={e => { if (e.key === 'Enter') { setShowSuggestions(false); addTicker(input) } }}
                onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
                onFocus={() => input.length >= 1 && setShowSuggestions(suggestions.length > 0)}
                placeholder="+ Aggiungi ticker..."
                style={{
                  background: 'rgba(255,255,255,0.05)',
                  border: '1px dashed rgba(255,255,255,0.2)',
                  color: 'var(--white)', borderRadius: 100,
                  padding: '4px 12px', fontSize: 12,
                  outline: 'none', width: 140,
                  fontFamily: 'var(--sans)',
                }}
              />
              {input && (
                <button
                  onClick={() => { setShowSuggestions(false); addTicker(input) }}
                  style={{
                    background: 'var(--blue)', color: 'white',
                    borderRadius: 100, padding: '4px 10px', fontSize: 12,
                  }}
                >→</button>
              )}
            </div>
            {showSuggestions && (
              <div style={{
                position: 'absolute', top: '110%', left: 0, zIndex: 100,
                background: 'var(--dark)', border: '1px solid var(--border)',
                borderRadius: 8, overflow: 'hidden', minWidth: 200,
                boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
              }}>
                {suggestions.map(tk => (
                  <div
                    key={tk.symbol}
                    onMouseDown={() => selectSuggestion(tk)}
                    style={{
                      padding: '7px 12px', cursor: 'pointer', fontSize: 12,
                      display: 'flex', justifyContent: 'space-between',
                      borderBottom: '1px solid var(--border)',
                    }}
                    onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.05)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                  >
                    <span style={{ fontWeight: 500 }}>{tk.symbol}</span>
                    <span style={{ color: 'var(--muted)', fontSize: 11 }}>{tk.name}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {inputError && (
        <div style={{ fontSize: 11, color: '#f87171', marginBottom: 10 }}>⚠ {inputError}</div>
      )}

      {/* Grafico */}
      {mergedData.length > 0 ? (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={mergedData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis
              dataKey="date"
              tick={{ fill: '#64748b', fontSize: 10 }}
              tickFormatter={d => d?.slice(5)}
              interval="preserveStartEnd"
            />
            <YAxis
              domain={[-1, 1]}
              tickCount={5}
              tickFormatter={v => v.toFixed(1)}
              tick={{ fill: '#64748b', fontSize: 10 }}
              width={36}
            />
            <Tooltip content={<CompareTooltip />} />
            <ReferenceLine y={0}    stroke="rgba(255,255,255,0.1)" />
            <ReferenceLine y={0.1}  stroke="rgba(74,222,128,0.15)"  strokeDasharray="3 3" />
            <ReferenceLine y={-0.1} stroke="rgba(248,113,113,0.15)" strokeDasharray="3 3" />

            {allTickers.map(({ ticker }, i) => (
              <Line
                key={ticker}
                type="monotone"
                dataKey={ticker}
                name={ticker}
                stroke={PALETTE[i]}
                strokeWidth={1.8}
                dot={false}
                activeDot={{ r: 4, fill: PALETTE[i] }}
                connectNulls={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <div style={{ textAlign: 'center', padding: '30px 0', color: 'var(--muted)', fontSize: 13 }}>
          Aggiungi un secondo ticker per confrontare i sentiment.
        </div>
      )}

      {/* Mini riepilogo per ticker */}
      {allTickers.length > 1 && mergedData.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: `repeat(${allTickers.length}, 1fr)`, gap: 8, marginTop: 14 }}>
          {allTickers.map(({ ticker, sentiment }, i) => {
            const vals = sentiment?.map(s => s.sentiment).filter(v => v != null) || []
            const avg  = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null
            const last = vals.length ? vals[vals.length - 1] : null
            const color = PALETTE[i]
            const sentColor = v => v == null ? '#94a3b8' : v > 0.1 ? '#4ade80' : v < -0.1 ? '#f87171' : '#facc15'
            return (
              <div key={ticker} style={{
                background: 'rgba(255,255,255,0.02)',
                border: `1px solid ${color}30`,
                borderRadius: 8, padding: '10px 12px',
              }}>
                <div style={{ fontSize: 10, color, fontWeight: 600, letterSpacing: '0.06em', marginBottom: 4 }}>
                  {ticker}
                </div>
                <div style={{ fontSize: 13, fontWeight: 600, color: sentColor(last) }}>
                  {last != null ? (last > 0 ? '+' : '') + last.toFixed(3) : '—'}
                </div>
                <div style={{ fontSize: 10, color: '#64748b', marginTop: 2 }}>
                  media {avg != null ? (avg > 0 ? '+' : '') + avg.toFixed(3) : '—'}
                </div>
              </div>
            )
          })}
        </div>
      )}

      <p style={{ fontSize: 10, color: 'var(--muted)', marginTop: 12, marginBottom: 0 }}>
        Sentiment giornaliero medio AI · fino a {MAX_COMPARE} ticker · solo PRO
      </p>
    </div>
  )
}

function Header() {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{
          fontSize: 10, fontWeight: 700, letterSpacing: '0.08em',
          color: '#60a5fa', background: 'rgba(96,165,250,0.1)',
          padding: '3px 9px', borderRadius: 100,
          border: '1px solid rgba(96,165,250,0.2)',
          textTransform: 'uppercase',
        }}>📊 Confronto</span>
        <h3 style={{ fontFamily: 'var(--serif)', fontSize: 18, fontWeight: 400, letterSpacing: '-0.02em', margin: 0 }}>
          Multi-ticker sentiment
        </h3>
      </div>
      <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 4, marginBottom: 0 }}>
        Sovrapponi il sentiment di più ticker per confrontarli
      </p>
    </div>
  )
}

const panelStyle = {
  background: 'rgba(255,255,255,0.02)',
  border: '1px solid var(--border)',
  borderRadius: 12, padding: '16px 20px',
}
