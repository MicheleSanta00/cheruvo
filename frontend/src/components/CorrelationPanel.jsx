import { useMemo } from 'react'
import {
  ComposedChart, Scatter, Line,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts'
import Icon from './Icon.jsx'
import {
  MIN_COPPIE, MIN_GIORNI_MEDIA, correlazione, mediaConBanda,
  compatibileConZero, etichetta, spiegazione,
} from '../utils/incertezza.js'

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
        <span style={{ color: d.x >= 0.1 ? '#4ade80' : d.x <= -0.1 ? '#f87171' : 'var(--giallo)', fontWeight: 600 }}>
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
  const color = payload.x > 0.1 ? '#4ade80' : payload.x < -0.1 ? '#f87171' : 'var(--giallo)'
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

    const xs   = pairs.map(p => p.x)
    const ys   = pairs.map(p => p.y)
    const corr = correlazione(xs, ys)

    // Lo scatter si mostra anche sotto le venti coppie: i punti sono dati veri
    // e guardarli non fa danno. Quello che non si mostra sotto le venti è il
    // NUMERO, perché è quello che viene scambiato per una misura. Sotto le
    // cinque coppie non c'è nemmeno abbastanza per disegnare qualcosa.
    if (pairs.length < 5) return { pairs, corr, regLine: [], stats: null }

    // La retta di regressione si disegna SOLO se la correlazione è
    // distinguibile da zero. Una riga che attraversa la nuvola in diagonale è
    // un'affermazione più forte del numero che le sta accanto: l'occhio la
    // legge come "ecco l'andamento" anche quando sotto ci sono otto punti
    // messi a caso. Togliere il numero e lasciare la retta sarebbe stato
    // sistemare la finestra e lasciare aperta la porta.
    const { a, b } = linearRegression(xs, ys)
    const xMin = Math.min(...xs)
    const xMax = Math.max(...xs)
    const regLine = compatibileConZero(corr) ? [] : [
      { x: parseFloat(xMin.toFixed(3)), y: parseFloat((a + b * xMin).toFixed(3)) },
      { x: parseFloat(xMax.toFixed(3)), y: parseFloat((a + b * xMax).toFixed(3)) },
    ]

    // Stats
    const posReturns = ys.filter(y => y > 0).length
    const avgPos     = ys.filter(y => y > 0).reduce((s, v) => s + v, 0) / (posReturns || 1)
    const avgNeg     = ys.filter(y => y < 0).reduce((s, v) => s + v, 0) / (ys.filter(y => y < 0).length || 1)

    // Giorni con sentiment bullish → rendimento medio D+1, con la banda.
    //
    // Erano due medie nude, dietro il piano a pagamento, colorate di verde o
    // rosso: si leggevano come una regola operativa. Misurate su sei ticker,
    // sette medie calcolabili su sette comprendevano lo zero e due erano la
    // variazione di un giorno solo spacciata per media. Il ragionamento
    // completo, con i numeri, sta in utils/incertezza.js.
    const avgRetBull = mediaConBanda(pairs.filter(p => p.x > 0.1).map(p => p.y))
    const avgRetBear = mediaConBanda(pairs.filter(p => p.x < -0.1).map(p => p.y))

    return { pairs, corr, regLine, stats: { posReturns, avgPos, avgNeg, avgRetBull, avgRetBear, n: pairs.length } }
  }, [prices, sentiment])

  // Il colore adesso dice "distinguibile da zero", non "numero grande". Un
  // -0.712 su cinque giorni prendeva il rosso e l'etichetta "Forte negativa":
  // erano tutte e due false, e la seconda era peggio della prima.
  const corrColor = c => compatibileConZero(c) ? '#94a3b8'
    : c.r > 0 ? '#4ade80' : '#f87171'

  // Stessa regola per le due medie di rendimento. Il verde su un +0.45%
  // calcolato su dodici giorni diceva "questo funziona", e non era vero.
  const valoreMedia = m => m?.media == null
    ? '—'
    : `${m.media > 0 ? '+' : ''}${m.media.toFixed(2)}%`

  const coloreMedia = m => compatibileConZero(m) ? '#94a3b8'
    : m.media > 0 ? '#4ade80' : '#f87171'

  const spiegaMedia = (m, gruppo) => {
    if (m?.media == null) {
      return `servono ${MIN_GIORNI_MEDIA} giorni ${gruppo}, ce ne sono ${m?.n ?? 0}`
    }
    const seg = v => `${v > 0 ? '+' : ''}${v.toFixed(2)}%`
    return compatibileConZero(m)
      ? `${seg(m.lo)} / ${seg(m.hi)}: comprende lo zero`
      : `${seg(m.lo)} / ${seg(m.hi)} su ${m.n} giorni`
  }

  // Sotto le cinque coppie non c'è nemmeno una nuvola di punti da guardare.
  // Il messaggio dice il numero che serve per il NUMERO, non per il disegno,
  // perché è quello che la gente sta aspettando.
  if (pairs.length < 5) return (
    <div style={panelStyle}>
      <Header />
      <div style={{ textAlign: 'center', padding: '30px 0', color: 'var(--muted)', fontSize: 13 }}>
        Ancora {pairs.length} giorni con notizie e prezzo.
        <br />
        La nuvola dei punti compare da 5 giorni, il coefficiente da {MIN_COPPIE}.
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
            {corr?.r != null ? (corr.r > 0 ? '+' : '') + corr.r : '—'}
          </div>
          <div style={{ fontSize: 11, color: corrColor(corr), marginTop: 4 }}>
            {etichetta(corr)}
          </div>
          <div style={{ fontSize: 10, color: '#64748b', marginTop: 3 }}>
            {spiegazione(corr)}
          </div>
        </div>

        <div style={{ fontSize: 12, color: 'var(--muted)', lineHeight: 1.7, flex: 1, minWidth: 200 }}>
          Ogni punto mostra il <b style={{ color: 'var(--off-white)' }}>sentiment del giorno D</b> e il{' '}
          <b style={{ color: 'var(--off-white)' }}>rendimento del prezzo il giorno dopo (D+1)</b>.
          {corr?.r == null ? (
            <> Il numero compare da {MIN_COPPIE} giorni in su: sotto, la banda di
            incertezza è più larga di qualsiasi relazione che avrebbe senso
            rivendicare, e quello che si legge è rumore.</>
          ) : compatibileConZero(corr) ? (
            <> La banda va da {corr.lo} a {corr.hi} e comprende lo zero: su questi
            dati <b style={{ color: 'var(--off-white)' }}>non si può dire che una
            relazione ci sia</b>.</>
          ) : (
            <> La banda va da {corr.lo} a {corr.hi} e non comprende lo zero. Resta
            una relazione statistica su {corr.n} giorni, che non vuol dire che il
            sentiment causi il movimento.</>
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
            value={valoreMedia(stats.avgRetBull)}
            valueColor={coloreMedia(stats.avgRetBull)}
            sub={isPro ? spiegaMedia(stats.avgRetBull, 'bullish') : 'dopo i giorni bullish'}
            locked={!isPro}
          />
          <StatBlock
            label="Rendimento medio (Bearish)"
            value={valoreMedia(stats.avgRetBear)}
            valueColor={coloreMedia(stats.avgRetBear)}
            sub={isPro ? spiegaMedia(stats.avgRetBear, 'bearish') : 'dopo i giorni bearish'}
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
