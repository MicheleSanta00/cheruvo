import { useState, useMemo } from 'react'
import {
  ComposedChart, Area, Bar, Line,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Cell,
} from 'recharts'

// ── Tooltip hover ─────────────────────────────────────────────────────────
function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null

  const get   = key => payload.find(p => p.dataKey === key)?.value
  const close = get('Close')
  const open  = get('Open')
  const high  = get('High')
  const low   = get('Low')
  const sent  = get('sentiment')

  const sentCol = sent == null ? '#94a3b8'
    : sent > 0.1 ? '#4ade80' : sent < -0.1 ? '#f87171' : '#facc15'
  const sentLbl = sent == null ? '—'
    : sent > 0.1 ? 'Bullish' : sent < -0.1 ? 'Bearish' : 'Neutro'

  return (
    <div style={{
      background: '#0f1117', border: '1px solid rgba(255,255,255,0.1)',
      borderRadius: 10, padding: '12px 16px', fontSize: 12,
      minWidth: 190, boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
    }}>
      <div style={{ color: '#94a3b8', marginBottom: 10, fontWeight: 500 }}>{label}</div>
      {close != null && (
        <div style={{ marginBottom: 8 }}>
          <div style={{ color: '#475569', fontSize: 10, letterSpacing: '0.06em', marginBottom: 5 }}>PREZZO</div>
          <div style={{ display: 'grid', gridTemplateColumns: '80px 1fr', gap: '4px 0' }}>
            <span style={{ color: '#64748b' }}>Chiusura</span>
            <span style={{ color: '#60a5fa', fontWeight: 600 }}>${close?.toFixed(2)}</span>
            {open  != null && <><span style={{ color: '#64748b' }}>Apertura</span><span style={{ color: '#e2e8f0' }}>${open?.toFixed(2)}</span></>}
            {high  != null && <><span style={{ color: '#64748b' }}>Massimo</span><span style={{ color: '#4ade80' }}>${high?.toFixed(2)}</span></>}
            {low   != null && <><span style={{ color: '#64748b' }}>Minimo</span><span style={{ color: '#f87171' }}>${low?.toFixed(2)}</span></>}
            {open  != null && <>
              <span style={{ color: '#64748b' }}>Variazione</span>
              <span style={{ color: close >= open ? '#4ade80' : '#f87171' }}>
                {close >= open ? '+' : ''}{(close - open).toFixed(2)} ({((close - open) / open * 100).toFixed(2)}%)
              </span>
            </>}
          </div>
        </div>
      )}
      {sent != null && (
        <div style={{ borderTop: '1px solid rgba(255,255,255,0.07)', paddingTop: 8 }}>
          <div style={{ color: '#475569', fontSize: 10, letterSpacing: '0.06em', marginBottom: 5 }}>SENTIMENT</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ color: sentCol, fontWeight: 700, fontSize: 15 }}>
              {sent > 0 ? '+' : ''}{sent.toFixed(3)}
            </span>
            <span style={{
              fontSize: 10, color: sentCol, background: `${sentCol}18`,
              border: `1px solid ${sentCol}40`, borderRadius: 100,
              padding: '2px 8px', fontWeight: 500,
            }}>{sentLbl}</span>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Candlestick: usa closure con minP/maxP + background rect ──────────────
// recharts NON passa yAxis alla custom shape — bisogna ricostruire la scala
// manualmente dai valori noti del dominio e dall'altezza del background rect.
function makeCandleShape(minP, maxP) {
  const range = maxP - minP || 1
  return function CandleShape({ x, width, background, payload }) {
    if (!payload || !background) return null
    const { Open, Close, High, Low } = payload
    if (Open == null || Close == null) return null

    const top = background.y          // coordinata y del top del chart
    const h   = background.height     // altezza totale del chart
    const toY = v => top + h * (1 - (v - minP) / range)

    const isUp    = Close >= Open
    const color   = isUp ? '#4ade80' : '#f87171'
    const bodyTop = Math.min(toY(Open), toY(Close))
    const bodyBot = Math.max(toY(Open), toY(Close))
    const bodyH   = Math.max(1.5, bodyBot - bodyTop)
    const cx      = x + width / 2
    const cw      = Math.max(4, width * 0.6)

    return (
      <g>
        <line x1={cx} y1={toY(High ?? Math.max(Open, Close))}
              x2={cx} y2={bodyTop} stroke={color} strokeWidth={1} opacity={0.7}/>
        <rect x={cx - cw / 2} y={bodyTop} width={cw} height={bodyH}
              fill={color} rx={1}/>
        <line x1={cx} y1={bodyBot}
              x2={cx} y2={toY(Low ?? Math.min(Open, Close))} stroke={color} strokeWidth={1} opacity={0.7}/>
      </g>
    )
  }
}

// ── Pannello dati ─────────────────────────────────────────────────────────
// stats = { avg, max, min, total, sources } da /api/news  (coerente con KPIGrid)
// sentiment = array giornaliero da /api/sentiment (usato solo per conteggio giorni)
function DataPanel({ prices, sentiment, stats }) {
  if (!prices.length) return null

  const last   = prices[prices.length - 1]
  const first  = prices[0]
  const change = last.Close - first.Close
  const pct    = (change / first.Close) * 100
  const isUp   = change >= 0

  const closes = prices.map(p => p.Close)
  const high   = Math.max(...closes)
  const low    = Math.min(...closes)

  // Conteggio giorni bullish/bearish/neutri dall'array sentiment giornaliero
  const sentVals    = sentiment.map(s => s.sentiment).filter(v => v != null)
  const bullishDays = sentVals.filter(v => v > 0.1).length
  const bearishDays = sentVals.filter(v => v < -0.1).length
  const neutralDays = sentVals.filter(v => v >= -0.1 && v <= 0.1).length
  const total       = sentVals.length || 1
  const lastSent    = sentVals.length ? sentVals[sentVals.length - 1] : null

  // Valori avg/max/min da stats (= stessa fonte di KPIGrid → coerenti)
  const avgSent = stats?.avg ?? null
  const maxSent = stats?.max ?? null
  const minSent = stats?.min ?? null

  const sentColor = v => v == null ? '#94a3b8'
    : v > 0.1 ? '#4ade80' : v < -0.1 ? '#f87171' : '#facc15'
  const sentLabel = v => v == null ? '—'
    : v > 0.1 ? 'Bullish' : v < -0.1 ? 'Bearish' : 'Neutro'

  const Block = ({ label, value, sub, valueColor = '#f1f5f9', big }) => (
    <div style={{
      background: 'rgba(255,255,255,0.02)',
      border: '1px solid rgba(255,255,255,0.07)',
      borderRadius: 10, padding: '12px 14px',
    }}>
      <div style={{ fontSize: 10, color: '#64748b', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ fontSize: big ? 20 : 15, fontWeight: 600, letterSpacing: '-0.02em', color: valueColor, lineHeight: 1 }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: 11, marginTop: 4 }}>{sub}</div>}
    </div>
  )

  const fmt = v => v == null ? '—' : `${v > 0 ? '+' : ''}${Number(v).toFixed(3)}`

  return (
    <div style={{ marginBottom: 20 }}>

      {/* Prezzi */}
      <div style={{ fontSize: 10, color: '#475569', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8 }}>
        📈 Prezzi
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 8, marginBottom: 16 }}>
        <Block label="Ultimo prezzo" value={`$${last.Close?.toFixed(2)}`} big
          sub={<span style={{ color: isUp ? '#4ade80' : '#f87171' }}>
            {isUp ? '+' : ''}{change.toFixed(2)} ({isUp ? '+' : ''}{pct.toFixed(2)}%) sul periodo
          </span>}
        />
        <Block label="Apertura periodo" value={`$${(first.Open ?? first.Close)?.toFixed(2)}`}
          sub={<span style={{ color: '#64748b' }}>{first.date}</span>}
        />
        <Block label="Massimo periodo" value={`$${high.toFixed(2)}`} valueColor="#4ade80"
          sub={<span style={{ color: '#64748b' }}>su {prices.length} candele</span>}
        />
        <Block label="Minimo periodo" value={`$${low.toFixed(2)}`} valueColor="#f87171"
          sub={<span style={{ color: '#64748b' }}>su {prices.length} candele</span>}
        />
      </div>

      {/* Sentiment */}
      {(avgSent != null || sentVals.length > 0) && (
        <>
          <div style={{ fontSize: 10, color: '#475569', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8 }}>
            🧠 Sentiment news
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 8 }}>
            <Block label="Sentiment recente" value={fmt(lastSent)} big
              valueColor={sentColor(lastSent)}
              sub={<span style={{ color: sentColor(lastSent) }}>{sentLabel(lastSent)}</span>}
            />
            <Block label="Sentiment medio" value={fmt(avgSent)}
              valueColor={sentColor(avgSent)}
              sub={<span style={{ color: sentColor(avgSent) }}>{sentLabel(avgSent)}</span>}
            />
            <Block label="Picco positivo" value={fmt(maxSent)}
              valueColor="#4ade80"
              sub={<span style={{ color: '#64748b' }}>massimo registrato</span>}
            />
            <Block label="Picco negativo" value={fmt(minSent)}
              valueColor="#f87171"
              sub={<span style={{ color: '#64748b' }}>minimo registrato</span>}
            />
            <Block label="Giorni bullish" value={`${bullishDays} gg`}
              valueColor="#4ade80"
              sub={<span style={{ color: '#64748b' }}>{((bullishDays / total) * 100).toFixed(0)}% del periodo</span>}
            />
            <Block label="Giorni bearish" value={`${bearishDays} gg`}
              valueColor="#f87171"
              sub={<span style={{ color: '#64748b' }}>{((bearishDays / total) * 100).toFixed(0)}% del periodo</span>}
            />
            <Block label="Giorni neutri" value={`${neutralDays} gg`}
              valueColor="#facc15"
              sub={<span style={{ color: '#64748b' }}>{((neutralDays / total) * 100).toFixed(0)}% del periodo</span>}
            />
          </div>
        </>
      )}
    </div>
  )
}

const fmtDate = d => {
  if (!d) return ''
  const p = d.split('-')
  return p.length >= 3 ? `${p[2]}/${p[1]}` : d
}

// ── Componente principale ─────────────────────────────────────────────────
export default function Chart({ prices, sentiment, ticker, stats }) {
  const [showCandles, setShowCandles] = useState(false)

  const data = useMemo(() => {
    const sentMap = {}
    sentiment.forEach(s => { sentMap[s.date] = s.sentiment })
    return prices.map(p => ({ ...p, sentiment: sentMap[p.date] ?? null }))
  }, [prices, sentiment])

  const { minP, maxP } = useMemo(() => {
    if (!prices.length) return { minP: 0, maxP: 100 }
    const lows  = prices.map(p => p.Low  ?? p.Close)
    const highs = prices.map(p => p.High ?? p.Close)
    const mn = Math.min(...lows)
    const mx = Math.max(...highs)
    const pad = (mx - mn) * 0.06
    return { minP: mn - pad, maxP: mx + pad }
  }, [prices])

  // CandleShape ricreata solo quando cambia il range prezzi
  const CandleShape = useMemo(() => makeCandleShape(minP, maxP), [minP, maxP])

  if (!prices.length) return (
    <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748b', fontSize: 14 }}>
      Nessun dato prezzi disponibile.
    </div>
  )

  const step    = Math.max(1, Math.floor(data.length / 80))
  const display = data.filter((_, i) => i % step === 0)
  const xInt    = Math.max(0, Math.floor(display.length / 6) - 1)

  return (
    <div>
      <DataPanel prices={prices} sentiment={sentiment} stats={stats} />

      {/* Toggle */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, justifyContent: 'flex-end' }}>
        {['Linea', 'Candele'].map((lbl, i) => {
          const active = showCandles === (i === 1)
          return (
            <button key={lbl} onClick={() => setShowCandles(i === 1)} style={{
              fontSize: 11, padding: '4px 12px', borderRadius: 6, cursor: 'pointer',
              background: active ? 'rgba(96,165,250,0.15)' : 'transparent',
              border: active ? '1px solid rgba(96,165,250,0.4)' : '1px solid rgba(255,255,255,0.1)',
              color: active ? '#60a5fa' : '#64748b',
            }}>{lbl}</button>
          )
        })}
      </div>

      {/* Label */}
      <div style={{ marginBottom: 6 }}>
        <span style={{ fontSize: 10, color: '#475569', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
          PREZZO {showCandles ? 'OHLC' : 'CHIUSURA'} — {ticker}
        </span>
      </div>

      {/* Grafico prezzi */}
      <ResponsiveContainer width="100%" height={220}>
        <ComposedChart data={display} margin={{ top: 4, right: 60, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor="#3b7bff" stopOpacity={0.2}/>
              <stop offset="100%" stopColor="#3b7bff" stopOpacity={0}/>
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 4" stroke="rgba(255,255,255,0.04)" vertical={false}/>
          <XAxis dataKey="date" tickFormatter={fmtDate} interval={xInt}
            tick={{ fontSize: 10, fill: '#475569' }} axisLine={false} tickLine={false}/>
          <YAxis yAxisId="price" orientation="right" domain={[minP, maxP]}
            tickFormatter={v => `$${v.toFixed(0)}`}
            tick={{ fontSize: 10, fill: '#475569' }} axisLine={false} tickLine={false} width={54}/>
          <Tooltip content={<CustomTooltip />}/>

          {/* Open/High/Low invisibili ma inclusi nel payload del tooltip */}
          {['Open','High','Low'].map(k => (
            <Line key={k} yAxisId="price" dataKey={k}
              dot={false} stroke="transparent" strokeWidth={0}/>
          ))}

          {showCandles ? (
            <Bar yAxisId="price" dataKey="Close"
              shape={<CandleShape />}
              isAnimationActive={false}/>
          ) : (
            <Area yAxisId="price" dataKey="Close"
              stroke="#3b7bff" strokeWidth={1.8}
              fill="url(#priceGrad)" dot={false}
              activeDot={{ r: 4, fill: '#60a5fa', strokeWidth: 0 }}/>
          )}
        </ComposedChart>
      </ResponsiveContainer>

      {/* Grafico sentiment */}
      <div style={{ marginTop: 16, marginBottom: 6 }}>
        <span style={{ fontSize: 10, color: '#475569', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
          SENTIMENT GIORNALIERO
        </span>
      </div>
      <ResponsiveContainer width="100%" height={100}>
        <ComposedChart data={display} margin={{ top: 4, right: 60, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 4" stroke="rgba(255,255,255,0.04)" vertical={false}/>
          <XAxis dataKey="date" tickFormatter={fmtDate} interval={xInt}
            tick={{ fontSize: 10, fill: '#475569' }} axisLine={false} tickLine={false}/>
          <YAxis yAxisId="sent" orientation="right" domain={[-1, 1]}
            ticks={[-1, -0.5, 0, 0.5, 1]} tickFormatter={v => v.toFixed(1)}
            tick={{ fontSize: 10, fill: '#475569' }} axisLine={false} tickLine={false} width={34}/>
          <ReferenceLine yAxisId="sent" y={0} stroke="rgba(255,255,255,0.12)" strokeDasharray="3 4"/>
          <Tooltip content={<CustomTooltip />}/>
          <Bar yAxisId="sent" dataKey="sentiment" radius={[2,2,0,0]} maxBarSize={12}>
            {display.map((d, i) => (
              <Cell key={i} opacity={0.75}
                fill={d.sentiment == null ? '#334155'
                  : d.sentiment > 0.1 ? '#4ade80'
                  : d.sentiment < -0.1 ? '#f87171'
                  : '#facc15'}
              />
            ))}
          </Bar>
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}