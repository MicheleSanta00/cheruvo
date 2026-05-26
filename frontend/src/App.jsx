import { useState, useEffect } from 'react'
import Auth from './components/Auth.jsx'
import Profile from './components/Profile.jsx'
import { supabase } from './supabase.js'
import { useLang } from './LangContext.jsx'

import Sidebar  from './components/Sidebar.jsx'
import KPIGrid     from './components/KPIGrid.jsx'
import SummaryCard from './components/SummaryCard.jsx'
import Chart    from './components/Chart.jsx'
import TopNews  from './components/TopNews.jsx'
import Stats    from './components/Stats.jsx'
import { useFinData } from './hooks/useFinData.js'

const DEFAULT_TICKER = 'NVDA'
const DEFAULT_DAYS   = 30
const DEFAULT_PERIOD = '3mo'

export default function App() {
  const { lang, t, toggleLang } = useLang()

  const [user, setUser]               = useState(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [ticker, setTicker]           = useState(DEFAULT_TICKER)
  const [days, setDays]               = useState(DEFAULT_DAYS)
  const [period, setPeriod]           = useState(DEFAULT_PERIOD)
  const [isPro, setIsPro]             = useState(false)
  const [showProfile, setShowProfile] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  // FIX: ticker "confermato" — si aggiorna solo dopo che il caricamento è completato
  const [loadedTicker, setLoadedTicker] = useState(null)

  const { tickerInfo, news, stats, prices, sentiment, loading, fetching, error, load, triggerFetch } = useFinData()

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(session?.user ?? null)
      setAuthLoading(false)
    })
    supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null)
    })
  }, [])

  useEffect(() => {
    if (user) {
      fetch(`${import.meta.env.VITE_API_BASE}/subscription/${user.id}`)
        .then(r => r.json())
        .then(data => setIsPro(data.status === 'pro'))
        .catch(() => setIsPro(false))
    }
  }, [user])

  // FIX: handleLoad aggiorna loadedTicker solo a caricamento completato
  const handleLoad = async (tk, d, p) => {
    await load(tk, d, p)
    setLoadedTicker(tk)
    setSidebarOpen(false)
  }

  const handleFetch = async (tk) => {
    await triggerFetch(tk)
    setTimeout(() => handleLoad(tk, days, period), 3000)
  }

  const handleUpgrade = async () => {
    const res = await fetch(`${import.meta.env.VITE_API_BASE}/checkout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: user.email, user_id: user.id }),
    })
    const data = await res.json()
    if (data.url) window.location.href = data.url
  }

  const handleExport = () => {
    if (!isPro) { handleUpgrade(); return }
    if (!news.length) return
    const headers = ['title', 'source', 'published_date', 'sentiment', 'url']
    const rows = news.map(n => headers.map(h => `"${(n[h] || '').toString().replace(/"/g, '""')}`).join(','))
    const csv = [headers.join(','), ...rows].join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url
    a.download = `${ticker}_sentiment_${new Date().toISOString().slice(0,10)}.csv`
    a.click(); URL.revokeObjectURL(url)
  }

  if (authLoading) return null
  if (!user) return <Auth onLogin={setUser} />

  return (
    <div style={{ display: 'flex', height: '100dvh', overflow: 'hidden', background: 'var(--black)', position: 'relative' }}>

      {sidebarOpen && (
        <div
          onClick={() => setSidebarOpen(false)}
          style={{
            position: 'fixed', inset: 0, zIndex: 40,
            background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(2px)',
          }}
        />
      )}

      {showProfile && (
        <Profile
          user={user} isPro={isPro}
          onClose={() => setShowProfile(false)}
          onUpgrade={() => { setShowProfile(false); handleUpgrade() }}
        />
      )}

      <div style={{ position: 'relative', zIndex: 50 }}
        className={`sidebar-wrapper ${sidebarOpen ? 'sidebar-open' : ''}`}>
        <Sidebar
          ticker={ticker} days={days} period={period}
          loading={loading} fetching={fetching} isPro={isPro}
          onTickerChange={setTicker} onDaysChange={setDays} onPeriodChange={setPeriod}
          onLoad={(tk, d, p) => handleLoad(tk, d, p)}
          onFetch={handleFetch} onUpgrade={handleUpgrade}
        />
      </div>

      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: '100dvh', minWidth: 0 }}>

        <header style={{
          height: 56, flexShrink: 0,
          borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center',
          padding: '0 16px', gap: 12,
          background: 'var(--near-black)',
        }}>

          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="mobile-menu-btn"
            style={{
              display: 'none', background: 'transparent',
              color: 'var(--muted)', fontSize: 18, padding: '4px',
              border: '1px solid var(--border)', borderRadius: 6,
            }}
          >☰</button>

          {tickerInfo ? (
            <>
              <span style={{ fontSize: 15, fontWeight: 500, letterSpacing: '-0.01em', flexShrink: 0 }}>{tickerInfo.ticker}</span>
              <span style={{ fontSize: 14, color: 'var(--muted)', flexShrink: 0 }}>·</span>
              <span style={{ fontSize: 14, color: 'var(--muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{tickerInfo.nome}</span>
              {tickerInfo.settore && tickerInfo.settore !== 'N/A' && (
                <span style={{
                  fontSize: 11, color: 'var(--azure)', flexShrink: 0,
                  background: 'rgba(96,165,250,0.08)',
                  border: '1px solid rgba(96,165,250,0.15)',
                  padding: '3px 10px', borderRadius: 100,
                }} className="hide-mobile">{tickerInfo.settore}</span>
              )}
            </>
          ) : (
            <span style={{ fontSize: 14, color: 'var(--muted)', fontFamily: 'var(--serif)', fontStyle: 'italic' }}>
              {t.header.enterTicker}
            </span>
          )}

          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>

            {news.length > 0 && (
              <button
                onClick={handleExport}
                style={{
                  fontSize: 12, color: isPro ? 'var(--muted)' : 'rgba(255,255,255,0.2)',
                  border: '1px solid var(--border)', borderRadius: 6,
                  padding: '4px 10px', background: 'transparent', cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: 4,
                }}
                className="hide-mobile"
              >
                {isPro ? t.header.csv : t.header.csvLocked}
              </button>
            )}

            {loading && <Spinner />}
            {fetching && <Spinner color="var(--azure)" />}

            {isPro ? (
              <span style={{
                fontSize: 12, color: '#4ade80',
                border: '1px solid rgba(74,222,128,0.3)',
                borderRadius: 6, padding: '4px 10px',
              }}>{t.header.pro}</span>
            ) : (
              <button
                onClick={handleUpgrade}
                style={{
                  fontSize: 12, color: 'white', background: 'var(--blue)',
                  border: 'none', borderRadius: 6, padding: '4px 12px',
                  cursor: 'pointer', fontWeight: 500,
                }}>{t.header.upgradePro}</button>
            )}

            <button
              onClick={toggleLang}
              style={{
                fontSize: 14, background: 'transparent',
                border: '1px solid var(--border)',
                borderRadius: 6, padding: '4px 8px',
                cursor: 'pointer', lineHeight: 1,
              }}
              title={lang === 'it' ? 'Switch to English' : "Passa all'italiano"}
            >
              {lang === 'it' ? '🇮🇹' : '🇬🇧'}
            </button>

            <div
              onClick={() => setShowProfile(true)}
              title={user?.email}
              style={{
                width: 30, height: 30, borderRadius: '50%',
                background: 'var(--blue)', display: 'flex',
                alignItems: 'center', justifyContent: 'center',
                fontSize: 13, fontWeight: 500, cursor: 'pointer', flexShrink: 0,
              }}
            >
              {user?.email?.[0].toUpperCase()}
            </div>
          </div>
        </header>

        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 16px', display: 'flex', flexDirection: 'column', gap: 20 }}>

          {error && (
            <div style={{
              background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)',
              borderRadius: 10, padding: '12px 16px', fontSize: 14, color: 'var(--red)',
            }}>{error}</div>
          )}

          {stats && <KPIGrid stats={stats} />}

          {/* FIX: usa loadedTicker invece di ticker — la SummaryCard parte solo dopo il caricamento completo */}
          {tickerInfo && !loading && loadedTicker && (
            <SummaryCard ticker={loadedTicker} isPro={isPro} />
          )}

          {!loading && !tickerInfo && !error && <EmptyState t={t} />}

          {tickerInfo && !loading && !news.length && !error && (
            <div style={{
              background: 'rgba(96,165,250,0.06)', border: '1px solid rgba(96,165,250,0.15)',
              borderRadius: 12, padding: '24px 28px', textAlign: 'center',
            }}>
              <div style={{ fontSize: 15, color: 'var(--azure)', marginBottom: 8 }}>{t.main.noNews}</div>
              <div style={{ fontSize: 13, color: 'var(--muted)' }}>
                {t.main.noNewsHint} <b style={{ color: 'var(--white)' }}>{t.main.refreshNews}</b> {t.main.noNewsHint2}
              </div>
            </div>
          )}

          {(prices.length > 0 || news.length > 0) && (
            <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)', borderRadius: 12, padding: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
                <div>
                  <div style={{ fontSize: 15, fontWeight: 500, letterSpacing: '-0.01em' }}>{t.main.chartTitle(ticker)}</div>
                  <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 2 }}>{t.main.chartSub}</div>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <Legend color="var(--azure)" label={t.main.price} />
                  <Legend color="var(--green)" label={t.main.positive} />
                  <Legend color="var(--red)" label={t.main.negative} />
                </div>
              </div>
              <div style={{ height: 300 }}>
                <Chart prices={prices} sentiment={sentiment} ticker={ticker} />
              </div>
            </div>
          )}

          {news.length > 0 && <TopNews news={news} isPro={isPro} onUpgrade={handleUpgrade} />}
          {news.length > 0 && isPro && <Stats news={news} />}

          {news.length > 0 && !isPro && (
            <div style={{
              background: 'rgba(30,92,255,0.04)', border: '1px solid rgba(30,92,255,0.15)',
              borderRadius: 12, padding: '28px', textAlign: 'center',
            }}>
              <div style={{ fontSize: 15, color: 'var(--white)', marginBottom: 8, fontWeight: 500 }}>
                {t.main.advancedTitle}
              </div>
              <div style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 16 }}>
                {t.main.advancedDesc}
              </div>
              <button
                onClick={handleUpgrade}
                style={{
                  background: 'var(--blue)', color: 'white', border: 'none',
                  borderRadius: 8, padding: '10px 24px', fontSize: 14,
                  fontWeight: 500, cursor: 'pointer',
                }}>{t.main.upgradeBtn}</button>
            </div>
          )}

          <div style={{ height: 20 }} />
        </div>
      </main>
    </div>
  )
}

function Spinner({ color = 'var(--muted)' }) {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" style={{ animation: 'spin 0.8s linear infinite' }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <circle cx="7" cy="7" r="5.5" stroke={color} strokeWidth="1.5" strokeDasharray="20 14" strokeLinecap="round"/>
    </svg>
  )
}

function Legend({ color, label }) {
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--muted)' }}>
      <span style={{ width: 8, height: 8, background: color, borderRadius: 2, display: 'inline-block', opacity: 0.8 }}/>
      {label}
    </span>
  )
}

function EmptyState({ t }) {
  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      padding: '80px 40px', textAlign: 'center', gap: 16,
    }}>
      <div style={{
        width: 56, height: 56, background: 'rgba(30,92,255,0.1)',
        border: '1px solid rgba(30,92,255,0.2)', borderRadius: 14,
        display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 8,
      }}>
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--azure)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 12h4l3-9 4 18 3-9h4"/>
        </svg>
      </div>
      <h2 style={{ fontFamily: 'var(--serif)', fontSize: 28, fontWeight: 400, letterSpacing: '-0.02em' }}>
        {t.empty.title}
      </h2>
      <p style={{ fontSize: 14, color: 'var(--muted)', maxWidth: 400, lineHeight: 1.7 }}>
        {t.empty.desc}
      </p>
    </div>
  )
}