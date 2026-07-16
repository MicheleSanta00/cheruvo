import { useState, useEffect } from 'react'
import Auth        from './components/Auth.jsx'
import Profile     from './components/Profile.jsx'
import { supabase } from './supabase.js'
import { useLang }  from './LangContext.jsx'
import apiFetch    from './apiFetch.js'

import Sidebar     from './components/Sidebar.jsx'
import KPIGrid     from './components/KPIGrid.jsx'
import SummaryCard from './components/SummaryCard.jsx'
import Chart       from './components/Chart.jsx'
import TopNews     from './components/TopNews.jsx'
import Stats            from './components/Stats.jsx'
import CorrelationPanel from './components/CorrelationPanel.jsx'
import ComparePanel       from './components/ComparePanel.jsx'
import OnboardingTooltip  from './components/OnboardingTooltip.jsx'
import ChatWidget         from './components/ChatWidget.jsx'
import Icon               from './components/Icon.jsx'
import MarketToday        from './components/MarketToday.jsx'
import { useFinData } from './hooks/useFinData.js'
import { generateReport } from './utils/generatePDF.js'
import { identifyUser, resetUser, track } from './analytics.js'
import Academy from './academy/Academy.jsx'

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
  const [loadedTicker, setLoadedTicker] = useState(null)
  const [showStats, setShowStats]     = useState(false)
  const [showAcademy, setShowAcademy] = useState(false)
  const [showMarket, setShowMarket]   = useState(false)

  const { tickerInfo, news, stats, prices, sentiment, loading, fetching, error, load, triggerFetch } = useFinData()

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(session?.user ?? null)
      setAuthLoading(false)
    })
    supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null)
      if (!session) resetUser()  // logout: resetta identità PostHog
    })
  }, [])

  // Apri direttamente l'Academy se si arriva dal sottodominio academy.* o con ?academy
  // (?market apre lo screener — usato anche dalle scorciatoie PWA)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (window.location.hostname.startsWith('academy.') || params.get('academy') !== null) {
      setShowAcademy(true)
    } else if (params.get('market') !== null) {
      setShowMarket(true)
    }
  }, [])

  useEffect(() => {
    if (user) {
      apiFetch(`/subscription/${user.id}`)
        .then(data => {
          const pro = data.status === 'pro'
          setIsPro(pro)
          identifyUser(user.id, user.email, pro ? 'pro' : 'free')
        })
        .catch(() => setIsPro(false))
    }
  }, [user])

  const handleLoad = async (tk, d, p) => {
    await load(tk, d, p)
    setLoadedTicker(tk)
    setSidebarOpen(false)
    track('ticker_searched', { ticker: tk, days: d, period: p })
  }

  const handleFetch = async (tk) => {
    track('news_refreshed', { ticker: tk })
    await triggerFetch(tk)
    setTimeout(() => handleLoad(tk, days, period), 3000)
  }

  const handleUpgrade = async () => {
    track('upgrade_clicked', { ticker: loadedTicker, from: 'app' })
    const data = await apiFetch('/checkout', {
      method: 'POST',
      body: JSON.stringify({ email: user.email, user_id: user.id }),
    })
    if (data.url) window.location.href = data.url
  }

  const handlePDF = async () => {
    if (!isPro) { handleUpgrade(); return }
    if (!tickerInfo) return
    track('pdf_exported', { ticker: loadedTicker })
    let summary = null
    try { summary = await apiFetch(`/summary/${loadedTicker}`) } catch (_) {}
    await generateReport({ ticker, tickerInfo, stats, news, sentiment, prices, summary })
  }

  const handleExport = () => {
    if (!isPro) { handleUpgrade(); return }
    track('csv_exported', { ticker: loadedTicker })
    if (!news.length) return
    const headers = ['title', 'source', 'published_date', 'sentiment', 'sentiment_label', 'url']
    // Excel italiano si aspetta ';' e la virgola decimale; quello inglese ',' e il punto
    const isIt = lang === 'it'
    const SEP = isIt ? ';' : ','
    const esc = v => `"${(v ?? '').toString().replace(/"/g, '""')}"`
    const num = v => { const s = Number(v).toFixed(3); return isIt ? s.replace('.', ',') : s }
    const label = v => v == null ? '' : v > 0.1 ? 'bullish' : v < -0.1 ? 'bearish' : 'neutral'
    const rows = news.map(n => [
      esc(n.title),
      esc(n.source),
      esc((n.published_date || '').toString().slice(0, 10)),
      n.sentiment != null ? num(n.sentiment) : '',
      label(n.sentiment),
      esc(n.url),
    ].join(SEP))
    // BOM per gli accenti in Excel + CRLF
    const csv = String.fromCharCode(0xFEFF) + [headers.join(SEP), ...rows].join('\r\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url
    a.download = `${ticker}_sentiment_${new Date().toISOString().slice(0,10)}.csv`
    a.click(); URL.revokeObjectURL(url)
  }

  if (authLoading) return null
  if (!user) return <Auth onLogin={setUser} />
  if (showAcademy) return <Academy user={user} onExit={() => setShowAcademy(false)} />
  if (showMarket) return (
    <MarketToday
      onExit={() => setShowMarket(false)}
      onPick={(tk) => { setTicker(tk); setShowMarket(false); handleLoad(tk, days, period) }}
      onUpgrade={handleUpgrade}
    />
  )

  const hasData = !!tickerInfo && !loading

  return (
    <div style={{ display: 'flex', height: '100dvh', overflow: 'hidden', background: 'var(--black)', position: 'relative' }}>
      <OnboardingTooltip hasData={hasData} />
      <ChatWidget
        ticker={loadedTicker}
        sentimentScore={stats?.avg}
        topNews={news}
      />

      {/* Overlay mobile */}
      {sidebarOpen && (
        <div onClick={() => setSidebarOpen(false)} style={{
          position: 'fixed', inset: 0, zIndex: 40,
          background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(2px)',
        }} />
      )}

      {showProfile && (
        <Profile
          user={user} isPro={isPro}
          onClose={() => setShowProfile(false)}
          onUpgrade={() => { setShowProfile(false); handleUpgrade() }}
        />
      )}

      {/* Sidebar */}
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

      {/* Main area */}
      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', height: '100dvh', minWidth: 0 }}>

        {/* Header */}
        <header style={{
          height: 52, flexShrink: 0,
          borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center',
          padding: '0 16px', gap: 10,
          background: 'var(--near-black)',
        }}>
          <button onClick={() => setSidebarOpen(!sidebarOpen)} className="mobile-menu-btn"
            style={{ display: 'none', background: 'transparent', color: 'var(--muted)', padding: '4px', border: '1px solid var(--border)', borderRadius: 6, alignItems: 'center' }}>
            <Icon name="menu" size={18} />
          </button>

          {tickerInfo ? (
            <>
              <span style={{ fontSize: 15, fontWeight: 600, letterSpacing: '-0.01em', flexShrink: 0 }}>{tickerInfo.ticker}</span>
              <span style={{ fontSize: 13, color: 'var(--muted)', flexShrink: 0 }}>·</span>
              <span style={{ fontSize: 13, color: 'var(--muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{tickerInfo.nome}</span>
              {tickerInfo.settore && tickerInfo.settore !== 'N/A' && (
                <span className="hide-mobile" style={{
                  fontSize: 11, color: 'var(--azure)', flexShrink: 0,
                  background: 'rgba(96,165,250,0.08)', border: '1px solid rgba(96,165,250,0.15)',
                  padding: '2px 8px', borderRadius: 100,
                }}>{tickerInfo.settore}</span>
              )}
            </>
          ) : (
            <span style={{ fontSize: 13, color: 'var(--muted)', fontStyle: 'italic' }}>
              {t.header.enterTicker}
            </span>
          )}

          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
            {news.length > 0 && (
              <>
                <button onClick={handlePDF} className="hide-mobile" style={{
                  fontSize: 11, color: isPro ? 'var(--muted)' : 'rgba(255,255,255,0.2)',
                  border: '1px solid var(--border)', borderRadius: 6,
                  padding: '4px 10px', background: 'transparent', cursor: 'pointer',
                  display: 'inline-flex', alignItems: 'center', gap: 5,
                }}>
                  <Icon name={isPro ? 'pdf' : 'lock'} size={12} /> PDF
                </button>
                <button onClick={handleExport} className="hide-mobile" style={{
                  fontSize: 11, color: isPro ? 'var(--muted)' : 'rgba(255,255,255,0.2)',
                  border: '1px solid var(--border)', borderRadius: 6,
                  display: 'inline-flex', alignItems: 'center', gap: 5,
                  padding: '4px 10px', background: 'transparent', cursor: 'pointer',
                }}>
                  <Icon name={isPro ? 'csv' : 'lock'} size={12} /> CSV
                </button>
              </>
            )}
            {loading && <Spinner />}
            {fetching && <Spinner color="var(--azure)" />}
            {isPro ? (
              <span style={{ fontSize: 11, color: '#4ade80', border: '1px solid rgba(74,222,128,0.3)', borderRadius: 6, padding: '3px 8px' }}>
                {t.header.pro}
              </span>
            ) : (
              <button onClick={handleUpgrade} style={{
                fontSize: 11, color: 'white', background: 'var(--blue)',
                border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontWeight: 500,
              }}>{t.header.upgradePro}</button>
            )}
            <button onClick={() => setShowMarket(true)} title={lang === 'it' ? 'Mercato oggi' : 'Market today'} style={{
              fontSize: 11, color: 'var(--white)', background: 'transparent',
              border: '1px solid var(--border)', borderRadius: 6, padding: '4px 10px',
              cursor: 'pointer', fontWeight: 500,
            }}><Icon name="compare" size={13} /><span className="hide-mobile"> {lang === 'it' ? 'Mercato' : 'Market'}</span></button>
            <button onClick={() => setShowAcademy(true)} title="Cheruvo Academy" style={{
              fontSize: 11, color: 'var(--white)', background: 'transparent',
              border: '1px solid var(--border)', borderRadius: 6, padding: '4px 10px',
              cursor: 'pointer', fontWeight: 500,
            }}><Icon name="academy" size={14} /><span className="hide-mobile"> Academy</span></button>
            <a href="https://cheruvo.com/guida.html" target="_blank" rel="noreferrer" title={lang === 'it' ? 'Guida all\'uso' : 'User guide'} style={{
              display: 'inline-flex', alignItems: 'center', textDecoration: 'none',
              fontSize: 11, color: 'var(--white)', background: 'transparent',
              border: '1px solid var(--border)', borderRadius: 6, padding: '4px 10px',
              cursor: 'pointer', fontWeight: 500,
            }}><Icon name="book" size={13} /><span className="hide-mobile"> {lang === 'it' ? 'Guida' : 'Guide'}</span></a>
            <button onClick={toggleLang} style={{
              fontSize: 13, background: 'transparent', border: '1px solid var(--border)',
              borderRadius: 6, padding: '3px 7px', cursor: 'pointer', lineHeight: 1,
            }}>
              {lang === 'it' ? '🇮🇹' : '🇬🇧'}
            </button>
            <div onClick={() => setShowProfile(true)} title={user?.email} style={{
              width: 28, height: 28, borderRadius: '50%', background: 'var(--blue)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 12, fontWeight: 600, cursor: 'pointer', flexShrink: 0,
            }}>
              {user?.email?.[0].toUpperCase()}
            </div>
          </div>
        </header>

        {/* ── Content area ── */}
        {!hasData && !error ? (
          /* Empty / loading state — full width */
          <div style={{ flex: 1, overflowY: 'auto', padding: '20px 20px' }}>
            {error && <ErrorBanner msg={error} />}
            {!loading && !error && <EmptyState t={t} onLoad={handleLoad} days={days} period={period} />}
            {loading && <LoadingState />}
          </div>
        ) : (
          /* Two-column dashboard */
          <div className="dashboard-grid" style={{ flex: 1, overflow: 'hidden', display: 'grid', gridTemplateColumns: '380px 1fr', gridTemplateRows: '1fr' }}>

            {/* ── LEFT PANEL ── */}
            <div style={{
              borderRight: '1px solid var(--border)',
              overflowY: 'auto', padding: '20px 16px',
              display: 'flex', flexDirection: 'column', gap: 16,
            }}>
              {error && <ErrorBanner msg={error} />}

              {/* AI Summary */}
              {loadedTicker && (
                <SummaryCard ticker={loadedTicker} isPro={isPro} onUpgrade={handleUpgrade} />
              )}

              {/* KPI */}
              {stats && <div id="kpi-avg"><KPIGrid stats={stats} /></div>}

              {/* Stats PRO — collassabili */}
              {news.length > 0 && isPro && (
                <div>
                  <button
                    onClick={() => setShowStats(s => !s)}
                    style={{
                      width: '100%', display: 'flex', justifyContent: 'space-between',
                      alignItems: 'center', padding: '10px 14px',
                      background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)',
                      borderRadius: 8, cursor: 'pointer', fontSize: 12,
                      color: 'var(--muted)', marginBottom: showStats ? 12 : 0,
                    }}
                  >
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><Icon name="analytics" size={13} /> Analytics avanzate</span>
                    <Icon name="chevron-down" size={14} style={{ transition: 'transform .2s', transform: showStats ? 'rotate(180deg)' : 'none' }} />
                  </button>
                  {showStats && <Stats news={news} />}
                </div>
              )}

              {/* Upgrade banner FREE */}
              {news.length > 0 && !isPro && (
                <div style={{
                  background: 'rgba(30,92,255,0.04)', border: '1px solid rgba(30,92,255,0.15)',
                  borderRadius: 10, padding: '16px',
                }}>
                  <div style={{ fontSize: 13, color: 'var(--white)', marginBottom: 6, fontWeight: 500 }}>
                    {t.main.advancedTitle}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 12, lineHeight: 1.6 }}>
                    {t.main.advancedDesc}
                  </div>
                  <button onClick={handleUpgrade} style={{
                    background: 'var(--blue)', color: 'white', border: 'none',
                    borderRadius: 7, padding: '8px 18px', fontSize: 13,
                    fontWeight: 500, cursor: 'pointer', width: '100%',
                  }}>{t.main.upgradeBtn}</button>
                </div>
              )}

              <div style={{ height: 8 }} />
            </div>

            {/* ── RIGHT PANEL ── */}
            <div style={{ overflowY: 'auto', padding: '20px 20px', display: 'flex', flexDirection: 'column', gap: 20 }}>

              {/* Chart */}
              {(prices.length > 0 || news.length > 0) && (
                <div style={{
                  background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)',
                  borderRadius: 12, padding: '16px 20px',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14, flexWrap: 'wrap', gap: 8 }}>
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 500, letterSpacing: '-0.01em' }}>{t.main.chartTitle(ticker)}</div>
                      <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>{t.main.chartSub}</div>
                    </div>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <Legend color="var(--azure)"  label={t.main.price} />
                      <Legend color="var(--green)"  label={t.main.positive} />
                      <Legend color="var(--red)"    label={t.main.negative} />
                    </div>
                  </div>
                  <div id="chart-area"><Chart prices={prices} sentiment={sentiment} ticker={ticker} stats={stats} /></div>
                </div>
              )}

              {/* No news notice */}
              {tickerInfo && !loading && !news.length && !error && (
                <div style={{
                  background: 'rgba(96,165,250,0.06)', border: '1px solid rgba(96,165,250,0.15)',
                  borderRadius: 12, padding: '24px', textAlign: 'center',
                }}>
                  <div style={{ fontSize: 14, color: 'var(--azure)', marginBottom: 8 }}>{t.main.noNews}</div>
                  <div style={{ fontSize: 12, color: 'var(--muted)' }}>
                    {t.main.noNewsHint} <b style={{ color: 'var(--white)' }}>{t.main.refreshNews}</b> {t.main.noNewsHint2}
                  </div>
                </div>
              )}

              {/* Confronto multi-ticker */}
              {sentiment.length > 0 && (
                <ComparePanel
                  primaryTicker={ticker}
                  primarySentiment={sentiment}
                  isPro={isPro}
                  onUpgrade={handleUpgrade}
                />
              )}

              {/* Correlazione sentiment/prezzo */}
              {prices.length > 0 && sentiment.length > 0 && (
                <CorrelationPanel
                  prices={prices}
                  sentiment={sentiment}
                  isPro={isPro}
                  onUpgrade={handleUpgrade}
                />
              )}

              {/* News */}
              {news.length > 0 && (
                <div id="top-news">
                  <TopNews news={news} isPro={isPro} onUpgrade={handleUpgrade} />
                </div>
              )}

              <div style={{ height: 12 }} />
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

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

function ErrorBanner({ msg }) {
  return (
    <div style={{
      background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)',
      borderRadius: 10, padding: '12px 16px', fontSize: 13, color: 'var(--red)',
    }}>{msg}</div>
  )
}

function LoadingState() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh', gap: 10, color: 'var(--muted)', fontSize: 13 }}>
      <svg width="16" height="16" viewBox="0 0 14 14" fill="none" style={{ animation: 'spin 0.8s linear infinite' }}>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        <circle cx="7" cy="7" r="5.5" stroke="var(--muted)" strokeWidth="1.5" strokeDasharray="20 14" strokeLinecap="round"/>
      </svg>
      Caricamento...
    </div>
  )
}

const SUGGESTED_TICKERS = [
  { symbol: 'NVDA',   name: 'NVIDIA',        flag: '🇺🇸' },
  { symbol: 'AAPL',   name: 'Apple',          flag: '🇺🇸' },
  { symbol: 'TSLA',   name: 'Tesla',          flag: '🇺🇸' },
  { symbol: 'ENI.MI', name: 'Eni',            flag: '🇮🇹' },
  { symbol: 'MSFT',   name: 'Microsoft',      flag: '🇺🇸' },
  { symbol: 'ENEL.MI',name: 'Enel',           flag: '🇮🇹' },
]

function EmptyState({ t, onLoad, days, period }) {
  const [showWelcome, setShowWelcome] = useState(() => {
    return !localStorage.getItem('cheruvo_welcomed')
  })

  const dismissWelcome = () => {
    localStorage.setItem('cheruvo_welcomed', '1')
    setShowWelcome(false)
  }

  const handleSuggestion = (symbol) => {
    dismissWelcome()
    onLoad(symbol, days, period)
  }

  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', position: 'relative',
      padding: '60px 40px', textAlign: 'center', gap: 20, maxWidth: 560, margin: '0 auto',
    }}>
      {/* Glow soffuso + Sentiment Orb: dà vita alla schermata iniziale (lega app e landing) */}
      <div className="welcome-glow" aria-hidden="true" />
      <div className="orb" title="Il battito del mercato" style={{ position: 'relative', zIndex: 1, marginBottom: 4 }}>
        <span className="ring"></span><span className="ring r2"></span><span className="core"></span>
      </div>

      {/* Welcome banner — solo al primo accesso */}
      {showWelcome && (
        <div style={{
          width: '100%', background: 'rgba(30,92,255,0.08)',
          border: '1px solid rgba(30,92,255,0.25)', borderRadius: 14,
          padding: '20px 24px', textAlign: 'left', position: 'relative',
        }}>
          <button
            onClick={dismissWelcome}
            style={{
              position: 'absolute', top: 12, right: 12,
              background: 'transparent', color: 'var(--muted)',
              fontSize: 16, padding: '2px 6px', borderRadius: 4,
              border: '1px solid transparent', display: 'flex', alignItems: 'center',
            }}
          ><Icon name="close" size={15} /></button>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--azure)', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 7 }}>
            <Icon name="welcome" size={16} /> {t.empty.welcomeTitle}
          </div>
          <div style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.7 }}>
            {t.empty.welcomeDesc}
          </div>
        </div>
      )}

      {/* Icona */}
      <div style={{ width: 80, height: 80, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <img src="/logo-v2.png" alt="Cheruvo" style={{ width: 80, height: 80, filter: 'brightness(1) drop-shadow(0 0 12px rgba(255,255,255,0.9)) drop-shadow(0 0 24px rgba(255,255,255,0.5)) drop-shadow(0 0 40px rgba(255,255,255,0.2))' }} />
      </div>

      <div>
        <h2 style={{ fontFamily: 'var(--serif)', fontSize: 26, fontWeight: 400, letterSpacing: '-0.02em', marginBottom: 10 }}>
          {t.empty.title}
        </h2>
        <p style={{ fontSize: 14, color: 'var(--muted)', lineHeight: 1.7 }}>
          {t.empty.desc}
        </p>
      </div>

      {/* Ticker suggeriti */}
      <div style={{ width: '100%' }}>
        <div style={{ fontSize: 11, color: 'var(--muted)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 10 }}>
          {t.empty.suggestions}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center' }}>
          {SUGGESTED_TICKERS.map(tk => (
            <button
              key={tk.symbol}
              onClick={() => handleSuggestion(tk.symbol)}
              style={{
                padding: '8px 14px', borderRadius: 8, fontSize: 13,
                border: '1px solid var(--border-br)',
                background: 'rgba(255,255,255,0.03)',
                color: 'var(--white)', cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: 6,
                transition: 'border-color 0.15s, background 0.15s',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.borderColor = 'rgba(30,92,255,0.5)'
                e.currentTarget.style.background = 'rgba(30,92,255,0.08)'
              }}
              onMouseLeave={e => {
                e.currentTarget.style.borderColor = 'var(--border-br)'
                e.currentTarget.style.background = 'rgba(255,255,255,0.03)'
              }}
            >
              <span>{tk.flag}</span>
              <span style={{ fontWeight: 600 }}>{tk.symbol}</span>
              <span style={{ fontSize: 11, color: 'var(--muted)' }}>{tk.name}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}