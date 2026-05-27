import { useEffect, useState } from 'react'
import { supabase } from '../supabase.js'

const BASE = import.meta.env.VITE_API_BASE || 'https://financial-sentiment-analysis-20px.onrender.com/api'

const COLORI = {
  bullish: { accent: '#34d399', bg: 'rgba(52,211,153,0.08)', border: 'rgba(52,211,153,0.2)', badge: '#34d399', emoji: '📈' },
  bearish: { accent: '#f87171', bg: 'rgba(248,113,113,0.08)', border: 'rgba(248,113,113,0.2)', badge: '#f87171', emoji: '📉' },
  neutro:  { accent: '#8a94a6', bg: 'rgba(138,148,166,0.06)', border: 'rgba(138,148,166,0.15)', badge: '#8a94a6', emoji: '➡️' },
}

export default function SummaryCard({ ticker, isPro, onUpgrade }) {
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState(null)

  useEffect(() => {
    if (!ticker) return
    setData(null)
    setError(null)
    setLoading(true)

    // Recupera il token Supabase prima di chiamare l'API
    supabase.auth.getSession().then(({ data: sessionData }) => {
      const token = sessionData?.session?.access_token
      if (!token) {
        setError(true)
        setLoading(false)
        return
      }
      fetch(`${BASE}/summary/${ticker}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
        .then(r => {
          if (r.status === 401) throw new Error('auth')
          if (!r.ok) throw new Error('fetch')
          return r.json()
        })
        .then(d => setData(d))
        .catch(() => setError(true))
        .finally(() => setLoading(false))
    })
  }, [ticker])

  if (loading) return (
    <div style={card()}>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <div style={sk(90, 20)} /><div style={sk(60, 20)} />
      </div>
      <div style={sk('100%', 13, 0)} />
      <div style={sk('85%',  13, 6)} />
      <div style={sk('70%',  13, 6)} />
    </div>
  )

  if (error || !data) return (
    <div style={card()}>
      <p style={{ fontSize: 12, color: 'var(--muted)', lineHeight: 1.6 }}>
        ℹ️ Nessun summary disponibile — carica prima le news con il pulsante Aggiorna.
      </p>
    </div>
  )

  // Il backend ora gestisce il gate PRO:
  // - se locked=true nel response → l'utente è FREE (1 sola frase)
  // - se locked=false/assente → l'utente è PRO (testo completo)
  const isLocked = data.locked === true

  const c = COLORI[data.giudizio] || COLORI.neutro
  const frasi = data.riassunto?.split('.').filter(f => f.trim().length > 5) || []

  return (
    <div style={{ ...card(), background: c.bg, borderColor: c.border }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
        <span style={{
          fontSize: 10, fontWeight: 700, letterSpacing: '0.08em',
          color: '#a78bfa', background: 'rgba(167,139,250,0.12)',
          padding: '3px 9px', borderRadius: 100,
          border: '1px solid rgba(167,139,250,0.25)',
          textTransform: 'uppercase',
        }}>✨ AI Summary</span>

        <span style={{
          fontSize: 10, fontWeight: 700, letterSpacing: '0.06em',
          color: c.badge, background: 'rgba(0,0,0,0.2)',
          padding: '3px 9px', borderRadius: 100,
          border: `1px solid ${c.border}`,
          textTransform: 'uppercase',
        }}>
          {c.emoji} {data.giudizio}
        </span>

        <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--muted)' }}>
          {data.news_analizzate} news
        </span>
      </div>

      {/* Linea colorata */}
      <div style={{ height: 2, background: c.accent, borderRadius: 2, marginBottom: 14, opacity: 0.5 }} />

      {/* Testo riassunto */}
      <div style={{ position: 'relative' }}>
        {frasi.map((frase, i) => (
          <p key={i} style={{
            fontSize: 12, lineHeight: 1.75,
            color: 'var(--off-white)',
            margin: '0 0 6px 0',
          }}>
            {frase.trim()}.
          </p>
        ))}

        {/* Banner upgrade solo se il backend ha restituito locked=true */}
        {isLocked && (
          <div style={{
            marginTop: 10,
            background: 'rgba(0,0,0,0.15)',
            borderRadius: 8,
            padding: '10px 12px',
            textAlign: 'center',
          }}>
            <button onClick={onUpgrade} style={{
              fontSize: 11, color: '#a78bfa', fontWeight: 600,
              padding: '5px 14px', background: 'rgba(167,139,250,0.12)',
              borderRadius: 100, border: '1px solid rgba(167,139,250,0.25)',
              cursor: 'pointer',
            }}>
              🔒 Passa a PRO per il riassunto completo
            </button>
          </div>
        )}
      </div>

      {/* Temi — visibili solo se non locked */}
      {!isLocked && data.temi?.length > 0 && (
        <div className="summary-temi" style={{ display: 'flex', gap: 6, marginTop: 14, flexWrap: 'wrap' }}>
          {data.temi.map((tema, i) => (
            <span key={i} style={{
              fontSize: 11, fontWeight: 500, color: c.badge,
              background: 'rgba(0,0,0,0.2)', padding: '3px 10px',
              borderRadius: 100, border: `1px solid ${c.border}`,
            }}>{tema}</span>
          ))}
        </div>
      )}

      <p style={{ fontSize: 10, color: 'var(--muted)', marginTop: 12, marginBottom: 0 }}>
        Llama 3 · aggiornato ogni 6h
      </p>
    </div>
  )
}

function card() {
  return {
    background: 'rgba(255,255,255,0.03)',
    border: '1px solid var(--border)',
    borderRadius: 10, padding: '14px 16px',
  }
}

function sk(w, h, mt = 0) {
  return {
    width: w, height: h, borderRadius: 4, display: 'block', marginTop: mt,
    background: 'linear-gradient(90deg,rgba(255,255,255,0.05) 25%,rgba(255,255,255,0.1) 50%,rgba(255,255,255,0.05) 75%)',
    backgroundSize: '200% 100%', animation: 'shimmer 1.5s infinite',
  }
}