import { useState, useEffect } from 'react'
import Auth from './components/Auth.jsx'
import { supabase } from './supabase.js'

import Sidebar  from './components/Sidebar.jsx'
import KPIGrid  from './components/KPIGrid.jsx'
import Chart    from './components/Chart.jsx'
import TopNews  from './components/TopNews.jsx'
import Stats    from './components/Stats.jsx'
import { useFinData } from './hooks/useFinData.js'

const DEFAULT_TICKER = 'NVDA'
const DEFAULT_DAYS   = 30
const DEFAULT_PERIOD = '3mo'

export default function App() {

  const [user, setUser] = useState(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [ticker, setTicker] = useState(DEFAULT_TICKER)
  const [days, setDays]     = useState(DEFAULT_DAYS)
  const [period, setPeriod] = useState(DEFAULT_PERIOD)

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

  const handleFetch = async (t) => {
    await triggerFetch(t)
    setTimeout(() => load(t, days, period), 3000)
  }

  if (authLoading) return null
  if (!user) return <Auth onLogin={setUser} />

  const [isPro, setIsPro] = useState(false)

  useEffect(() => {
    if (user) {
      fetch(`${import.meta.env.VITE_API_BASE}/api/subscription/${user.id}`)
        .then(r => r.json())
        .then(data => setIsPro(data.status === 'pro'))
    }
  }, [user])

  const handleUpgrade = async () => {
    const res = await fetch(`${import.meta.env.VITE_API_BASE}/api/checkout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: user.email, user_id: user.id }),
    })
    const data = await res.json()
    if (data.url) window.location.href = data.url
  }
    
  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', background: 'var(--black)' }}>

      {/* Sidebar */}
      <Sidebar
        ticker={ticker}
        days={days}
        period={period}
        loading={loading}
        fetching={fetching}
        onTickerChange={setTicker}
        onDaysChange={setDays}
        onPeriodChange={setPeriod}
        onLoad={load}
        onFetch={handleFetch}
      />

      {/* Main area */}
      <main style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        overflow: 'hidden', height: '100vh',
      }}>
        {/* Top bar */}
        <header style={{
          height: 56, flexShrink: 0,
          borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center',
          padding: '0 28px', gap: 16,
          background: 'var(--near-black)',
        }}>
          {tickerInfo ? (
            <>
              <span style={{ fontSize: 16, fontWeight: 500, letterSpacing: '-0.01em' }}>{tickerInfo.ticker}</span>
              <span style={{ fontSize: 14, color: 'var(--muted)' }}>·</span>
              <span style={{ fontSize: 14, color: 'var(--muted)' }}>{tickerInfo.nome}</span>
              {tickerInfo.settore && tickerInfo.settore !== 'N/A' && (
                <span style={{
                  fontSize: 11, color: 'var(--azure)',
                  background: 'rgba(96,165,250,0.08)',
                  border: '1px solid rgba(96,165,250,0.15)',
                  padding: '3px 10px', borderRadius: 100,
                }}>{tickerInfo.settore}</span>
              )}
            </>
          ) : (
            <span style={{ fontSize: 14, color: 'var(--muted)', fontFamily: 'var(--serif)', fontStyle: 'italic' }}>
              Inserisci un ticker per iniziare
            </span>
          )}

          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 12 }}>
            {loading && (
              <span style={{ fontSize: 12, color: 'var(--muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
                <Spinner /> Caricamento...
              </span>
            )}
            {fetching && (
              <span style={{ fontSize: 12, color: 'var(--azure)', display: 'flex', alignItems: 'center', gap: 6 }}>
                <Spinner color="var(--azure)" /> Aggiornando news...
              </span>
            )}

            {isPro ? (
              <span style={{
                fontSize: 12, color: '#4ade80',
                border: '1px solid rgba(74,222,128,0.3)',
                borderRadius: 6, padding: '4px 10px',
              }}>
                ✓ Pro
              </span>
            ) : (
              <button
                onClick={handleUpgrade}
                style={{
                  fontSize: 12, color: 'white',
                  background: 'var(--blue)',
                  border: 'none', borderRadius: 6,
                  padding: '4px 12px', cursor: 'pointer',
                  fontWeight: 500,
                }}
              >
                ⚡ Passa a Pro
              </button>
            )}
            
            <button
              onClick={() => supabase.auth.signOut()}
              style={{
                fontSize: 12, color: 'var(--muted)', background: 'transparent',
                border: '1px solid var(--border)', borderRadius: 6, padding: '4px 10px',
                cursor: 'pointer',
              }}
            >
              Esci
            </button>
          </div>
        </header>

        {/* Scroll area */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 24 }}>

          {/* Error */}
          {error && (
            <div style={{
              background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)',
              borderRadius: 10, padding: '12px 16px', fontSize: 14, color: 'var(--red)',
            }}>
              {error}
            </div>
          )}

          {/* KPIs */}
          {stats && <KPIGrid stats={stats} />}

          {/* Empty state */}
          {!loading && !tickerInfo && !error && (
            <EmptyState />
          )}

          {/* No news */}
          {tickerInfo && !loading && !news.length && !error && (
            <div style={{
              background: 'rgba(96,165,250,0.06)', border: '1px solid rgba(96,165,250,0.15)',
              borderRadius: 12, padding: '24px 28px', textAlign: 'center',
            }}>
              <div style={{ fontSize: 15, color: 'var(--azure)', marginBottom: 8 }}>Nessuna news nel database</div>
              <div style={{ fontSize: 13, color: 'var(--muted)' }}>Clicca <b style={{ color: 'var(--white)' }}>Aggiorna news</b> nella sidebar per caricare i dati.</div>
            </div>
          )}

          {/* Chart */}
          {(prices.length > 0 || news.length > 0) && (
            <div style={{
              background: 'rgba(255,255,255,0.02)',
              border: '1px solid var(--border)',
              borderRadius: 12, padding: 20,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
                <div>
                  <div style={{ fontSize: 15, fontWeight: 500, letterSpacing: '-0.01em' }}>
                    {ticker} — Prezzo & Sentiment
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 2 }}>
                    Candlestick OHLCV + Sentiment giornaliero FinBERT
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <Legend color="var(--azure)" label="Prezzo" />
                  <Legend color="var(--green)" label="Positivo" />
                  <Legend color="var(--red)" label="Negativo" />
                </div>
              </div>
              <div style={{ height: 340 }}>
                <Chart prices={prices} sentiment={sentiment} ticker={ticker} />
              </div>
            </div>
          )}

          {/* Top News */}
          {news.length > 0 && <TopNews news={news} />}

          {/* Stats */}
          {news.length > 0 && <Stats news={news} />}

          {/* Bottom padding */}
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

function EmptyState() {
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
        Benvenuto in FinSentinel
      </h2>
      <p style={{ fontSize: 14, color: 'var(--muted)', maxWidth: 400, lineHeight: 1.7 }}>
        Cerca un ticker nella sidebar oppure selezionane uno dalla watchlist per visualizzare sentiment, prezzi e notizie in tempo reale.
      </p>
    </div>
  )
}
