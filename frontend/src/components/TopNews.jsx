export default function TopNews({ news }) {
  if (!news.length) return null

  const sorted = [...news].sort((a, b) => b.sentiment - a.sentiment)
  const positive = sorted.slice(0, 8)
  const negative = [...news].sort((a, b) => a.sentiment - b.sentiment).slice(0, 5)

  return (
    <div>
      <h3 style={{ fontFamily: 'var(--serif)', fontSize: 22, fontWeight: 400, letterSpacing: '-0.02em', marginBottom: 20 }}>
        Top News
      </h3>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        <NewsColumn title="Ottimismo" items={positive} positive />
        <NewsColumn title="Pessimismo" items={negative} positive={false} />
      </div>
    </div>
  )
}

function NewsColumn({ title, items, positive }) {
  const color = positive ? 'var(--green)' : 'var(--red)'
  const borderColor = positive ? 'rgba(52,211,153,0.2)' : 'rgba(248,113,113,0.2)'

  return (
    <div>
      <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--muted)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 12 }}>
        {title}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {items.map((item, i) => (
          <a
            key={i}
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: 'block',
              padding: '12px 14px',
              background: 'rgba(255,255,255,0.02)',
              border: '1px solid var(--border)',
              borderLeft: `3px solid ${color}`,
              borderRadius: '0 8px 8px 0',
              transition: 'background .15s',
            }}
            onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.05)'}
            onMouseLeave={e => e.currentTarget.style.background = 'rgba(255,255,255,0.02)'}
          >
            <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
              <span style={{ fontSize: 12, fontWeight: 600, color, flexShrink: 0, marginTop: 2 }}>
                {(item.sentiment >= 0 ? '+' : '') + Number(item.sentiment).toFixed(3)}
              </span>
              <span style={{ fontSize: 13, lineHeight: 1.5, color: 'var(--off-white)' }}>
                {item.title?.length > 80 ? item.title.slice(0, 80) + '…' : item.title}
              </span>
            </div>
            <div style={{ marginTop: 6, fontSize: 11, color: 'var(--muted)', paddingLeft: 46 }}>
              {item.source} · {item.published_date}
            </div>
          </a>
        ))}
      </div>
    </div>
  )
}
