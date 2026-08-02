import { useState, useMemo, useEffect } from 'react'
import {
  ComposedChart, Area, Bar, Line,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Cell,
} from 'recharts'
import Icon from './Icon.jsx'

// ── Rileva schermi piccoli (per proporzioni grafico e tooltip) ────────────
function useIsMobile() {
  const [m, setM] = useState(typeof window !== 'undefined' && window.innerWidth <= 640)
  useEffect(() => {
    const on = () => setM(window.innerWidth <= 640)
    window.addEventListener('resize', on)
    return () => window.removeEventListener('resize', on)
  }, [])
  return m
}

// ── Tooltip hover ─────────────────────────────────────────────────────────
function CustomTooltip({ active, payload, label, compact }) {
  if (!active || !payload?.length) return null

  const get   = key => payload.find(p => p.dataKey === key)?.value
  const close = get('Close')
  const open  = get('Open')
  const high  = get('High')
  const low   = get('Low')
  const vol   = get('Volume')
  const sent  = get('sentiment')
  const ma    = get('sentMA')

  const sentVal = sent ?? ma
  const sentCol = sentVal == null ? '#94a3b8'
    : sentVal > 0.1 ? '#4ade80' : sentVal < -0.1 ? '#f87171' : '#facc15'
  const sentLbl = sentVal == null ? '—'
    : sentVal > 0.1 ? 'Bullish' : sentVal < -0.1 ? 'Bearish' : 'Neutro'

  const fmtVol = v => {
    if (!v) return '—'
    if (v >= 1e9) return `${(v/1e9).toFixed(2)}B`
    if (v >= 1e6) return `${(v/1e6).toFixed(2)}M`
    if (v >= 1e3) return `${(v/1e3).toFixed(0)}K`
    return v
  }

  return (
    <div style={{
      background: '#0f1117', border: '1px solid rgba(255,255,255,0.1)',
      borderRadius: 10, padding: compact ? '8px 10px' : '12px 16px', fontSize: compact ? 11 : 12,
      minWidth: compact ? 148 : 190, maxWidth: compact ? 185 : undefined,
      boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
    }}>
      <div style={{ color: '#94a3b8', marginBottom: compact ? 6 : 10, fontWeight: 500 }}>{label}</div>
      {close != null && (
        <div style={{ marginBottom: 8 }}>
          <div style={{ color: '#475569', fontSize: 10, letterSpacing: '0.06em', marginBottom: 5 }}>PREZZO</div>
          <div style={{ display: 'grid', gridTemplateColumns: compact ? '68px 1fr' : '80px 1fr', gap: '4px 0' }}>
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
            {vol   != null && <><span style={{ color: '#64748b' }}>Volume</span><span style={{ color: '#94a3b8' }}>{fmtVol(vol)}</span></>}
          </div>
        </div>
      )}
      {sentVal != null && (
        <div style={{ borderTop: '1px solid rgba(255,255,255,0.07)', paddingTop: 8 }}>
          <div style={{ color: '#475569', fontSize: 10, letterSpacing: '0.06em', marginBottom: 5 }}>SENTIMENT</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ color: sentCol, fontWeight: 700, fontSize: 15 }}>
              {sentVal > 0 ? '+' : ''}{sentVal.toFixed(3)}
            </span>
            <span style={{
              fontSize: 10, color: sentCol, background: `${sentCol}18`,
              border: `1px solid ${sentCol}40`, borderRadius: 100,
              padding: '2px 8px', fontWeight: 500,
            }}>{sentLbl}</span>
          </div>
          {ma != null && sent != null && (
            <div style={{ fontSize: 11, color: '#64748b', marginTop: 4 }}>
              MA7: {ma > 0 ? '+' : ''}{ma.toFixed(3)}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Calcola media mobile N giorni ─────────────────────────────────────────
function movingAverage(data, key, n = 7) {
  return data.map((d, i) => {
    const slice = data.slice(Math.max(0, i - n + 1), i + 1)
      .map(x => x[key])
      .filter(v => v != null)
    if (!slice.length) return null
    return parseFloat((slice.reduce((a, b) => a + b, 0) / slice.length).toFixed(4))
  })
}

// ── Calcola correlazione di Pearson tra due array ─────────────────────────
function pearsonCorrelation(x, y) {
  const pairs = x.map((v, i) => [v, y[i]]).filter(([a, b]) => a != null && b != null)
  if (pairs.length < 5) return null
  const n  = pairs.length
  const mx = pairs.reduce((s, [a]) => s + a, 0) / n
  const my = pairs.reduce((s, [, b]) => s + b, 0) / n
  const num = pairs.reduce((s, [a, b]) => s + (a - mx) * (b - my), 0)
  const dx  = Math.sqrt(pairs.reduce((s, [a]) => s + (a - mx) ** 2, 0))
  const dy  = Math.sqrt(pairs.reduce((s, [, b]) => s + (b - my) ** 2, 0))
  return dx && dy ? parseFloat((num / (dx * dy)).toFixed(3)) : null
}

// ── Candlestick shape ─────────────────────────────────────────────────────
function makeCandleShape(minP, maxP) {
  const range = maxP - minP || 1
  return function CandleShape({ x, width, background, payload }) {
    if (!payload || !background) return null
    const { Open, Close, High, Low } = payload
    if (Open == null || Close == null) return null

    const top = background.y
    const h   = background.height
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

// ── Pannello statistiche ──────────────────────────────────────────────────
function DataPanel({ prices, sentiment, stats, correlation }) {
  if (!prices.length) return null

  const last   = prices[prices.length - 1]
  const first  = prices[0]
  const change = last.Close - first.Close
  const pct    = (change / first.Close) * 100
  const isUp   = change >= 0

  const closes = prices.map(p => p.Close)
  const high   = Math.max(...closes)
  const low    = Math.min(...closes)

  const sentVals    = sentiment.map(s => s.sentiment).filter(v => v != null)
  const bullishDays = sentVals.filter(v => v > 0.1).length
  const bearishDays = sentVals.filter(v => v < -0.1).length
  const neutralDays = sentVals.filter(v => v >= -0.1 && v <= 0.1).length
  const total       = sentVals.length || 1
  const lastSent    = sentVals.length ? sentVals[sentVals.length - 1] : null

  const avgSent = stats?.avg ?? null
  const maxSent = stats?.max ?? null
  const minSent = stats?.min ?? null

  const sentColor = v => v == null ? '#94a3b8'
    : v > 0.1 ? '#4ade80' : v < -0.1 ? '#f87171' : '#facc15'
  const sentLabel = v => v == null ? '—'
    : v > 0.1 ? 'Bullish' : v < -0.1 ? 'Bearish' : 'Neutro'

  const corrColor = c => c == null ? '#94a3b8'
    : c > 0.3 ? '#4ade80' : c < -0.3 ? '#f87171' : '#facc15'
  const corrLabel = c => c == null ? 'N/D'
    : c > 0.5 ? 'Forte positiva' : c > 0.3 ? 'Moderata positiva'
    : c < -0.5 ? 'Forte negativa' : c < -0.3 ? 'Moderata negativa'
    : 'Debole / assente'

  // Celle piatte, non schedine arrotondate: stesso linguaggio della striscia
  // KPI in alto. Numeri monospaziati e tabellari così le cifre restano
  // incolonnate quando cambiano.
  const Block = ({ label, value, sub, valueColor = 'var(--off-white)', big }) => (
    <div style={{
      background: 'var(--near-black)',
      border: '1px solid var(--border)',
      padding: '9px 12px',
    }}>
      <div style={{ fontSize: 9.5, color: 'var(--muted)', letterSpacing: '0.12em', textTransform: 'uppercase', fontWeight: 700, marginBottom: 5 }}>
        {label}
      </div>
      <div style={{
        fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums',
        fontSize: big ? 19 : 15, fontWeight: 700, color: valueColor, lineHeight: 1,
      }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: 10.5, marginTop: 4 }}>{sub}</div>}
    </div>
  )

  const fmt = v => v == null ? '—' : `${v > 0 ? '+' : ''}${Number(v).toFixed(3)}`

  return (
    <div style={{ marginBottom: 20 }}>

      {/* Prezzi */}
      <div style={{ fontSize: 10, color: '#475569', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 5 }}>
        <Icon name="analyzer" size={12} /> Prezzi
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 1, background: 'var(--border)', marginBottom: 16 }}>
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

      {/* Sentiment + Correlazione */}
      {(avgSent != null || sentVals.length > 0) && (
        <>
          <div style={{ fontSize: 10, color: '#475569', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 5 }}>
            <Icon name="ai-brain" size={12} /> Sentiment & Correlazione
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 1, background: 'var(--border)' }}>
            <Block label="Sentiment recente" value={fmt(lastSent)} big
              valueColor={sentColor(lastSent)}
              sub={<span style={{ color: sentColor(lastSent) }}>{sentLabel(lastSent)}</span>}
            />
            {/* Sentiment medio e picchi stanno già nella striscia in alto:
                ripeterli qui significava mostrare gli stessi numeri due volte,
                con due stili diversi. Qui resta solo ciò che è specifico del
                grafico: il dato più recente, la correlazione e i conteggi. */}

            {/* Correlazione sentiment/prezzo */}
            <Block
              label="Correlazione sent/prezzo"
              value={correlation != null ? (correlation > 0 ? '+' : '') + correlation : 'N/D'}
              valueColor={corrColor(correlation)}
              sub={<span style={{ color: corrColor(correlation) }}>{corrLabel(correlation)}</span>}
            />

            <Block label="Giorni bullish" value={`${bullishDays} gg`} valueColor="#4ade80"
              sub={<span style={{ color: '#64748b' }}>{((bullishDays / total) * 100).toFixed(0)}% del periodo</span>}
            />
            <Block label="Giorni bearish" value={`${bearishDays} gg`} valueColor="#f87171"
              sub={<span style={{ color: '#64748b' }}>{((bearishDays / total) * 100).toFixed(0)}% del periodo</span>}
            />
            <Block label="Giorni neutri" value={`${neutralDays} gg`} valueColor="#facc15"
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

// Interruttori del grafico: squadrati e in maiuscoletto come il resto della
// plancia. Erano pillole arrotondate, l'unica cosa tonda in tutta la pagina.
const stileInterruttore = {
  fontSize: 10, letterSpacing: '.1em', textTransform: 'uppercase', fontWeight: 700,
  padding: '4px 10px', borderRadius: 3, border: '1px solid var(--border-br)',
  fontFamily: 'var(--sans)',
}

// ── Componente principale ─────────────────────────────────────────────────
export default function Chart({ prices, sentiment, ticker, stats }) {
  const [showCandles, setShowCandles] = useState(false)
  const [showMA, setShowMA]           = useState(true)
  const isMobile = useIsMobile()

  const data = useMemo(() => {
    const sentMap = {}
    sentiment.forEach(s => { sentMap[s.date] = s.sentiment })

    const merged = prices.map(p => ({ ...p, sentiment: sentMap[p.date] ?? null }))

    // Calcola MA7 sul sentiment
    const maValues = movingAverage(merged, 'sentiment', 7)
    return merged.map((d, i) => ({ ...d, sentMA: maValues[i] }))
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

  // Correlazione Pearson tra sentiment e variazione prezzo stesso giorno
  const correlation = useMemo(() => {
    const sentArr  = data.map(d => d.sentiment)
    const priceChg = data.map(d =>
      d.Open != null && d.Close != null ? (d.Close - d.Open) / d.Open : null
    )
    return pearsonCorrelation(sentArr, priceChg)
  }, [data])

  const CandleShape = useMemo(() => makeCandleShape(minP, maxP), [minP, maxP])

  // Filtra sentiment per includere solo le date nel range dei prezzi
  const filteredSentiment = useMemo(() => {
    if (!prices.length) return sentiment
    const dateSet = new Set(prices.map(p => p.date))
    return sentiment.filter(s => dateSet.has(s.date))
  }, [sentiment, prices])

  if (!prices.length) return (
    <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748b', fontSize: 14 }}>
      Nessun dato prezzi disponibile.
    </div>
  )

  const step    = Math.max(1, Math.floor(data.length / 80))
  const display = data.filter((_, i) => i % step === 0)
  // Su mobile meno etichette sull'asse X (altrimenti si accavallano)
  const xInt    = Math.max(0, Math.floor(display.length / (isMobile ? 4 : 6)) - 1)
  const yW      = isMobile ? 46 : 54       // larghezza asse Y (uguale nei due grafici: restano allineati)
  const chartMargin = { top: 4, right: isMobile ? 4 : 16, left: 0, bottom: 0 }

  const hasVolume = display.some(d => d.Volume > 0)
  const maxVol    = hasVolume ? Math.max(...display.map(d => d.Volume ?? 0)) : 1

  return (
    <div>
      <DataPanel prices={prices} sentiment={filteredSentiment} stats={stats} correlation={correlation} />

      {/* Toggle Linea/Candele + MA */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
        {['Linea', 'Candele'].map((lbl, i) => {
          const active = showCandles === (i === 1)
          return (
            <button key={lbl} onClick={() => setShowCandles(i === 1)} style={{
              ...stileInterruttore, cursor: 'pointer',
              background: active ? 'rgba(96,165,250,0.14)' : 'transparent',
              borderColor: active ? 'rgba(96,165,250,0.45)' : 'var(--border-br)',
              color: active ? 'var(--azure)' : 'var(--muted)',
            }}>{lbl}</button>
          )
        })}
        <button onClick={() => setShowMA(v => !v)} style={{
          ...stileInterruttore, cursor: 'pointer',
          background: showMA ? 'rgba(250,204,21,0.12)' : 'transparent',
          borderColor: showMA ? 'rgba(250,204,21,0.4)' : 'var(--border-br)',
          color: showMA ? '#facc15' : 'var(--muted)',
        }}>MA7 Sentiment</button>
      </div>

      {/* Label */}
      <div style={{ marginBottom: 6 }}>
        <span style={{ fontSize: 10, color: '#475569', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
          PREZZO {showCandles ? 'OHLC' : 'CHIUSURA'} — {ticker}
        </span>
      </div>

      {/* Grafico prezzi + volume */}
      <ResponsiveContainer width="100%" height={isMobile ? 250 : 220}>
        <ComposedChart data={display} margin={chartMargin}>
          <defs>
            <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor="#3b7bff" stopOpacity={0.2}/>
              <stop offset="100%" stopColor="#3b7bff" stopOpacity={0}/>
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 4" stroke="rgba(255,255,255,0.04)" vertical={false}/>
          {/* preserveStartEnd: l'ultimo giorno viene SEMPRE etichettato.
              Con il solo interval numerico l'asse si fermava a un tick prima
              della fine (es. "30/07" mentre il dato arrivava al 31/07) e
              sembrava che i prezzi fossero fermi da un giorno. */}
          <XAxis dataKey="date" tickFormatter={fmtDate} interval="preserveStartEnd" minTickGap={isMobile ? 44 : 60}
            tick={{ fontSize: 10, fill: '#475569' }} axisLine={false} tickLine={false}/>
          <YAxis yAxisId="price" orientation="right" domain={[minP, maxP]}
            tickFormatter={v => `$${v.toFixed(0)}`}
            tick={{ fontSize: 10, fill: '#475569' }} axisLine={false} tickLine={false} width={yW}/>
          {hasVolume && (
            <YAxis yAxisId="vol" orientation="left" domain={[0, maxVol * 4]}
              tick={false} axisLine={false} tickLine={false} width={0}/>
          )}
          <Tooltip content={<CustomTooltip compact={isMobile} />}/>

          {/* Volume bars (sfondo, molto sottili) */}
          {hasVolume && (
            <Bar yAxisId="vol" dataKey="Volume" maxBarSize={8} radius={[2,2,0,0]} isAnimationActive={false}>
              {display.map((d, i) => (
                <Cell key={i} fill={d.Close >= (d.Open ?? d.Close) ? 'rgba(74,222,128,0.2)' : 'rgba(248,113,113,0.2)'} />
              ))}
            </Bar>
          )}

          {/* Open/High/Low per tooltip */}
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

      {/* Grafico sentiment + MA7 */}
      <div style={{ marginTop: 16, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ fontSize: 10, color: '#475569', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
          SENTIMENT GIORNALIERO
        </span>
        {showMA && (
          <span style={{ fontSize: 10, color: '#facc15', display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 16, height: 2, background: '#facc15', display: 'inline-block', borderRadius: 1 }}/>
            Media mobile 7 giorni
          </span>
        )}
      </div>

      <ResponsiveContainer width="100%" height={isMobile ? 150 : 120}>
        <ComposedChart data={display} margin={chartMargin}>
          <CartesianGrid strokeDasharray="3 4" stroke="rgba(255,255,255,0.04)" vertical={false}/>
          {/* preserveStartEnd: l'ultimo giorno viene SEMPRE etichettato.
              Con il solo interval numerico l'asse si fermava a un tick prima
              della fine (es. "30/07" mentre il dato arrivava al 31/07) e
              sembrava che i prezzi fossero fermi da un giorno. */}
          <XAxis dataKey="date" tickFormatter={fmtDate} interval="preserveStartEnd" minTickGap={isMobile ? 44 : 60}
            tick={{ fontSize: 10, fill: '#475569' }} axisLine={false} tickLine={false}/>
          <YAxis yAxisId="sent" orientation="right" domain={[-1, 1]}
            ticks={[-1, -0.5, 0, 0.5, 1]} tickFormatter={v => v.toFixed(1)}
            tick={{ fontSize: 10, fill: '#475569' }} axisLine={false} tickLine={false} width={yW}/>
          <ReferenceLine yAxisId="sent" y={0} stroke="rgba(255,255,255,0.12)" strokeDasharray="3 4"/>
          <ReferenceLine yAxisId="sent" y={0.1}  stroke="rgba(74,222,128,0.1)"  strokeDasharray="2 4"/>
          <ReferenceLine yAxisId="sent" y={-0.1} stroke="rgba(248,113,113,0.1)" strokeDasharray="2 4"/>
          <Tooltip content={<CustomTooltip compact={isMobile} />}/>

          <Bar yAxisId="sent" dataKey="sentiment" radius={[2,2,0,0]} maxBarSize={12} isAnimationActive={false}>
            {display.map((d, i) => (
              <Cell key={i} opacity={0.7}
                fill={d.sentiment == null ? '#334155'
                  : d.sentiment > 0.1 ? '#4ade80'
                  : d.sentiment < -0.1 ? '#f87171'
                  : '#facc15'}
              />
            ))}
          </Bar>

          {/* MA7 come linea sovrapposta */}
          {showMA && (
            <Line yAxisId="sent" dataKey="sentMA"
              stroke="#facc15" strokeWidth={1.5}
              dot={false} strokeDasharray="0"
              activeDot={{ r: 3, fill: '#facc15', strokeWidth: 0 }}
            />
          )}

          {/* Il Brush è stato tolto di proposito. Apparteneva solo a questo
              grafico e partiva zoomato sugli ultimi 30 giorni: il sentiment
              sotto copriva quindi un periodo diverso dai prezzi sopra, e i due
              assi non combaciavano proprio dove servono di più, cioè quando li
              confronti. Il periodo ora lo governano i pulsanti 1M/3M/6M/1A,
              che valgono per entrambi i grafici. */}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
