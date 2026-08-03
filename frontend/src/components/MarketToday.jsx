/**
 * MarketToday.jsx — screener "Mercato oggi": classifica dei ticker per
 * sentiment recente (endpoint pubblico /market/today, cache lato server).
 * Overlay a tutta pagina. Click su un ticker → lo carica
 * nella dashboard.
 */
import { useState, useEffect } from 'react'
import { useLang } from '../LangContext.jsx'
import apiFetch from '../apiFetch.js'
import Icon from './Icon.jsx'

const TXT = {
  it: {
    title: 'Mercato oggi', sub: 'Classifica per sentiment delle ultime 48 ore, dalle news analizzate dall\'AI. Copre i {n} titoli attualmente seguiti da Cheruvo, non l\'intero mercato.',
    bulls: 'Più rialzisti', bears: 'Più ribassisti', news: 'news', delta7: 'vs 7 giorni',
    empty: 'Dati in aggiornamento — torna tra qualche minuto.', back: '← App',
    updated: 'aggiornato', open: 'Apri →', loading: 'Caricamento…',
    earnTitle: 'Earnings in arrivo', earnSub: 'Sentiment degli ultimi 7 giorni prima dei conti.',
    days: 'giorni', tomorrow: 'domani', today: 'oggi', trendUp: 'in salita', trendDown: 'in calo',
    lockLine: 'Il sentiment pre-earnings è una funzione Pro',
    lockCta: 'Sblocca con Pro — €9/mese',
  },
  en: {
    title: 'Market today', sub: 'Sentiment ranking of the last 48 hours, from AI-analyzed news. Covers the {n} stocks Cheruvo currently tracks, not the entire market.',
    bulls: 'Most bullish', bears: 'Most bearish', news: 'news', delta7: 'vs 7 days',
    empty: 'Data is updating — check back in a few minutes.', back: '← App',
    updated: 'updated', open: 'Open →', loading: 'Loading…',
    earnTitle: 'Upcoming earnings', earnSub: 'Sentiment of the last 7 days before the report.',
    days: 'days', tomorrow: 'tomorrow', today: 'today', trendUp: 'rising', trendDown: 'falling',
    lockLine: 'Pre-earnings sentiment is a Pro feature',
    lockCta: 'Unlock with Pro — €9/month',
  },
}

const fmtScore = (v) => `${v > 0 ? '+' : ''}${Number(v).toFixed(2)}`
const scoreColor = (v) => (v > 0.08 ? '#34d399' : v < -0.08 ? '#f87171' : '#8a94a6')

export default function MarketToday({ onExit, onPick, onUpgrade }) {
  const { lang } = useLang()
  const s = TXT[lang] || TXT.it
  const [data, setData] = useState(null)
  const [earn, setEarn] = useState(null)
  const [err, setErr] = useState(false)

  useEffect(() => {
    apiFetch('/market/today').then(setData).catch(() => setErr(true))
    apiFetch('/earnings/upcoming').then(setEarn).catch(() => {})
  }, [])

  const rows = data?.rows || []
  const bulls = rows.filter((r) => r.sentiment > 0).slice(0, 8)
  const bears = rows.filter((r) => r.sentiment <= 0).slice(-8).reverse()
  const updatedAt = data?.updated_at
    ? new Date(data.updated_at).toLocaleTimeString(lang === 'it' ? 'it-IT' : 'en-US', { hour: '2-digit', minute: '2-digit' })
    : null

  const Row = ({ r, i }) => (
    <button onClick={() => onPick(r.ticker)} style={rowStyle} title={s.open}>
      <span style={{ color: 'var(--muted)', fontSize: 11, width: 18 }}>{i + 1}</span>
      <b style={{ fontSize: 14, flex: 1, textAlign: 'left' }}>{r.ticker}</b>
      <span style={{ fontSize: 11, color: 'var(--muted)' }}>{r.news} {s.news}</span>
      {r.delta != null && (
        <span style={{ fontSize: 11, color: r.delta >= 0 ? '#34d399' : '#f87171', width: 74, textAlign: 'right' }}>
          {fmtScore(r.delta)} {s.delta7}
        </span>
      )}
      <span style={{
        fontSize: 12.5, fontWeight: 700, color: scoreColor(r.sentiment),
        background: 'rgba(255,255,255,0.04)', border: `1px solid ${scoreColor(r.sentiment)}33`,
        borderRadius: 99, padding: '3px 10px', width: 64, textAlign: 'center',
      }}>{fmtScore(r.sentiment)}</span>
    </button>
  )

  return (
    <div style={{ height: '100dvh', overflow: 'auto', background: 'var(--black)', color: 'var(--white)' }}>
      <header style={{
        minHeight: 52, borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', gap: 8, padding: '8px 14px', background: 'var(--near-black)',
        position: 'sticky', top: 0, zIndex: 10,
      }}>
        <span style={{ fontSize: 16, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Icon name="analyzer" size={16} color="#60a5fa" /> {s.title}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {updatedAt && <span style={{ fontSize: 11, color: 'var(--muted)' }}>{s.updated} {updatedAt}</span>}
          <button onClick={onExit} style={{
            fontSize: 12, background: 'transparent', border: '1px solid var(--border)',
            borderRadius: 8, padding: '5px 10px', cursor: 'pointer', color: 'var(--white)',
          }}>{s.back}</button>
        </div>
      </header>

      <div style={{ maxWidth: 880, margin: '0 auto', padding: '24px 18px 60px' }}>
        <p style={{ color: 'var(--muted)', fontSize: 13.5, margin: '0 0 20px' }}>
          {rows.length ? s.sub.replace('{n}', rows.length) : s.sub.replace(' {n}', '')}
        </p>

        {!data && !err && <div style={{ color: 'var(--muted)', fontSize: 13 }}>{s.loading}</div>}
        {(err || (data && !rows.length)) && <div style={{ color: 'var(--muted)', fontSize: 13.5 }}>{s.empty}</div>}

        {rows.length > 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 18 }}>
            <div>
              <div style={groupTitle('#34d399')}>{s.bulls}</div>
              <div style={{ display: 'grid', gap: 7 }}>
                {bulls.map((r, i) => <Row key={r.ticker} r={r} i={i} />)}
                {!bulls.length && <span style={{ color: 'var(--muted)', fontSize: 12.5 }}>—</span>}
              </div>
            </div>
            <div>
              <div style={groupTitle('#f87171')}>{s.bears}</div>
              <div style={{ display: 'grid', gap: 7 }}>
                {bears.map((r, i) => <Row key={r.ticker} r={r} i={i} />)}
                {!bears.length && <span style={{ color: 'var(--muted)', fontSize: 12.5 }}>—</span>}
              </div>
            </div>
          </div>
        )}

        {earn && earn.rows && earn.rows.length > 0 && (
          <div style={{ marginTop: 30 }}>
            <div style={groupTitle('#f5c451')}>{s.earnTitle}</div>
            <p style={{ color: 'var(--muted)', fontSize: 12.5, margin: '0 0 10px' }}>{s.earnSub}</p>
            <div style={{ display: 'grid', gap: 7 }}>
              {earn.rows.map((r) => {
                const when = r.days_left === 0 ? s.today
                  : r.days_left === 1 ? s.tomorrow
                  : `${new Date(r.date).toLocaleDateString(lang === 'it' ? 'it-IT' : 'en-US', { day: 'numeric', month: 'short' })} · ${r.days_left} ${s.days}`
                return (
                  <button key={r.ticker} onClick={() => onPick(r.ticker)} style={rowStyle} title={s.open}>
                    <b style={{ fontSize: 14, width: 76, textAlign: 'left' }}>{r.ticker}</b>
                    <span style={{ fontSize: 12, color: '#f5c451', flex: 1, textAlign: 'left', display: 'inline-flex', alignItems: 'center', gap: 5 }}><Icon name="recent" size={12} color="#f5c451" /> {when}</span>
                    {earn.is_pro ? (
                      r.sentiment != null ? (
                        <>
                          {r.trend != null && (
                            <span style={{ fontSize: 11, color: r.trend >= 0 ? '#34d399' : '#f87171' }}>
                              {r.trend >= 0 ? '▲ ' + s.trendUp : '▼ ' + s.trendDown}
                            </span>
                          )}
                          <span style={{
                            fontSize: 12.5, fontWeight: 700, color: scoreColor(r.sentiment),
                            background: 'rgba(255,255,255,0.04)', border: `1px solid ${scoreColor(r.sentiment)}33`,
                            borderRadius: 99, padding: '3px 10px', width: 64, textAlign: 'center',
                          }}>{fmtScore(r.sentiment)}</span>
                        </>
                      ) : <span style={{ fontSize: 11, color: 'var(--muted)' }}>{r.news} {s.news}</span>
                    ) : (
                      <span style={{
                        fontSize: 12.5, fontWeight: 700, color: 'var(--muted)', filter: 'blur(4px)',
                        background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border)',
                        borderRadius: 99, padding: '3px 10px', width: 64, textAlign: 'center', userSelect: 'none',
                      }}>+0.00</span>
                    )}
                  </button>
                )
              })}
            </div>
            {!earn.is_pro && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginTop: 12,
                background: 'rgba(245,196,81,0.06)', border: '1px solid rgba(245,196,81,0.25)',
                borderRadius: 10, padding: '10px 14px',
              }}>
                <span style={{ fontSize: 12.5, color: 'var(--muted)', flex: 1, display: 'inline-flex', alignItems: 'center', gap: 6 }}><Icon name="lock" size={12} /> {s.lockLine}</span>
                {onUpgrade && (
                  <button onClick={onUpgrade} style={{
                    fontSize: 12, fontWeight: 600, color: '#f5c451', background: 'rgba(245,196,81,0.12)',
                    border: '1px solid rgba(245,196,81,0.35)', borderRadius: 99, padding: '7px 14px', cursor: 'pointer',
                  }}>{s.lockCta}</button>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

const rowStyle = {
  display: 'flex', alignItems: 'center', gap: 10, width: '100%',
  background: 'var(--near-black)', border: '1px solid var(--border)', borderRadius: 10,
  padding: '10px 12px', cursor: 'pointer', color: 'var(--white)',
}
const groupTitle = (color) => ({
  fontSize: 11.5, fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase',
  color, marginBottom: 10,
})
