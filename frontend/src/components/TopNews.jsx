import { useState } from 'react'
import { useLang } from '../LangContext.jsx'
import Icon from './Icon.jsx'

const PAGE_SIZE = 10

export default function TopNews({ news, isPro, onUpgrade }) {
  const { t } = useLang()
  const [tab, setTab]   = useState('top')      // 'top' | 'recent'
  const [shown, setShown] = useState(PAGE_SIZE) // per tab recenti

  const sorted   = [...news].sort((a, b) => b.sentiment - a.sentiment)
  const positive = sorted.filter(n => n.sentiment > 0).slice(0, isPro ? 15 : 3)
  const negative = [...news].sort((a, b) => a.sentiment - b.sentiment).filter(n => n.sentiment < 0).slice(0, isPro ? 10 : 2)
  const recent   = [...news].sort((a, b) => new Date(b.published_date) - new Date(a.published_date))

  const tabs = [
    { id: 'top',    icon: 'compare', label: 'Top Bullish / Bearish' },
    { id: 'recent', icon: 'recent',  label: 'Recenti' },
  ]

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
        <h3 style={{ fontFamily: 'var(--serif)', fontSize: 22, fontWeight: 400, letterSpacing: '-0.02em' }}>
          {t.topNews.title}
        </h3>
        {!isPro && (
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>
            {positive.length + negative.length} / {news.length} —{' '}
            <span onClick={onUpgrade} style={{ color: 'var(--azure)', cursor: 'pointer', textDecoration: 'underline' }}>
              {t.topNews.upgradeBtn}
            </span>
          </span>
        )}
        {isPro && (
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>{news.length} news</span>
        )}
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
        {tabs.map(tb => (
          <button
            key={tb.id}
            onClick={() => { setTab(tb.id); setShown(PAGE_SIZE) }}
            style={{
              padding: '6px 14px', borderRadius: 8, fontSize: 12, fontWeight: 500,
              border: '1px solid',
              borderColor: tab === tb.id ? 'rgba(30,92,255,0.5)' : 'var(--border-br)',
              background: tab === tb.id ? 'rgba(30,92,255,0.12)' : 'transparent',
              color: tab === tb.id ? 'var(--azure)' : 'var(--muted)',
              cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6,
            }}
          ><Icon name={tb.icon} size={12} /> {tb.label}</button>
        ))}
      </div>

      {/* Tab: Top Bullish/Bearish */}
      {tab === 'top' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 20 }}>
          <NewsColumn title="Bullish" items={positive} positive onUpgrade={onUpgrade} isPro={isPro} total={sorted.filter(n => n.sentiment > 0).length} t={t} />
          <NewsColumn title="Bearish" items={negative} positive={false} onUpgrade={onUpgrade} isPro={isPro} total={news.filter(n => n.sentiment < 0).length} t={t} />
        </div>
      )}

      {/* Tab: Recenti */}
      {tab === 'recent' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {recent.slice(0, shown).map((item, i) => (
            <RecentNewsItem key={i} item={item} />
          ))}

          {/* Lock per utenti free dopo i primi 5 */}
          {!isPro && recent.length > 5 && shown <= 5 && (
            <button onClick={onUpgrade} style={{
              padding: '12px 14px', borderRadius: 8,
              background: 'rgba(30,92,255,0.04)',
              border: '1px solid rgba(30,92,255,0.15)',
              cursor: 'pointer', textAlign: 'center',
            }}>
              <div style={{ fontSize: 13, color: 'var(--muted)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}><Icon name="lock" size={12} /> +{recent.length - 5} altre news</div>
              <div style={{ fontSize: 12, color: 'var(--azure)', marginTop: 4 }}>{t.topNews.lockedDesc}</div>
            </button>
          )}

          {/* Load more per PRO */}
          {isPro && shown < recent.length && (
            <button
              onClick={() => setShown(s => s + PAGE_SIZE)}
              style={{
                padding: '10px', borderRadius: 8, fontSize: 13,
                border: '1px solid var(--border-br)',
                background: 'transparent', color: 'var(--muted)',
                cursor: 'pointer',
              }}
            >
              Mostra altre {Math.min(PAGE_SIZE, recent.length - shown)} news <Icon name="arrow-down" size={13} style={{ marginLeft: 2 }} />
            </button>
          )}

          {isPro && shown >= recent.length && recent.length > PAGE_SIZE && (
            <p style={{ textAlign: 'center', fontSize: 12, color: 'var(--muted)' }}>
              Tutte le {recent.length} news caricate
            </p>
          )}
        </div>
      )}
    </div>
  )
}

// ── News item per tab Recenti ─────────────────────────────────────────────

function RecentNewsItem({ item }) {
  const score = Number(item.sentiment)
  const color = score >= 0.1 ? 'var(--green)' : score <= -0.1 ? 'var(--red)' : 'var(--muted)'
  const label = score >= 0.1 ? '▲' : score <= -0.1 ? '▼' : '─'

  return (
    <a
      href={item.url}
      target="_blank"
      rel="noopener noreferrer"
      style={{
        display: 'block', padding: '12px 14px',
        background: 'rgba(255,255,255,0.02)',
        border: '1px solid var(--border)',
        borderRadius: 8, transition: 'background .15s',
        textDecoration: 'none',
      }}
      onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.05)'}
      onMouseLeave={e => e.currentTarget.style.background = 'rgba(255,255,255,0.02)'}
    >
      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
        <span style={{ fontSize: 12, fontWeight: 700, color, flexShrink: 0, marginTop: 2, minWidth: 40 }}>
          {label} {Math.abs(score).toFixed(2)}
        </span>
        <span style={{ fontSize: 13, lineHeight: 1.5, color: 'var(--off-white)' }}>
          {item.title?.length > 100 ? item.title.slice(0, 100) + '…' : item.title}
        </span>
      </div>
      <div style={{ marginTop: 6, fontSize: 11, color: 'var(--muted)', paddingLeft: 50, display: 'flex', gap: 10 }}>
        <span>{item.source}</span>
        <span>·</span>
        <span>{item.published_date}</span>
      </div>
    </a>
  )
}

// ── Colonna Bullish/Bearish ───────────────────────────────────────────────

function NewsColumn({ title, items, positive, onUpgrade, isPro, total, t }) {
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
              textDecoration: 'none',
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
              borderLeft: '3px solid rgba(30,92,255,0.3)',
              cursor: 'pointer', textAlign: 'left',
            }}
          >
            <div style={{ fontSize: 13, color: 'var(--muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
              <Icon name="lock" size={12} /> +{hiddenCount} {t.topNews.lockedTitle}
            </div>
            <div style={{ fontSize: 12, color: 'var(--azure)', marginTop: 4 }}>
              {t.topNews.lockedDesc}
            </div>
          </button>
        )}
      </div>
    </div>
  )
}
