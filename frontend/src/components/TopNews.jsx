export default function TopNews({ news, isPro, onUpgrade }) {
  const sorted   = [...news].sort((a, b) => b.sentiment - a.sentiment)
  const positive = sorted.slice(0, isPro ? 10 : 3)
  const negative = [...news].sort((a, b) => a.sentiment - b.sentiment).slice(0, isPro ? 5 : 2)

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 20, flexWrap: 'wrap', gap: 8 }}>
        <h3 style={{ fontFamily: 'var(--serif)', fontSize: 22, fontWeight: 400, letterSpacing: '-0.02em' }}>
          Top News
        </h3>
        {!isPro && (
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>
            Showing {positive.length + negative.length} of {news.length} —{' '}
            <span
              onClick={onUpgrade}
              style={{ color: 'var(--azure)', cursor: 'pointer', textDecoration: 'underline' }}
            >Pro to see all</span>
          </span>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 20 }}>
        <NewsColumn title="Bullish" items={positive} positive onUpgrade={onUpgrade} isPro={isPro} total={sorted.length} />
        <NewsColumn title="Bearish" items={negative} positive={false} onUpgrade={onUpgrade} isPro={isPro} total={news.length} />
      </div>
    </div>
  )
}

function NewsColumn({ title, items, positive, onUpgrade, isPro, total }) {
  const color = positive ? 'var(--green)' : 'var(--red)'
  const hiddenCount = total - items.length

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
              display: 'block', padding: '12px 14px',
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

        {!isPro && hiddenCount > 0 && (
          <button
            onClick={onUpgrade}
            style={{
              padding: '12px 14px', borderRadius: '0 8px 8px 0',
              background: 'rgba(30,92,255,0.04)',
              border: '1px solid rgba(30,92,255,0.15)',
              borderLeft: `3px solid rgba(30,92,255,0.3)`,
              cursor: 'pointer', textAlign: 'left',
            }}
          >
            <div style={{ fontSize: 13, color: 'var(--muted)' }}>
              🔒 +{hiddenCount} hidden articles
            </div>
            <div style={{ fontSize: 12, color: 'var(--azure)', marginTop: 4 }}>
              Upgrade to Pro to unlock →
            </div>
          </button>
        )}
      </div>
    </div>
  )
}
