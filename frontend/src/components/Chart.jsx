import { useState, useMemo } from 'react'
import {
  ComposedChart, Area, Bar, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Cell
} from 'recharts'

// ── Tooltip personalizzato ────────────────────────────────────────────────
function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null

  const price  = payload.find(p => p.dataKey === 'Close')
  const sentim = payload.find(p => p.dataKey === 'sentiment')
  const open   = payload.find(p => p.dataKey === 'Open')
  const high   = payload.find(p => p.dataKey === 'High')
  const low    = payload.find(p => p.dataKey === 'Low')

  const sentVal  = sentim?.value ?? null
  const sentCol  = sentVal == null ? '#94a3b8' : sentVal > 0.1 ? '#4ade80' : sentVal < -0.1 ? '#f87171' : '#facc15'
  const sentLbl  = sentVal == null ? '—' : sentVal > 0.1 ? 'Bullish' : sentVal < -0.1 ? 'Bearish' : 'Neutro'

  return (
    <div style={{
      background: '#0f1117',
      border: '1px solid rgba(255,255,255,0.1)',
      borderRadius: 10,
      padding: '12px 16px',
      fontSize: 12,
      minWidth: 180,
      boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
    }}>
      <div style={{ color: '#94a3b8', marginBottom: 10, fontWeight: 500 }}>{label}</div>

      {price && (
        <div style={{ marginBottom: 8 }}>
          <div style={{ color: '#94a3b8', fontSize: 10, letterSpacing: '0.06em', marginBottom: 4 }}>PREZZO</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '3px 12px' }}>
            <Row label="Chiusura" value={`$${price.value?.toFixed(2)}`} color="#60a5fa" bold />
            {open  && <Row label="Apertura" value={`$${open.value?.toFixed(2)}`}  />}
            {high  && <Row label="Massimo"  value={`$${high.value?.toFixed(2)}`}  color="#4ade80" />}
            {low   && <Row label="Minimo"   value={`$${low.value?.toFixed(2)}`}   color="#f87171" />}
          </div>
        </div>
      )}

      {sentVal != null && (
        <div style={{ borderTop: '1px solid rgba(255,255,255,0.07)', paddingTop: 8 }}>
          <div style={{ color: '#94a3b8', fontSize: 10, letterSpacing: '0.06em', marginBottom: 4 }}>SENTIMENT</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ color: sentCol, fontWeight: 600, fontSize: 14 }}>
              {sentVal > 0 ? '+' : ''}{sentVal.toFixed(3)}
            </span>
            <span style={{
              fontSize: 10, color: sentCol,
              background: `${sentCol}18`,
              border: `1px solid ${sentCol}40`,
              borderRadius: 100, padding: '2px 8px', fontWeight: 500,
            }}>{sentLbl}</span>
          </div>
        </div>
      )}
    </div>
  )
}

function Row({ label, value, color = '#e2e8f0', bold }) {
  return (
    <div style={{ display: 'contents' }}>
      <span style={{ color: '#64748b' }}>{label}</span>
      <span style={{ color, fontWeight: bold ? 600 : 400 }}>{value}</span>
    </div>
  )
}

function formatVol(v) {
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(1)}B`
  if (v >= 1_000_000)     return `${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000)         return `${(v / 1_000).toFixed(0)}K`
  return v.toFixed(0)
}

// ── Pannello KPI prezzi ───────────────────────────────────────────────────
function PricePanel({ prices, sentiment }) {
  if (!prices.length) return null

  const last      = prices[prices.length - 1]
  const first     = prices[0]
  const change    = last.Close - first.Close
  const changePct = (change / first.Close) * 100
  const isUp      = change >= 0

  const allClose = prices.map(p => p.Close)
  const high52   = Math.max(...allClose)
  const low52    = Math.min(...allClose)

  const sentVals = sentiment.map(s => s.sentiment).filter(v => v != null)
  const avgSent  = sentVals.length ? sentVals.reduce((a, b) => a + b, 0) / sentVals.length : null
  const maxSent  = sentVals.length ? Math.max(...sentVals) : null
  const minSent  = sentVals.length ? Math.min(...sentVals) : null

  const sentCol  = avgSent == null ? '#94a3b8' : avgSent > 0.1 ? '#4ade80' : avgSent < -0.1 ? '#f87171' : '#facc15'
  const sentLbl  = avgSent == null ? '—' : avgSent > 0.1 ? 'Bullish' : avgSent < -0.1 ? 'Bearish' : 'Neutro'

  const kpis = [
    {
      label: 'Ultimo Prezzo',
      value: `$${last.Close?.toFixed(2)}`,
      sub: `${isUp ? '+' : ''}${change.toFixed(2)} (${isUp ? '+' : ''}${changePct.toFixed(2)}%)`,
      subColor: isUp ? '#4ade80' : '#f87171',
      big: true,
    },
    {
      label: 'Massimo Periodo',
      value: `$${high52.toFixed(2)}`,
      sub: `su ${prices.length} giorni`,
      subColor: '#4ade80',
    },
    {
      label: 'Minimo Periodo',
      value: `$${low52.toFixed(2)}`,
      sub: `su ${prices.length} giorni`,
      subColor: '#f87171',
    },
    {
      label: 'Sentiment Medio',
      value: avgSent != null ? `${avgSent > 0 ? '+' : ''}${avgSent.toFixed(3)}` : '—',
      sub: sentLbl,
      subColor: sentCol,
      valueColor: sentCol,
    },
    {
      label: 'Picco Positivo',
      value: maxSent != null ? `${maxSent > 0 ? '+' : ''}${maxSent.toFixed(3)}` : '—',
      sub: 'sentiment massimo',
      subColor: '#4ade80',
      valueColor: maxSent != null ? '#4ade80' : '#94a3b8',
    },
    {
      label: 'Picco Negativo',
      value: minSent != null ? `${minSent > 0 ? '+' : ''}${minSent.toFixed(3)}` : '—',
      sub: 'sentiment minimo',
      subColor: '#f87171',
      valueColor: minSent != null ? '#f87171' : '#94a3b8',
    },
    ...((() => {
      const volumes = prices.map(p => p.Volume).filter(Boolean)
      const avgVol = volumes.length ? volumes.reduce((a, b) => a + b, 0) / volumes.length : null
      return avgVol ? [{
        label: 'Scambi Giornalieri',
        value: formatVol(avgVol),
        sub: 'azioni trattate/giorno',
        subColor: '#94a3b8',
      }] : []
    })()),
  ]

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
      gap: 10,
      marginBottom: 16,
    }}>
      {kpis.map((k, i) => (
        <div key={i} style={{
          background: 'rgba(255,255,255,0.02)',
          border: '1px solid rgba(255,255,255,0.07)',
          borderRadius: 10,
          padding: '12px 14px',
        }}>
          <div style={{ fontSize: 10, color: '#64748b', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 6 }}>
            {k.label}
          </div>
          <div style={{ fontSize: k.big ? 20 : 16, fontWeight: 600, letterSpacing: '-0.02em', color: k.valueColor || '#f1f5f9', lineHeight: 1 }}>
            {k.value}
          </div>
          <div style={{ fontSize: 11, color: k.subColor, marginTop: 4 }}>
            {k.sub}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Candlestick custom shape ──────────────────────────────────────────────
function CandlestickBar(props) {
  const { x, width, payload, background, yAxis } = props
  if (!payload || !background) return null

  const open  = payload.Open
  const close = payload.Close
  const high  = payload.High ?? Math.max(open, close)
  const low   = payload.Low  ?? Math.min(open, close)
  if (open == null || close == null) return null

  const domain = yAxis?.domain ?? [0, 100]
  const domMin = Math.min(...domain)
  const domMax = Math.max(...domain)
  const chartTop    = background.y
  const chartHeight = background.height
  const toY = v => chartTop + ((domMax - v) / (domMax - domMin)) * chartHeight

  const yOpen  = toY(open)
  const yClose = toY(close)
  const yHigh  = toY(high)
  const yLow   = toY(low)

  const isUp    = close >= open
  const color   = isUp ? '#4ade80' : '#f87171'
  const bodyTop = Math.min(yOpen, yClose)
  const bodyH   = Math.max(Math.abs(yOpen - yClose), 1)
  const cx      = x + width / 2

  return (
    <g>
      <line x1={cx} y1={yHigh} x2={cx} y2={bodyTop} stroke={color} strokeWidth={1} opacity={0.8} />
      <rect x={x + 1} y={bodyTop} width={Math.max(width - 2, 2)} height={bodyH} fill={color} opacity={0.85} rx={1} />
      <line x1={cx} y1={bodyTop + bodyH} x2={cx} y2={yLow} stroke={color} strokeWidth={1} opacity={0.8} />
    </g>
  )
}

// ── Formatta date sull'asse X ─────────────────────────────────────────────
function fmtDate(d) {
  if (!d) return ''
  const parts = d.split('-')
  if (parts.length < 3) return d
  return `${parts[2]}/${parts[1]}`
}

// ── Componente principale ────────────────────────────────────────────────
export default function Chart({ prices, sentiment, ticker }) {
  const [showCandles, setShowCandles] = useState(false)

  const data = useMemo(() => {
    const sentMap = {}
    sentiment.forEach(s => { sentMap[s.date] = s.sentiment })
    return prices.map(p => ({
      ...p,
      sentiment: sentMap[p.date] ?? null,
    }))
  }, [prices, sentiment])

  const { minP, maxP } = useMemo(() => {
    if (!prices.length) return { minP: 0, maxP: 100 }
    const lows  = prices.map(p => p.Low  ?? p.Close)
    const highs = prices.map(p => p.High ?? p.Close)
    const mn = Math.min(...lows)
    const mx = Math.max(...highs)
    const pad = (mx - mn) * 0.05
    return { minP: mn - pad, maxP: mx + pad }
  }, [prices])

  if (!prices.length) return (
    <div style={{ height: 320, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748b', fontSize: 14 }}>
      Nessun dato prezzi disponibile.
    </div>
  )

  const step    = Math.max(1, Math.floor(data.length / 60))
  const display = data.filter((_, i) => i % step === 0)
  const xInterval = Math.max(0, Math.floor(display.length / 6) - 1)

  return (
    <div>
      <PricePanel prices={prices} sentiment={sentiment} />

      {/* Toggle linea / candele */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, justifyContent: 'flex-end' }}>
        {['Linea', 'Candele'].map((lbl, i) => (
          <button key={lbl} onClick={() => setShowCandles(i === 1)} style={{
            fontSize: 11, padding: '4px 12px', borderRadius: 6, cursor: 'pointer',
            background: showCandles === (i === 1) ? 'rgba(96,165,250,0.15)' : 'transparent',
            border: showCandles === (i === 1) ? '1px solid rgba(96,165,250,0.4)' : '1px solid rgba(255,255,255,0.1)',
            color: showCandles === (i === 1) ? '#60a5fa' : '#64748b',
          }}>{lbl}</button>
        ))}
      </div>

      <div style={{ marginBottom: 6 }}>
        <span style={{ fontSize: 10, color: '#475569', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
          PREZZO {showCandles ? 'OHLC' : 'CHIUSURA'} — {ticker}
        </span>
      </div>

      <ResponsiveContainer width="100%" height={220}>
        <ComposedChart data={display} margin={{ top: 4, right: 56, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor="#3b7bff" stopOpacity={0.2}/>
              <stop offset="100%" stopColor="#3b7bff" stopOpacity={0}/>
            </linearGradient>
          </defs>

          <CartesianGrid strokeDasharray="3 4" stroke="rgba(255,255,255,0.04)" vertical={false}/>

          <XAxis
            dataKey="date"
            tickFormatter={fmtDate}
            interval={xInterval}
            tick={{ fontSize: 10, fill: '#475569' }}
            axisLine={false}
            tickLine={false}
          />

          <YAxis
            yAxisId="price"
            orientation="right"
            domain={[minP, maxP]}
            tickFormatter={v => `$${v.toFixed(0)}`}
            tick={{ fontSize: 10, fill: '#475569' }}
            axisLine={false}
            tickLine={false}
            width={52}
          />

          <Tooltip content={<CustomTooltip />} />

          {/* Open/High/Low sempre presenti per il tooltip */}
          <Line yAxisId="price" dataKey="Open" dot={false} stroke="transparent" strokeWidth={0}/>
          <Line yAxisId="price" dataKey="High" dot={false} stroke="transparent" strokeWidth={0}/>
          <Line yAxisId="price" dataKey="Low"  dot={false} stroke="transparent" strokeWidth={0}/>

          {showCandles ? (
            /* Candele: Bar con shape custom */
            <Bar
              yAxisId="price"
              dataKey="Close"
              shape={<CandlestickBar />}
              isAnimationActive={false}
            />
          ) : (
            /* Linea con area fill */
            <Area
              yAxisId="price"
              dataKey="Close"
              stroke="#3b7bff"
              strokeWidth={1.8}
              fill="url(#priceGrad)"
              dot={false}
              activeDot={{ r: 4, fill: '#60a5fa', strokeWidth: 0 }}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>

      {/* Grafico sentiment */}
      <div style={{ marginTop: 12, marginBottom: 6 }}>
        <span style={{ fontSize: 10, color: '#475569', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
          SENTIMENT GIORNALIERO
        </span>
      </div>
      <ResponsiveContainer width="100%" height={100}>
        <ComposedChart data={display} margin={{ top: 4, right: 56, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 4" stroke="rgba(255,255,255,0.04)" vertical={false}/>

          <XAxis
            dataKey="date"
            tickFormatter={fmtDate}
            interval={xInterval}
            tick={{ fontSize: 10, fill: '#475569' }}
            axisLine={false}
            tickLine={false}
          />

          <YAxis
            yAxisId="sent"
            orientation="right"
            domain={[-1, 1]}
            ticks={[-1, -0.5, 0, 0.5, 1]}
            tickFormatter={v => v.toFixed(1)}
            tick={{ fontSize: 10, fill: '#475569' }}
            axisLine={false}
            tickLine={false}
            width={52}
          />

          <ReferenceLine yAxisId="sent" y={0} stroke="rgba(255,255,255,0.12)" strokeDasharray="3 4"/>

          <Tooltip content={<CustomTooltip />}/>

          <Bar yAxisId="sent" dataKey="sentiment" radius={[2, 2, 0, 0]} maxBarSize={12}>
            {display.map((entry, i) => (
              <Cell
                key={i}
                fill={
                  entry.sentiment == null ? '#334155'
                  : entry.sentiment > 0.1 ? '#4ade80'
                  : entry.sentiment < -0.1 ? '#f87171'
                  : '#facc15'
                }
                opacity={0.75}
              />
            ))}
          </Bar>
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}