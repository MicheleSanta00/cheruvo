import { useLang } from '../LangContext.jsx'

/**
 * Striscia metriche del titolo.
 *
 * Non più card arrotondate che galleggiano nel vuoto: un unico blocco a
 * divisori da un pixel, come la fascia di un terminale finanziario. I picchi
 * di sentiment non sono più qui perché vivono nel pannello del grafico, dove
 * hanno il contesto del periodo: prima gli stessi numeri comparivano due volte.
 */
export default function KPIGrid({ stats }) {
  const { t } = useLang()
  if (!stats) return null

  const items = [
    { label: t.kpi.total,   value: stats.total?.toLocaleString(), color: 'var(--white)' },
    { label: t.kpi.avg,     value: fmt(stats.avg),                color: segno(stats.avg) },
    { label: t.kpi.max,     value: fmt(stats.max),                color: 'var(--green)' },
    { label: t.kpi.min,     value: fmt(stats.min),                color: 'var(--red)' },
    { label: t.kpi.sources, value: stats.sources,                 color: 'var(--white)' },
  ]

  return (
    <div style={{
      display: 'flex', flexWrap: 'wrap',
      borderBottom: '1px solid var(--border)',
      background: 'rgba(255,255,255,0.015)',
    }}>
      {items.map((item, i) => (
        <div key={item.label} style={{
          flex: '1 1 120px', minWidth: 120, padding: '9px 15px',
          borderRight: i < items.length - 1 ? '1px solid var(--border)' : 'none',
        }}>
          <div style={{
            fontSize: 10, color: 'var(--muted)', fontWeight: 700,
            letterSpacing: '0.11em', textTransform: 'uppercase',
          }}>
            {item.label}
          </div>
          <div style={{
            fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums',
            fontSize: 17, fontWeight: 700, lineHeight: 1.25, marginTop: 3,
            color: item.color,
          }}>
            {item.value ?? '—'}
          </div>
        </div>
      ))}
    </div>
  )
}

function fmt(v) {
  if (v == null || isNaN(v)) return '—'
  return (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(Number(v)).toFixed(3)
}

function segno(v) {
  if (v == null || isNaN(v)) return 'var(--muted)'
  return v > 0.08 ? 'var(--green)' : v < -0.08 ? 'var(--red)' : 'var(--muted)'
}
