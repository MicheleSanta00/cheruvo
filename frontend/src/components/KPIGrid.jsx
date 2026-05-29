import { useLang } from '../LangContext.jsx'

export default function KPIGrid({ stats }) {
  const { t } = useLang()
  if (!stats) return null

  const items = [
    { label: t.kpi.total,   value: stats.total?.toLocaleString(), cls: 'blue' },
    { label: t.kpi.avg,     value: fmt(stats.avg),                cls: stats.avg >= 0 ? 'pos' : 'neg' },
    { label: t.kpi.max,     value: fmt(stats.max),                cls: 'pos' },
    { label: t.kpi.min,     value: fmt(stats.min),                cls: 'neg' },
    { label: t.kpi.sources, value: stats.sources,                 cls: '' },
  ]

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
      gap: 10,
    }}>
      {items.map((item) => (
        <div key={item.label} style={{
          background: 'rgba(255,255,255,0.03)',
          border: '1px solid var(--border)',
          borderRadius: 10,
          padding: '14px 16px',
        }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 6, letterSpacing: '0.02em' }}>
            {item.label}
          </div>
          <div className={item.cls} style={{ fontSize: 22, fontWeight: 500, letterSpacing: '-0.02em', lineHeight: 1 }}>
            {item.value ?? '—'}
          </div>
        </div>
      ))}
    </div>
  )
}

function fmt(v) {
  if (v == null || isNaN(v)) return '—'
  return (v > 0 ? '+' : '') + Number(v).toFixed(3)
}