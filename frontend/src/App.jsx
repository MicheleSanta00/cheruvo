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
import { TICKERS } from './data/tickers.js'

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
  const [showHeaderMenu, setShowHeaderMenu] = useState(false)
  const [showMarket, setShowMarket]   = useState(false)

  const { tickerInfo, news, stats, prices, sentiment, loading, fetching, error, load, triggerFetch, setFetching } = useFinData()

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

  // L'Academy non è più nell'interfaccia, ma resta raggiungibile dal
  // sottodominio academy.* o con ?academy: così i link già in giro non si
  // rompono e riattivarla è questione di rimettere un bottone.
  // ?market non serve più: la schermata iniziale È il mercato.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (window.location.hostname.startsWith('academy.') || params.get('academy') !== null) {
      setShowAcademy(true)
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

  const handleLoad = async (tk, d, p, autoFetch = true) => {
    const res = await load(tk, d, p)
    setLoadedTicker(tk)
    setSidebarOpen(false)
    track('ticker_searched', { ticker: tk, days: d, period: p })

    // Ticker mai scaricato prima: invece di mostrare una schermata vuota (che
    // fa sembrare il sito rotto) scarichiamo le news al volo. Il server lavora
    // in background, quindi riproviamo a caricare due volte e poi lasciamo
    // perdere in silenzio. autoFetch=false evita di rientrare qui a catena.
    if (autoFetch && res && !res.error && res.newsCount === 0) {
      track('auto_fetch_triggered', { ticker: tk })
      await triggerFetch(tk)
      setFetching(true)
      try {
        for (const wait of [3000, 4000]) {
          await new Promise((r) => setTimeout(r, wait))
          const retry = await load(tk, d, p)
          if (retry && retry.newsCount > 0) break
        }
      } finally {
        setFetching(false)
      }
    }
  }

  const handleFetch = async (tk) => {
    track('news_refreshed', { ticker: tk })
    await triggerFetch(tk)
    setTimeout(() => handleLoad(tk, days, period, false), 3000)
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
          hasTicker={!!loadedTicker}
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
              <span style={{ fontSize: 15, fontWeight: 700, letterSpacing: '-0.01em', flexShrink: 0 }}>{tickerInfo.ticker}</span>
              <span style={{ fontSize: 13, color: 'var(--muted)', flexShrink: 0 }}>·</span>
              <span style={{ fontSize: 13, color: 'var(--muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{tickerInfo.nome}</span>

              {/* Prezzo e giudizio accanto al nome: in un terminale l'identità
                  di un titolo è ticker + prezzo + stato, non solo il nome. */}
              {prices?.length > 0 && (() => {
                const ultimo = prices[prices.length - 1]
                const primo = prices[0]
                const px = Number(ultimo?.Close ?? ultimo?.close)
                const px0 = Number(primo?.Close ?? primo?.close)
                if (!isFinite(px)) return null
                const varPct = isFinite(px0) && px0 ? ((px - px0) / px0) * 100 : null
                const su = varPct != null && varPct >= 0
                return (
                  <span className="hide-mobile" style={{
                    display: 'inline-flex', alignItems: 'baseline', gap: 7, flexShrink: 0,
                    fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums', marginLeft: 4,
                  }}>
                    <span style={{ fontSize: 14, fontWeight: 700 }}>{px.toFixed(2)}</span>
                    {varPct != null && (
                      <span style={{ fontSize: 11.5, fontWeight: 700, color: su ? 'var(--green)' : 'var(--red)' }}>
                        {su ? '+' : '−'}{Math.abs(varPct).toFixed(2)}%
                      </span>
                    )}
                  </span>
                )
              })()}

              {stats?.avg != null && (
                <span className="hide-mobile" style={{
                  fontSize: 10, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase',
                  flexShrink: 0, padding: '2px 8px', borderRadius: 5,
                  fontFamily: 'var(--mono)',
                  color: stats.avg > 0.08 ? 'var(--green)' : stats.avg < -0.08 ? 'var(--red)' : 'var(--muted)',
                  background: stats.avg > 0.08 ? 'rgba(52,211,153,0.10)' : stats.avg < -0.08 ? 'rgba(248,113,113,0.10)' : 'rgba(255,255,255,0.04)',
                  border: '1px solid var(--border-br)',
                }}>
                  {stats.avg > 0 ? '+' : stats.avg < 0 ? '−' : ''}{Math.abs(stats.avg).toFixed(2)}
                </span>
              )}
            </>
          ) : (
            <HeaderSearch
              placeholder={t.header.enterTicker}
              days={days} period={period}
              onLoad={handleLoad} onTickerChange={setTicker}
            />
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
            {/* "Mercato" rimosso: la schermata iniziale È il mercato, il bottone
                mostrava la stessa cosa due volte. L'Academy è stata tolta
                dall'interfaccia perché fuori fuoco rispetto al prodotto: il
                codice resta in academy/, quindi si può riattivare quando serve. */}
            <a href="https://cheruvo.com/guida.html" target="_blank" rel="noreferrer" className="hide-mobile" title={lang === 'it' ? 'Guida all\'uso' : 'User guide'} style={{
              display: 'inline-flex', alignItems: 'center', textDecoration: 'none',
              fontSize: 11, color: 'var(--white)', background: 'transparent',
              border: '1px solid var(--border)', borderRadius: 6, padding: '4px 10px',
              cursor: 'pointer', fontWeight: 500,
            }}><Icon name="book" size={13} /> {lang === 'it' ? 'Guida' : 'Guide'}</a>
            <button onClick={toggleLang} className="hide-mobile" style={{
              fontSize: 13, background: 'transparent', border: '1px solid var(--border)',
              borderRadius: 6, padding: '3px 7px', cursor: 'pointer', lineHeight: 1,
            }}>
              {lang === 'it' ? '🇮🇹' : '🇬🇧'}
            </button>

            {/* Menu opzioni — solo mobile: raccoglie export, viste e lingua */}
            <div className="mobile-only" style={{ position: 'relative' }}>
              <button onClick={() => setShowHeaderMenu(v => !v)} aria-label="Menu opzioni" style={{
                color: 'var(--white)', background: 'transparent',
                border: '1px solid var(--border)', borderRadius: 6, padding: '4px 8px',
                cursor: 'pointer', display: 'inline-flex', alignItems: 'center',
              }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                  <circle cx="12" cy="5" r="1.9" /><circle cx="12" cy="12" r="1.9" /><circle cx="12" cy="19" r="1.9" />
                </svg>
              </button>
              {showHeaderMenu && (() => {
                const close = () => setShowHeaderMenu(false)
                const item = {
                  display: 'flex', alignItems: 'center', gap: 10, width: '100%',
                  padding: '10px 12px', borderRadius: 8, fontSize: 13, color: 'var(--white)',
                  background: 'transparent', border: 'none', cursor: 'pointer',
                  textAlign: 'left', textDecoration: 'none', fontFamily: 'var(--sans)',
                }
                return (
                  <>
                    <div onClick={close} style={{ position: 'fixed', inset: 0, zIndex: 98 }} />
                    <div style={{
                      position: 'absolute', top: 'calc(100% + 8px)', right: 0, zIndex: 99,
                      background: 'var(--dark2)', border: '1px solid var(--border-br)',
                      borderRadius: 12, padding: 6, minWidth: 195,
                      boxShadow: '0 14px 40px rgba(0,0,0,0.55)',
                      display: 'flex', flexDirection: 'column', gap: 2,
                    }}>
                      {news.length > 0 && (
                        <>
                          <button onClick={() => { close(); handlePDF() }} style={item}>
                            <Icon name={isPro ? 'pdf' : 'lock'} size={14} /> {lang === 'it' ? 'Report PDF' : 'PDF report'}
                          </button>
                          <button onClick={() => { close(); handleExport() }} style={item}>
                            <Icon name={isPro ? 'csv' : 'lock'} size={14} /> {lang === 'it' ? 'Esporta CSV' : 'Export CSV'}
                          </button>
                        </>
                      )}
                      {/* Mercato e Academy tolti anche dal menu mobile, per coerenza */}
                      <a href="https://cheruvo.com/guida.html" target="_blank" rel="noreferrer" onClick={close} style={item}>
                        <Icon name="book" size={14} /> {lang === 'it' ? 'Guida' : 'Guide'}
                      </a>
                      <button onClick={() => { close(); toggleLang() }} style={item}>
                        <span style={{ fontSize: 14, lineHeight: 1 }}>{lang === 'it' ? '🇬🇧' : '🇮🇹'}</span> {lang === 'it' ? 'English' : 'Italiano'}
                      </button>
                    </div>
                  </>
                )
              })()}
            </div>

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
          <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', minHeight: 0 }}>

          {/* Striscia metriche a tutta larghezza, subito sotto l'intestazione:
              è la fascia di riepilogo del titolo, come in un terminale. Prima
              stava dentro la colonna da 380px, dove sembrava un widget fra i
              tanti invece che l'identità numerica del titolo. */}
          {stats && <div id="kpi-avg"><KPIGrid stats={stats} /></div>}

          <div className="dashboard-grid" style={{ flex: 1, overflow: 'hidden', display: 'grid', gridTemplateColumns: '380px 1fr', gridTemplateRows: '1fr', minHeight: 0 }}>

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
          </div>
        )}
      </main>
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

// ── Ricerca ticker nell'header (con suggerimenti, come la sidebar) ─────────
function HeaderSearch({ placeholder, days, period, onLoad, onTickerChange }) {
  const [q, setQ] = useState('')
  const [sugg, setSugg] = useState([])
  const [open, setOpen] = useState(false)

  const change = (e) => {
    const v = e.target.value.toUpperCase()
    setQ(v)
    if (v.length >= 1) {
      const f = TICKERS.filter(tk =>
        tk.symbol.startsWith(v) || tk.name.toUpperCase().includes(v)
      ).slice(0, 6)
      setSugg(f)
      setOpen(f.length > 0)
    } else {
      setOpen(false)
    }
  }

  const go = (sym) => {
    const v = (sym || q).trim().toUpperCase()
    if (!v) return
    setOpen(false)
    setQ(v)
    onTickerChange?.(v)
    onLoad(v, days, period)
  }

  return (
    <div style={{ position: 'relative', flex: 1, maxWidth: 340, minWidth: 0 }}>
      <input
        value={q}
        onChange={change}
        onKeyDown={e => { if (e.key === 'Enter') go(); if (e.key === 'Escape') setOpen(false) }}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onFocus={() => q.length >= 1 && setOpen(sugg.length > 0)}
        placeholder={placeholder}
        style={{
          width: '100%', background: 'var(--dark)',
          border: '1px solid var(--border-br)', color: 'var(--white)',
          borderRadius: 7, padding: '7px 12px', fontSize: 13,
          outline: 'none', fontFamily: 'var(--sans)',
        }}
      />
      {open && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 6px)', left: 0, right: 0,
          background: 'var(--dark)', border: '1px solid var(--border)',
          borderRadius: 8, zIndex: 100, overflow: 'hidden',
          boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
        }}>
          {sugg.map(tk => (
            <div
              key={tk.symbol}
              onMouseDown={() => go(tk.symbol)}
              style={{
                padding: '9px 12px', fontSize: 13, cursor: 'pointer',
                display: 'flex', gap: 8, alignItems: 'baseline',
              }}
            >
              <b>{tk.symbol}</b>
              <span style={{ color: 'var(--muted)', fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{tk.name}</span>
            </div>
          ))}
        </div>
      )}
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

// ── Schermata iniziale: una PLANCIA, non un cartello di benvenuto ───────────
// Prima qui c'era un orb animato con "Benvenuto": bello ma vuoto, e faceva
// sembrare Cheruvo un tool in attesa di comandi. Ora chi apre l'app vede
// subito lo stato del mercato, come in un terminale professionale.

// Numeri sempre monospaziati e tabulari: è il dettaglio che più distingue
// un terminale finanziario da un sito qualsiasi.
const numStyle = {
  fontFamily: 'var(--mono, ui-monospace, monospace)',
  fontVariantNumeric: 'tabular-nums',
  fontWeight: 700,
}
const segno = (v) => (v > 0.08 ? 'var(--green, #2ee6a8)' : v < -0.08 ? 'var(--red, #f87171)' : 'var(--muted)')
const fmt = (v) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(Number(v)).toFixed(2)}`

function Pannello({ titolo, extra, children }) {
  return (
    <div style={{
      border: '1px solid var(--border-br)', borderRadius: 10,
      background: 'rgba(255,255,255,0.015)', overflow: 'hidden',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '8px 12px', borderBottom: '1px solid var(--border-br)',
        background: 'rgba(255,255,255,0.02)',
      }}>
        <span style={{ fontSize: 10.5, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--muted)', fontWeight: 700 }}>
          {titolo}
        </span>
        {extra && <span style={{ fontSize: 10.5, color: 'var(--muted)', ...numStyle, fontWeight: 500 }}>{extra}</span>}
      </div>
      {children}
    </div>
  )
}

function EmptyState({ t, onLoad, days, period }) {
  const { lang } = useLang()
  const [mercato, setMercato] = useState(null)
  const [stats, setStats] = useState(null)
  const [errore, setErrore] = useState(false)

  useEffect(() => {
    let vivo = true
    apiFetch('/market/today')
      .then((d) => { if (vivo) setMercato(d) })
      .catch(() => { if (vivo) setErrore(true) })
    apiFetch('/market/stats')
      .then((d) => { if (vivo) setStats(d) })
      .catch(() => {})
    return () => { vivo = false }
  }, [])

  const righe = mercato?.rows || []
  const rialzisti = righe.filter((r) => r.sentiment > 0).slice(0, 6)
  const ribassisti = righe.filter((r) => r.sentiment <= 0).slice(-6).reverse()
  const ora = mercato?.updated_at
    ? new Date(mercato.updated_at).toLocaleTimeString(lang === 'it' ? 'it-IT' : 'en-US', { hour: '2-digit', minute: '2-digit' })
    : null

  const Riga = ({ r, i }) => (
    <button
      onClick={() => onLoad(r.ticker, days, period)}
      style={{
        display: 'grid', gridTemplateColumns: '18px 1fr auto auto', gap: 10,
        alignItems: 'center', width: '100%', padding: '7px 12px',
        borderBottom: '1px solid var(--border-br)', background: 'transparent',
        border: 'none', borderRadius: 0, cursor: 'pointer', textAlign: 'left',
        color: 'var(--white)', fontSize: 13,
      }}
      onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.04)' }}
      onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
    >
      <span style={{ ...numStyle, fontWeight: 500, fontSize: 10.5, color: 'var(--muted)' }}>{i + 1}</span>
      <span style={{ fontWeight: 700 }}>{r.ticker}</span>
      <span style={{ fontSize: 10.5, color: 'var(--muted)' }}>{r.news} {t.empty.newsShort}</span>
      <span style={{ ...numStyle, color: segno(r.sentiment) }}>{fmt(r.sentiment)}</span>
    </button>
  )

  const Metrica = ({ etichetta, valore }) => (
    <div style={{ padding: '10px 14px', borderRight: '1px solid var(--border-br)', flex: 1, minWidth: 110 }}>
      <div style={{ fontSize: 10, letterSpacing: '0.11em', textTransform: 'uppercase', color: 'var(--muted)', fontWeight: 700 }}>
        {etichetta}
      </div>
      <div style={{ ...numStyle, fontSize: 18, marginTop: 3 }}>{valore ?? '—'}</div>
    </div>
  )

  return (
    <div style={{ flex: 1, overflow: 'auto', padding: '18px 20px 28px' }}>
      {/* intestazione */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap', marginBottom: 14 }}>
        <h2 style={{ fontFamily: 'var(--serif)', fontSize: 21, fontWeight: 400, letterSpacing: '-0.01em' }}>
          {t.empty.boardTitle}
        </h2>
        <span style={{ fontSize: 12.5, color: 'var(--muted)' }}>{t.empty.boardSub}</span>
        {ora && (
          <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--muted)', ...numStyle, fontWeight: 500 }}>
            {t.empty.updatedAt} {ora}
          </span>
        )}
      </div>

      {/* fascia metriche */}
      <div style={{
        display: 'flex', flexWrap: 'wrap', border: '1px solid var(--border-br)',
        borderRadius: 10, overflow: 'hidden', marginBottom: 16,
        background: 'rgba(255,255,255,0.015)',
      }}>
        <Metrica etichetta={t.empty.kTickers} valore={stats?.tickers} />
        <Metrica etichetta={t.empty.kNews} valore={stats?.news_total?.toLocaleString(lang === 'it' ? 'it-IT' : 'en-US')} />
        <Metrica etichetta={t.empty.k24h} valore={stats?.news_today} />
        <Metrica etichetta={t.empty.kRanked} valore={righe.length || null} />
      </div>

      {/* classifiche */}
      {!mercato && !errore && (
        <div style={{ color: 'var(--muted)', fontSize: 13, padding: '20px 0' }}>{t.empty.loading}</div>
      )}
      {(errore || (mercato && !righe.length)) && (
        <div style={{ color: 'var(--muted)', fontSize: 13, padding: '20px 0' }}>{t.empty.offline}</div>
      )}
      {righe.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 14 }}>
          <Pannello titolo={t.empty.bulls} extra={`${rialzisti.length}`}>
            {rialzisti.map((r, i) => <Riga key={r.ticker} r={r} i={i} />)}
            {!rialzisti.length && <div style={{ padding: 12, color: 'var(--muted)', fontSize: 12.5 }}>—</div>}
          </Pannello>
          <Pannello titolo={t.empty.bears} extra={`${ribassisti.length}`}>
            {ribassisti.map((r, i) => <Riga key={r.ticker} r={r} i={i} />)}
            {!ribassisti.length && <div style={{ padding: 12, color: 'var(--muted)', fontSize: 12.5 }}>—</div>}
          </Pannello>
        </div>
      )}

      {/* ticker suggeriti, in forma compatta */}
      <div style={{ marginTop: 20 }}>
        <div style={{ fontSize: 10.5, color: 'var(--muted)', letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 9, fontWeight: 700 }}>
          {t.empty.suggestions}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
          {SUGGESTED_TICKERS.map(tk => (
            <button
              key={tk.symbol}
              onClick={() => onLoad(tk.symbol, days, period)}
              style={{
                padding: '6px 11px', borderRadius: 7, fontSize: 12.5,
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
              <span style={{ fontWeight: 700 }}>{tk.symbol}</span>
              <span style={{ fontSize: 11, color: 'var(--muted)' }}>{tk.name}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}