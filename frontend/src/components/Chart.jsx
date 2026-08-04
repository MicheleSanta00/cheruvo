import { useState, useMemo, useEffect, useRef } from 'react'
import {
  ComposedChart, Area, Bar, Line,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, ReferenceArea, Cell,
} from 'recharts'
import Icon from './Icon.jsx'
import { formattaPrezzo } from './LogoCrypto.jsx'

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
    : sentVal > 0.1 ? '#4ade80' : sentVal < -0.1 ? '#f87171' : 'var(--giallo)'
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
      background: 'var(--near-black)', border: '1px solid rgba(var(--rgb-contrasto), 0.1)',
      borderRadius: 10, padding: compact ? '8px 10px' : '12px 16px', fontSize: compact ? 11 : 12,
      minWidth: compact ? 148 : 190, maxWidth: compact ? 185 : undefined,
      boxShadow: 'var(--ombra)',
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
        <div style={{ borderTop: '1px solid rgba(var(--rgb-contrasto), 0.07)', paddingTop: 8 }}>
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
    : v > 0.1 ? '#4ade80' : v < -0.1 ? '#f87171' : 'var(--giallo)'
  const sentLabel = v => v == null ? '—'
    : v > 0.1 ? 'Bullish' : v < -0.1 ? 'Bearish' : 'Neutro'

  const corrColor = c => c == null ? '#94a3b8'
    : c > 0.3 ? '#4ade80' : c < -0.3 ? '#f87171' : 'var(--giallo)'
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
            <Block label="Giorni neutri" value={`${neutralDays} gg`} valueColor='var(--giallo)'
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

// La targhetta del prezzo attuale, incollata al bordo destro dell'asse.
// Recharts non ha niente di simile: si disegna a mano dentro l'SVG usando le
// coordinate che passa alla label della ReferenceLine.
function EtichettaPrezzo({ viewBox, valore, colore }) {
  if (!viewBox) return null
  const { y, width, x } = viewBox
  const testo = formattaPrezzo(valore)
  const larghezza = Math.max(46, testo.length * 7.2 + 12)
  return (
    <g>
      <rect x={x + width - larghezza + 2} y={y - 9} width={larghezza} height={18}
            rx={3} fill={colore} />
      <text x={x + width - larghezza / 2 + 2} y={y + 4} textAnchor="middle"
            fontSize={11} fontWeight={700} fill="#06070a"
            fontFamily="var(--mono)">{testo}</text>
    </g>
  )
}

// Sull'intraday la data arriva come "2026-08-04 15:42": sull'asse serve
// soltanto l'ora, altrimenti le etichette si accavallano.
const fmtOra = d => {
  if (!d) return ''
  const p = String(d).split(' ')
  return p.length > 1 ? p[1] : d
}

function TooltipOggi({ active, payload, label, chiusuraIeri, tipoRiferimento }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  const rispettoIeri = chiusuraIeri != null ? d.Close - chiusuraIeri : null
  // Sulle crypto il confronto è su 24 ore vere, sulle azioni sulla chiusura
  // precedente: sono due cose diverse e l'etichetta deve dirlo.
  const etichettaRif = tipoRiferimento === '24h' ? 'in 24h' : 'da ieri'
  return (
    <div style={{
      background: 'var(--near-black)', border: '1px solid var(--border-br)',
      borderRadius: 6, padding: '8px 11px', fontSize: 12,
    }}>
      <div style={{ fontFamily: 'var(--mono)', color: 'var(--muted)', fontSize: 10.5, marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontFamily: 'var(--mono)', fontWeight: 700, fontSize: 15, color: 'var(--white)' }}>
        {formattaPrezzo(d.Close)}
      </div>
      {rispettoIeri != null && (
        <div style={{ fontFamily: 'var(--mono)', fontSize: 11, marginTop: 2,
                      color: rispettoIeri >= 0 ? 'var(--green)' : 'var(--red)' }}>
          {rispettoIeri >= 0 ? '+' : ''}{formattaPrezzo(rispettoIeri)} {etichettaRif}
        </div>
      )}
      {d.Volume > 0 && (
        <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 3 }}>
          volume {Number(d.Volume).toLocaleString('it-IT')}
        </div>
      )}
    </div>
  )
}

// Interruttori del grafico: squadrati e in maiuscoletto come il resto della
// plancia. Erano pillole arrotondate, l'unica cosa tonda in tutta la pagina.
const stileInterruttore = {
  fontSize: 10, letterSpacing: '.1em', textTransform: 'uppercase', fontWeight: 700,
  padding: '4px 10px', borderRadius: 3, border: '1px solid var(--border-br)',
  fontFamily: 'var(--sans)',
}

// ── Vista "Oggi" ──────────────────────────────────────────────────────────
// Il grafico della seduta in corso, che si allunga da solo mentre la borsa è
// aperta. Il colore della linea segue la giornata: verde se il titolo sta
// sopra la chiusura di ieri, rosso se sotto. È la convenzione di ogni
// terminale finanziario e si legge senza dover pensare.
/**
 * Raggruppa i minuti in candele più larghe.
 *
 * Una seduta americana sono 390 punti: disegnati come candele su un grafico
 * largo mille pixel verrebbero spessi due pixel e mezzo, cioè illeggibili.
 * Raggruppandoli in blocchi si ottengono candele vere, con corpo e ombre.
 * L'apertura è quella del primo minuto del blocco, la chiusura quella
 * dell'ultimo, massimo e minimo gli estremi, il volume la somma: è
 * esattamente come si costruisce una candela da timeframe più alto.
 */
function raggruppaInCandele(prices, quante = 80) {
  if (!prices.length) return []
  const passo = Math.max(1, Math.ceil(prices.length / quante))
  if (passo === 1) return prices

  const fuori = []
  for (let i = 0; i < prices.length; i += passo) {
    const blocco = prices.slice(i, i + passo).filter(p => p.Close != null)
    if (!blocco.length) continue
    const alti  = blocco.map(p => p.High  ?? p.Close)
    const bassi = blocco.map(p => p.Low   ?? p.Close)
    fuori.push({
      date:   blocco[0].date,
      Open:   blocco[0].Open ?? blocco[0].Close,
      Close:  blocco[blocco.length - 1].Close,
      High:   Math.max(...alti),
      Low:    Math.min(...bassi),
      Volume: blocco.reduce((s, p) => s + (p.Volume || 0), 0),
      // Quanti minuti stanno dentro questa candela: serve al tooltip, perché
      // "candela delle 15:42" senza sapere che dura 5 minuti confonde.
      minuti: blocco.length,
    })
  }
  return fuori
}

function GraficoOggi({ prices, ticker, statoBorsa, isMobile }) {
  const [espanso, setEspanso] = useState(false)
  const [candele, setCandele] = useState(false)
  // Lampeggia quando arriva un punto nuovo: è il modo per vedere che il
  // grafico è vivo. Senza, un aggiornamento che aggiunge un pixel sul bordo
  // destro è indistinguibile da un'immagine ferma.
  const [appenaAggiornato, setAppenaAggiornato] = useState(false)
  const quantiPrima = useRef(prices.length)

  useEffect(() => {
    if (prices.length > quantiPrima.current) {
      setAppenaAggiornato(true)
      const t = setTimeout(() => setAppenaAggiornato(false), 1400)
      quantiPrima.current = prices.length
      return () => clearTimeout(t)
    }
    quantiPrima.current = prices.length
  }, [prices.length])

  // Esc chiude la vista ingrandita: è il gesto che tutti si aspettano.
  useEffect(() => {
    if (!espanso) return
    const tasto = (e) => { if (e.key === 'Escape') setEspanso(false) }
    window.addEventListener('keydown', tasto)
    return () => window.removeEventListener('keydown', tasto)
  }, [espanso])

  const corpo = (
    <GraficoOggiCorpo prices={prices} ticker={ticker} statoBorsa={statoBorsa}
      isMobile={isMobile} espanso={espanso} appenaAggiornato={appenaAggiornato}
      candele={candele} onCandele={setCandele}
      onEspandi={() => setEspanso(true)} onChiudi={() => setEspanso(false)} />
  )

  if (!espanso) return corpo

  return (
    <>
      {/* Il grafico normale resta al suo posto sotto, così chiudendo non
          "salta" niente: la pagina è rimasta identica. */}
      <div style={{ opacity: 0.25, pointerEvents: 'none' }}>{corpo}</div>
      <div
        onClick={(e) => { if (e.target === e.currentTarget) setEspanso(false) }}
        style={{
          position: 'fixed', inset: 0, zIndex: 200,
          background: 'var(--black)', display: 'flex',
          alignItems: 'center', justifyContent: 'center', padding: isMobile ? 10 : 28,
        }}>
        <div style={{
          width: '100%', maxWidth: 1500, maxHeight: '100%', overflowY: 'auto',
          border: '1px solid var(--border-br)', borderRadius: 10,
          background: 'var(--near-black)', padding: isMobile ? 14 : 22,
        }}>
          {corpo}
        </div>
      </div>
    </>
  )
}

function GraficoOggiCorpo({ prices, ticker, statoBorsa, isMobile, espanso,
                            appenaAggiornato, candele, onCandele,
                            onEspandi, onChiudi }) {
  if (!prices.length) return (
    <div style={{ height: 220, display: 'flex', alignItems: 'center',
                  justifyContent: 'center', color: 'var(--muted)', fontSize: 13 }}>
      Nessuno scambio disponibile per la seduta di oggi.
    </div>
  )

  const chiusuraIeri = statoBorsa?.chiusura_precedente ?? null
  const ultimo = prices[prices.length - 1]?.Close ?? null
  const suGiornata = chiusuraIeri != null && ultimo != null ? ultimo >= chiusuraIeri : true
  const colore = suGiornata ? 'var(--green)' : 'var(--red)'
  const coloreHex = suGiornata ? '#34d399' : '#f87171'

  // ── Zoom: si trascina sul grafico per scegliere l'intervallo ────────────
  // Il taglio avviene sui dati mostrati, non sull'asse: così l'asse dei prezzi
  // si ricalcola sulla porzione scelta e un movimento di pochi centesimi
  // dentro una giornata piatta diventa finalmente leggibile. Zoomando senza
  // ricalcolare la scala si otterrebbe la stessa riga dritta, più larga.
  const [da, setDa] = useState(null)
  const [a, setA] = useState(null)
  const [trascinando, setTrascinando] = useState(null)

  const visibili = (da != null && a != null)
    ? prices.slice(Math.min(da, a), Math.max(da, a) + 1)
    : prices
  const zoomAttivo = visibili.length !== prices.length

  const chiusure = visibili.map(p => p.Close).filter(v => v != null)
  // La chiusura di ieri entra nella scala solo quando si vede tutta la
  // giornata: dentro uno zoom stretto schiaccerebbe tutto il resto.
  const riferimenti = (!zoomAttivo && chiusuraIeri != null) ? [...chiusure, chiusuraIeri] : chiusure
  const min = Math.min(...riferimenti)
  const max = Math.max(...riferimenti)
  const margine = (max - min) * 0.12 || 1

  // Massimo e minimo della porzione visibile: sono i due livelli che si
  // guardano per primi su qualsiasi grafico.
  const massimoVis = Math.max(...visibili.map(p => p.High ?? p.Close).filter(v => v != null))
  const minimoVis  = Math.min(...visibili.map(p => p.Low  ?? p.Close).filter(v => v != null))

  // Media mobile sui punti visibili: smussa il rumore del minuto per minuto.
  const [mostraMedia, setMostraMedia] = useState(false)
  const periodoMedia = Math.max(5, Math.round(visibili.length / 12))
  const conMedia = mostraMedia
    ? (() => {
        const m = movingAverage(visibili, 'Close', periodoMedia)
        return visibili.map((d, i) => ({ ...d, media: m[i] }))
      })()
    : visibili

  const dati = candele ? raggruppaInCandele(conMedia, isMobile ? 45 : 90) : conMedia
  const CandelaOggi = useMemo(() => makeCandleShape(min - margine, max + margine),
                              [min, max, margine])

  const iniziaTrascino = (e) => {
    if (!e?.activeTooltipIndex && e?.activeTooltipIndex !== 0) return
    setTrascinando({ inizio: e.activeTooltipIndex, fine: e.activeTooltipIndex })
  }
  const muoviTrascino = (e) => {
    if (!trascinando) return
    if (e?.activeTooltipIndex == null) return
    setTrascinando((t) => ({ ...t, fine: e.activeTooltipIndex }))
  }
  const finisciTrascino = () => {
    if (!trascinando) return
    const { inizio, fine } = trascinando
    setTrascinando(null)
    // Trascinamenti brevissimi sono click andati storti, non richieste di zoom
    if (Math.abs(fine - inizio) < 3) return
    const base = (da != null) ? Math.min(da, a) : 0
    setDa(base + Math.min(inizio, fine))
    setA(base + Math.max(inizio, fine))
  }
  const azzeraZoom = () => { setDa(null); setA(null); setTrascinando(null) }

  const variazione = chiusuraIeri != null && ultimo != null ? ultimo - chiusuraIeri : null
  const variazionePct = variazione != null && chiusuraIeri ? (variazione / chiusuraIeri) * 100 : null

  const oraScambio = statoBorsa?.ultimo_scambio
    ? new Date(statoBorsa.ultimo_scambio * 1000).toLocaleTimeString('it-IT',
        { hour: '2-digit', minute: '2-digit' })
    : null
  const aperto = statoBorsa?.aperto

  return (
    <div>
      {/* Riga di intestazione: prezzo grande, variazione sulla giornata, e
          SEMPRE l'ora dell'ultimo scambio. Quest'ultima non è un dettaglio:
          i dati di Yahoo su diverse borse arrivano con una quindicina di
          minuti di ritardo, e scrivere l'ora è l'unico modo onesto di non
          far credere che sia il secondo esatto in cui stai guardando. */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 14,
                    flexWrap: 'wrap', marginBottom: 14 }}>
        <span style={{ fontFamily: 'var(--mono)', fontSize: 26, fontWeight: 700,
                       fontVariantNumeric: 'tabular-nums', color: 'var(--white)' }}>
          {formattaPrezzo(ultimo)}
        </span>
        {variazione != null && (
          <span style={{ fontFamily: 'var(--mono)', fontSize: 14, fontWeight: 700, color: colore }}>
            {variazione >= 0 ? '+' : ''}{formattaPrezzo(variazione)}
            {' '}({variazione >= 0 ? '+' : ''}{variazionePct.toFixed(2)}%)
          </span>
        )}
        <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center',
                       gap: 7, fontSize: 11, color: 'var(--muted)' }}>
          <span style={{
            width: appenaAggiornato ? 9 : 6, height: appenaAggiornato ? 9 : 6,
            borderRadius: '50%',
            background: aperto ? 'var(--green)' : 'var(--muted)',
            boxShadow: aperto ? (appenaAggiornato ? '0 0 14px var(--green)' : '0 0 7px var(--green)') : 'none',
            transition: 'all .3s ease',
          }} />
          {statoBorsa?.sempre_aperto ? 'Scambi 24/7'
            : aperto ? 'Borsa aperta' : 'Borsa chiusa'}
          {oraScambio && <span style={{ fontFamily: 'var(--mono)' }}>· ultimo scambio {oraScambio}</span>}
        </span>
      </div>

      <div style={{ marginBottom: 6, display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ fontSize: 10, color: 'var(--muted)', letterSpacing: '0.12em',
                       textTransform: 'uppercase', fontWeight: 700 }}>
          Seduta di oggi — {ticker} · {zoomAttivo ? `${visibili.length} di ${prices.length}` : prices.length} minuti
        </span>
        {appenaAggiornato && (
          <span style={{ fontSize: 9.5, color: 'var(--green)', fontWeight: 700,
                         letterSpacing: '.1em', textTransform: 'uppercase' }}>
            + nuovo dato
          </span>
        )}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
          {zoomAttivo && (
            <button onClick={azzeraZoom} title="Torna a tutta la seduta" style={{
              fontSize: 9.5, letterSpacing: '.1em', textTransform: 'uppercase',
              fontWeight: 700, padding: '4px 9px', borderRadius: 3,
              border: '1px solid rgba(96,165,250,0.45)', background: 'rgba(96,165,250,0.14)',
              color: 'var(--azure)', cursor: 'pointer',
            }}>← tutto</button>
          )}
          <button onClick={() => setMostraMedia(v => !v)} title="Media mobile" style={{
            fontSize: 9.5, letterSpacing: '.1em', textTransform: 'uppercase',
            fontWeight: 700, padding: '4px 9px', borderRadius: 3,
            border: '1px solid ' + (mostraMedia ? 'rgba(250,204,21,0.4)' : 'var(--border-br)'),
            background: mostraMedia ? 'rgba(250,204,21,0.12)' : 'transparent',
            color: mostraMedia ? 'var(--giallo)' : 'var(--muted)', cursor: 'pointer',
          }}>media</button>
          {[['linea', false], ['candele', true]].map(([etichetta, v]) => (
            <button key={etichetta} onClick={() => onCandele(v)} style={{
              fontSize: 9.5, letterSpacing: '.1em', textTransform: 'uppercase',
              fontWeight: 700, padding: '4px 9px', borderRadius: 3,
              border: '1px solid ' + (candele === v ? 'rgba(96,165,250,0.45)' : 'var(--border-br)'),
              background: candele === v ? 'rgba(96,165,250,0.14)' : 'transparent',
              color: candele === v ? 'var(--azure)' : 'var(--muted)', cursor: 'pointer',
            }}>{etichetta}</button>
          ))}
        </div>
        <button
          onClick={espanso ? onChiudi : onEspandi}
          title={espanso ? 'Riduci (Esc)' : 'Ingrandisci il grafico'}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            fontSize: 10, letterSpacing: '.1em', textTransform: 'uppercase',
            fontWeight: 700, padding: '4px 9px', borderRadius: 3,
            border: '1px solid var(--border-br)', background: 'transparent',
            color: espanso ? 'var(--azure)' : 'var(--muted)', cursor: 'pointer',
          }}>
          <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor"
               strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
            {espanso
              ? <><path d="M6.5 1.5v5h-5"/><path d="M9.5 14.5v-5h5"/></>
              : <><path d="M1.5 5.5v-4h4"/><path d="M14.5 10.5v4h-4"/></>}
          </svg>
          {espanso ? 'Riduci' : 'Ingrandisci'}
        </button>
      </div>

      <div style={{ position: 'relative', userSelect: 'none' }}>
        <ResponsiveContainer width="100%" height={espanso ? (isMobile ? 380 : 560) : (isMobile ? 250 : 300)}>
          <ComposedChart data={dati} margin={{ top: 4, right: isMobile ? 4 : 16, left: 0, bottom: 0 }}
            onMouseDown={iniziaTrascino} onMouseMove={muoviTrascino}
            onMouseUp={finisciTrascino} onMouseLeave={() => setTrascinando(null)}>
            <defs>
              <linearGradient id="oggiGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"   stopColor={coloreHex} stopOpacity={0.22}/>
                <stop offset="100%" stopColor={coloreHex} stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 4" stroke="rgba(var(--rgb-contrasto), 0.04)" vertical={false}/>
            <XAxis dataKey="date" tickFormatter={fmtOra} interval="preserveStartEnd"
              minTickGap={isMobile ? 50 : 80}
              tick={{ fontSize: 10, fill: '#475569' }} axisLine={false} tickLine={false}/>
            <YAxis orientation="right" domain={[min - margine, max + margine]}
              tickFormatter={v => formattaPrezzo(v)}
              tick={{ fontSize: 10, fill: '#475569' }} axisLine={false} tickLine={false}
              width={isMobile ? 56 : 66}/>
            {/* Mirino verticale: segue il cursore e dice a che minuto sei */}
            <Tooltip cursor={{ stroke: 'rgba(var(--rgb-contrasto), 0.28)', strokeWidth: 1, strokeDasharray: '3 3' }}
              content={<TooltipOggi chiusuraIeri={chiusuraIeri}
                       tipoRiferimento={statoBorsa?.tipo_riferimento} />}/>

            {/* La chiusura di ieri come riga di riferimento: senza, "sta salendo"
                non ha un metro. È la linea che separa il verde dal rosso. */}
            {chiusuraIeri != null && !zoomAttivo && (
              <ReferenceLine y={chiusuraIeri} stroke="rgba(var(--rgb-contrasto), 0.22)" strokeDasharray="4 4"
                label={{ value: statoBorsa?.tipo_riferimento === '24h' ? '24 ore fa' : 'chiusura ieri',
                         position: 'insideTopLeft',
                         fill: '#475569', fontSize: 9.5 }}/>
            )}

            {/* Massimo e minimo della porzione a schermo */}
            <ReferenceLine y={massimoVis} stroke="rgba(52,211,153,0.28)" strokeDasharray="2 4"
              label={{ value: `max ${formattaPrezzo(massimoVis)}`, position: 'insideTopRight',
                       fill: '#34d399', fontSize: 9.5 }}/>
            <ReferenceLine y={minimoVis} stroke="rgba(248,113,113,0.28)" strokeDasharray="2 4"
              label={{ value: `min ${formattaPrezzo(minimoVis)}`, position: 'insideBottomRight',
                       fill: '#f87171', fontSize: 9.5 }}/>

            {/* IL PREZZO ORA, sempre a schermo sul bordo destro.
                È la cosa che chiedevi: prima per leggere l'ultimo valore
                bisognava inseguire col cursore l'ultimo punto del grafico. */}
            {ultimo != null && (
              <ReferenceLine y={ultimo} stroke={coloreHex} strokeWidth={1} strokeDasharray="1 3"
                label={<EtichettaPrezzo valore={ultimo} colore={coloreHex} />}/>
            )}

            {candele ? (
              <Bar dataKey="Close" shape={CandelaOggi} isAnimationActive={false} />
            ) : (
              <Area type="monotone" dataKey="Close" stroke={coloreHex}
                strokeWidth={1.6} fill="url(#oggiGrad)" dot={false} isAnimationActive={false}
                activeDot={{ r: 3.5, strokeWidth: 0, fill: coloreHex }}/>
            )}

            {mostraMedia && (
              <Line type="monotone" dataKey="media" stroke="var(--giallo)" strokeWidth={1.4}
                dot={false} isAnimationActive={false} connectNulls />
            )}

            {/* La fascia che si disegna mentre trascini per scegliere lo zoom */}
            {trascinando && Math.abs(trascinando.fine - trascinando.inizio) >= 1 && (
              <ReferenceArea
                x1={dati[Math.min(trascinando.inizio, trascinando.fine)]?.date}
                x2={dati[Math.max(trascinando.inizio, trascinando.fine)]?.date}
                fill="var(--azure)" fillOpacity={0.12}
                stroke="var(--azure)" strokeOpacity={0.4} />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 8 }}>
        {zoomAttivo
          ? `Ingrandito su ${visibili.length} minuti. Premi "tutto" per tornare alla seduta intera.`
          : 'Trascina sul grafico per ingrandire un intervallo.'}
      </div>

      {!aperto && !statoBorsa?.sempre_aperto && (
        <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 10, lineHeight: 1.5 }}>
          La borsa è chiusa: questo è il disegno completo dell'ultima seduta.
          Tornerà a muoversi da solo alla prossima apertura.
        </div>
      )}
    </div>
  )
}

// ── Componente principale ─────────────────────────────────────────────────
export default function Chart({ prices, sentiment, ticker, stats, intraday = false, statoBorsa = null }) {
  const [showCandles, setShowCandles] = useState(false)
  const [showMA, setShowMA]           = useState(true)
  const isMobile = useIsMobile()

  // Vista "Oggi": un punto al minuto invece che al giorno.
  //
  // È un grafico DIVERSO, non lo stesso con più punti, e il motivo è che il
  // sentiment qui non esiste: lo calcoliamo per giornata, quindi su una
  // singola seduta è un numero solo e non c'è nessuna curva da sovrapporre.
  // Sovrapporre una riga piatta sarebbe peggio che non metterla.
  if (intraday) {
    return <GraficoOggi prices={prices} ticker={ticker}
                        statoBorsa={statoBorsa} isMobile={isMobile} />
  }

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
          color: showMA ? 'var(--giallo)' : 'var(--muted)',
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
          <CartesianGrid strokeDasharray="3 4" stroke="rgba(var(--rgb-contrasto), 0.04)" vertical={false}/>
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
          <span style={{ fontSize: 10, color: 'var(--giallo)', display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 16, height: 2, background: 'var(--giallo)', display: 'inline-block', borderRadius: 1 }}/>
            Media mobile 7 giorni
          </span>
        )}
      </div>

      <ResponsiveContainer width="100%" height={isMobile ? 150 : 120}>
        <ComposedChart data={display} margin={chartMargin}>
          <CartesianGrid strokeDasharray="3 4" stroke="rgba(var(--rgb-contrasto), 0.04)" vertical={false}/>
          {/* preserveStartEnd: l'ultimo giorno viene SEMPRE etichettato.
              Con il solo interval numerico l'asse si fermava a un tick prima
              della fine (es. "30/07" mentre il dato arrivava al 31/07) e
              sembrava che i prezzi fossero fermi da un giorno. */}
          <XAxis dataKey="date" tickFormatter={fmtDate} interval="preserveStartEnd" minTickGap={isMobile ? 44 : 60}
            tick={{ fontSize: 10, fill: '#475569' }} axisLine={false} tickLine={false}/>
          <YAxis yAxisId="sent" orientation="right" domain={[-1, 1]}
            ticks={[-1, -0.5, 0, 0.5, 1]} tickFormatter={v => v.toFixed(1)}
            tick={{ fontSize: 10, fill: '#475569' }} axisLine={false} tickLine={false} width={yW}/>
          <ReferenceLine yAxisId="sent" y={0} stroke="rgba(var(--rgb-contrasto), 0.12)" strokeDasharray="3 4"/>
          <ReferenceLine yAxisId="sent" y={0.1}  stroke="rgba(74,222,128,0.1)"  strokeDasharray="2 4"/>
          <ReferenceLine yAxisId="sent" y={-0.1} stroke="rgba(248,113,113,0.1)" strokeDasharray="2 4"/>
          <Tooltip content={<CustomTooltip compact={isMobile} />}/>

          <Bar yAxisId="sent" dataKey="sentiment" radius={[2,2,0,0]} maxBarSize={12} isAnimationActive={false}>
            {display.map((d, i) => (
              <Cell key={i} opacity={0.7}
                fill={d.sentiment == null ? '#334155'
                  : d.sentiment > 0.1 ? '#4ade80'
                  : d.sentiment < -0.1 ? '#f87171'
                  : 'var(--giallo)'}
              />
            ))}
          </Bar>

          {/* MA7 come linea sovrapposta */}
          {showMA && (
            <Line yAxisId="sent" dataKey="sentMA"
              stroke='var(--giallo)' strokeWidth={1.5}
              dot={false} strokeDasharray="0"
              activeDot={{ r: 3, fill: 'var(--giallo)', strokeWidth: 0 }}
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
