import { useMemo } from 'react'
import {
  ComposedChart, Scatter, Line,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts'
import Icon from './Icon.jsx'

// ── Pearson correlation ───────────────────────────────────────────────────────
function pearson(x, y) {
  const n  = x.length
  if (n < 5) return null
  const mx = x.reduce((a, b) => a + b, 0) / n
  const my = y.reduce((a, b) => a + b, 0) / n
  const num = x.reduce((s, v, i) => s + (v - mx) * (y[i] - my), 0)
  const dx  = Math.sqrt(x.reduce((s, v) => s + (v - mx) ** 2, 0))
  const dy  = Math.sqrt(y.reduce((s, v) => s + (v - my) ** 2, 0))
  return dx && dy ? parseFloat((num / (dx * dy)).toFixed(3)) : null
}

// ── Regressione lineare y = a + b*x ──────────────────────────────────────────
function linearRegression(x, y) {
  const n  = x.length
  const mx = x.reduce((a, b) => a + b, 0) / n
  const my = y.reduce((a, b) => a + b, 0) / n
  const b  = x.reduce((s, v, i) => s + (v - mx) * (y[i] - my), 0) /
             x.reduce((s, v) => s + (v - mx) ** 2, 0)
  const a  = my - b * mx
  return { a, b }
}

// ── Tooltip custom ────────────────────────────────────────────────────────────
function ScatterTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload
  if (!d) return null
  return (
    <div style={{
      background: 'var(--near-black)', border: '1px solid rgba(var(--rgb-contrasto), 0.1)',
      borderRadius: 8, padding: '10px 14px', fontSize: 12,
    }}>
      <div style={{ color: '#94a3b8', marginBottom: 6 }}>{d.date}</div>
      <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: '3px 0' }}>
        <span style={{ color: '#64748b' }}>Sentiment</span>
        <span style={{ color: d.x >= 0.1 ? '#4ade80' : d.x <= -0.1 ? '#f87171' : '#facc15', fontWeight: 600 }}>
          {d.x > 0 ? '+' : ''}{d.x.toFixed(3)}
        </span>
        <span style={{ color: '#64748b' }}>Rendimento D+1</span>
        <span style={{ color: d.y >= 0 ? '#4ade80' : '#f87171', fontWeight: 600 }}>
          {d.y > 0 ? '+' : ''}{d.y.toFixed(2)}%
        </span>
      </div>
    </div>
  )
}

// ── Dot colorato per sentiment ────────────────────────────────────────────────
function ColorDot(props) {
  const { cx, cy, payload } = props
  if (cx == null || cy == null) return null
  const color = payload.x > 0.1 ? '#4ade80' : payload.x < -0.1 ? '#f87171' : '#facc15'
  return <circle cx={cx} cy={cy} r={4} fill={color} fillOpacity={0.75} stroke={color} strokeOpacity={0.3} strokeWidth={1} />
}

// ── Componente principale ─────────────────────────────────────────────────────
export default function CorrelationPanel({ prices, sentiment, isPro, onUpgrade }) {

  // Prepara i dati: sentiment[D] → return[D+1]
  const { pairs, corr, regLine, stats } = useMemo(() => {
    if (!prices?.length || !sentiment?.length) return { pairs: [], corr: null, regLine: [], stats: null }

    // Mappa date → sentiment
    const sentMap = {}
    sentiment.forEach(s => {
      if (s.date && s.sentiment != null) sentMap[s.date] = Number(s.sentiment)
    })

    // Ordina prezzi per data
    const sortedPrices = [...prices].sort((a, b) => new Date(a.date) - new Date(b.date))

    // Costruisce coppie (sentiment D, return D+1)
    const pairs = []
    for (let i = 0; i < sortedPrices.length - 1; i++) {
      const p      = sortedPrices[i]
      const pNext  = sortedPrices[i + 1]
      const sent   = sentMap[p.date]
      if (sent == null || p.Close == null || pNext.Close == null) continue
      const ret = parseFloat(((pNext.Close - p.Close) / p.Close * 100).toFixed(3))
      pairs.push({ x: sent, y: ret, date: p.date })
    }

    if (pairs.length < 5) return { pairs, corr: null, regLine: [], stats: null }

    const xs   = pairs.map(p => p.x)
    const ys   = pairs.map(p => p.y)
    const corr = pearson(xs, ys)
    const { a, b } = linearRegression(xs, ys)

    // Due punti per la linea di regressione
    const xMin = Math.min(...xs)
    const xMax = Math.max(...xs)
    const regLine = [
      { x: parseFloat(xMin.toFixed(3)), y: parseFloat((a + b * xMin).toFixed(3)) },
      { x: parseFloat(xMax.toFixed(3)), y: parseFloat((a + b * xMax).toFixed(3)) },
    ]

    // Stats
    const posReturns = ys.filter(y => y > 0).length
    const avgPos     = ys.filter(y => y > 0).reduce((s, v) => s + v, 0) / (posReturns || 1)
    const avgNeg     = ys.filter(y => y < 0).reduce((s, v) => s + v, 0) / (ys.filter(y => y < 0).length || 1)

    // Giorni con sentiment bullish → rendimento medio D+1
    const bullPairs = pairs.filter(p => p.x > 0.1)
    const bearPairs = pairs.filter(p => p.x < -0.1)
    const avgRetBull = bullPairs.length
      ? parseFloat((bullPairs.reduce((s, p) => s + p.y, 0) / bullPairs.length).toFixed(2))
      : null
    const avgRetBear = bearPairs.length
      ? parseFloat((bearPairs.reduce((s, p) => s + p.y, 0) / bearPairs.length).toFixed(2))
      : null

    return { pairs, corr, regLine, stats: { posReturns, avgPos, avgNeg, avgRetBull, avgRetBear, n: pairs.length } }
  }, [prices, sentiment])

  // Colori e label correlazione
  const corrColor = c => c == null ? '#94a3b8'
    : c > 0.3 ? '#4ade80' : c < -0.3 ? '#f87171' : '#facc15'
  const corrLabel = c => {
    if (c == null) return 'N/D'
    if (c > 0.6)  return 'Forte positiva'
    if (c > 0.3)  return 'Moderata positiva'
    if (c < -0.6) return 'Forte negativa'
    if (c < -0.3) return 'Moderata negativa'
    return 'Debole / assente'
  }

  // Se non ci sono abbastanza dati
  if (pairs.length < 5) return (
    <div style={panelStyle}>
      <Header />
      <div style={{ textAlign: 'center', padding: '30px 0', color: 'var(--muted)', fontSize: 13 }}>
        Servono almeno 6 giorni di dati per calcolare la correlazione.
      </div>
    </div>
  )

  return (
    <div style={panelStyle}>
      <Header />

      {/* Correlazione in evidenza */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 20, flexWrap: 'wrap' }}>
        <div style={{
          background: 'rgba(var(--rgb-contrasto), 0.03)', border: `1px solid ${corrColor(corr)}40`,
          borderRadius: 12, padding: '12px 18px', minWidth: 140,
        }}>
          <div style={{ fontSize: 10, color: '#64748b', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 4 }}>
            Pearson r
          </div>
          <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: '-0.02em', color: corrColor(corr), lineHeight: 1 }}>
            {corr != null ? (corr > 0 ? '+' : '') + corr : '—'}
          </div>
          <div style={{ fontSize: 11, color: corrColor(corr), marginTop: 4 }}>
            {corrLabel(corr)}
          </div>
        </div>

        <div style={{ fontSize: 12, color: 'var(--muted)', lineHeight: 1.7, flex: 1, minWidth: 200 }}>
          Ogni punto mostra il <b style={{ color: 'var(--off-white)' }}>sentiment del giorno D</b> e il{' '}
          <b style={{ color: 'var(--off-white)' }}>rendimento del prezzo il giorno dopo (D+1)</b>.
          {corr != null && (
            <> Un r = {corr > 0 ? '+' : ''}{corr} indica una correlazione <b style={{ color: corrColor(corr) }}>{corrLabel(corr).toLowerCase().replace(/[🚀📈🔻📉➡️]/g, '').trim()}</b>.</>
          )}
        </div>
      </div>

      {/* Scatter plot — locked per free */}
      <div style={{ position: 'relative' }}>
        <div style={{ filter: isPro ? 'none' : 'blur(5px)', pointerEvents: isPro ? 'auto' : 'none' }}>
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(var(--rgb-contrasto), 0.05)" />
              <XAxis
                dataKey="x"
                type="number"
                domain={[-1, 1]}
                tickCount={9}
                tickFormatter={v => v.toFixed(1)}
                tick={{ fill: '#64748b', fontSize: 10 }}
                label={{ value: 'Sentiment (D)', fill: '#64748b', fontSize: 10, dy: 14 }}
              />
              <YAxis
                dataKey="y"
                type="number"
                tickFormatter={v => `${v > 0 ? '+' : ''}${v.toFixed(1)}%`}
                tick={{ fill: '#64748b', fontSize: 10 }}
                width={52}
              />
              <Tooltip content={<ScatterTooltip />} />

              {/* Linee di riferimento */}
              <ReferenceLine x={0}    stroke="rgba(var(--rgb-contrasto), 0.12)" strokeWidth={1} />
              <ReferenceLine y={0}    stroke="rgba(var(--rgb-contrasto), 0.12)" strokeWidth={1} />
              <ReferenceLine x={0.1}  stroke="rgba(74,222,128,0.15)"  strokeDasharray="4 3" />
              <ReferenceLine x={-0.1} stroke="rgba(248,113,113,0.15)" strokeDasharray="4 3" />

              {/* Dati scatter */}
              <Scatter
                name="Punti"
                data={pairs}
                shape={<ColorDot />}
              />

              {/* Linea di regressione */}
              {regLine.length === 2 && (
                <Line
                  data={regLine}
                  dataKey="y"
                  dot={false}
                  activeDot={false}
                  stroke="#60a5fa"
                  strokeWidth={1.5}
                  strokeDasharray="6 3"
                  legendType="none"
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        {/* Paywall overlay */}
        {!isPro && (
          <div style={{
            position: 'absolute', inset: 0,
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center',
            gap: 8,
          }}>
            <div style={{ fontSize: 13, color: 'var(--off-white)', fontWeight: 500, display: 'flex', alignItems: 'center', gap: 6 }}>
              <Icon name="lock" size={13} /> Scatter plot disponibile con Pro
            </div>
            <button onClick={onUpgrade} style={{
              fontSize: 12, color: '#a78bfa', fontWeight: 600,
              padding: '7px 18px', background: 'rgba(167,139,250,0.12)',
              borderRadius: 100, border: '1px solid rgba(167,139,250,0.3)',
              cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6,
            }}><Icon name="bolt" size={12} /> Passa a Pro — €9/mese</button>
          </div>
        )}
      </div>

      {/* Riepilogo statistiche — visibile a tutti */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 8, marginTop: 16 }}>
          <StatBlock
            label="Campione"
            value={`${stats.n} giorni`}
            sub="coppie sentiment→prezzo"
          />
          <StatBlock
            label="Rendimento medio (Bullish)"
            value={stats.avgRetBull != null ? `${stats.avgRetBull > 0 ? '+' : ''}${stats.avgRetBull}%` : '—'}
            valueColor={stats.avgRetBull != null ? (stats.avgRetBull >= 0 ? '#4ade80' : '#f87171') : '#94a3b8'}
            sub={`dopo ${isPro ? (pairs.filter(p => p.x > 0.1).length) : '?'} giorni bullish`}
            locked={!isPro}
          />
          <StatBlock
            label="Rendimento medio (Bearish)"
            value={stats.avgRetBear != null ? `${stats.avgRetBear > 0 ? '+' : ''}${stats.avgRetBear}%` : '—'}
            valueColor={stats.avgRetBear != null ? (stats.avgRetBear >= 0 ? '#4ade80' : '#f87171') : '#94a3b8'}
            sub={`dopo ${isPro ? (pairs.filter(p => p.x < -0.1).length) : '?'} giorni bearish`}
            locked={!isPro}
          />
        </div>
      )}

      <p style={{ fontSize: 10, color: 'var(--muted)', marginTop: 12, marginBottom: 0 }}>
        Correlazione di Pearson tra sentiment giornaliero e variazione % del prezzo il giorno successivo. Non è una previsione finanziaria.
      </p>
    </div>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function Header() {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{
          fontSize: 10, fontWeight: 700, letterSpacing: '0.08em',
          color: '#60a5fa', background: 'rgba(96,165,250,0.1)',
          padding: '3px 9px', borderRadius: 100,
          border: '1px solid rgba(96,165,250,0.2)',
          textTransform: 'uppercase', display: 'inline-flex', alignItems: 'center', gap: 5,
        }}><Icon name="correlation" size={11} /> Correlazione</span>
        <h3 style={{ fontFamily: 'var(--serif)', fontSize: 18, fontWeight: 400, letterSpacing: '-0.02em', margin: 0 }}>
          Sentiment → Prezzo D+1
        </h3>
      </div>
      <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 4, marginBottom: 0 }}>
        Il sentiment di oggi predice il rendimento di domani?
      </p>
    </div>
  )
}

function StatBlock({ label, value, valueColor = '#f1f5f9', sub, locked }) {
  return (
    <div style={{
      background: 'rgba(var(--rgb-contrasto), 0.02)',
      border: '1px solid rgba(var(--rgb-contrasto), 0.07)',
      borderRadius: 10, padding: '10px 12px',
    }}>
      <div style={{ fontSize: 10, color: '#64748b', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 15, fontWeight: 600, color: locked ? 'transparent' : valueColor,
        textShadow: locked ? '0 0 8px rgba(var(--rgb-contrasto), 0.3)' : 'none',
        filter: locked ? 'blur(4px)' : 'none',
      }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: 11, color: '#64748b', marginTop: 3 }}>{sub}</div>}
    </div>
  )
}

const panelStyle = {
  background: 'rgba(var(--rgb-contrasto), 0.02)',
  border: '1px solid var(--border)',
  borderRadius: 12, padding: '16px 20px',
}
