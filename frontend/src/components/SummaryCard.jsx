import { useEffect, useState } from 'react'
import { useLang } from '../LangContext.jsx'

const BASE = import.meta.env.VITE_API_BASE || 'https://financial-sentiment-analysis-20px.onrender.com/api'

const COLORI = {
  bullish: { bg: '#f0fdf4', border: '#86efac', testo: '#15803d', emoji: '📈' },
  bearish: { bg: '#fff1f2', border: '#fca5a5', testo: '#b91c1c', emoji: '📉' },
  neutro:  { bg: '#f8fafc', border: '#cbd5e1', testo: '#475569', emoji: '➡️' },
}

export default function SummaryCard({ ticker, isPro }) {
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState(null)
  const { lang }              = useLang()

  useEffect(() => {
    if (!ticker) return
    setData(null)
    setError(null)
    setLoading(true)

    fetch(`${BASE}/summary/${ticker}`)
      .then(r => {
        if (!r.ok) throw new Error('no data')
        return r.json()
      })
      .then(d => setData(d))
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [ticker])

  // ── Skeleton loading ────────────────────────────────────────────────────
  if (loading) return (
    <div style={cardStyle('#f8fafc', '#e2e8f0')}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <div style={skeleton(100, 22)} />
        <div style={skeleton(60, 22)} />
      </div>
      <div style={skeleton('100%', 14, 8)} />
      <div style={skeleton('90%', 14, 6)} />
      <div style={skeleton('75%', 14, 6)} />
      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        {[1,2,3].map(i => <div key={i} style={skeleton(70, 26)} />)}
      </div>
    </div>
  )

  if (error || !data) return null

  const colori = COLORI[data.giudizio] || COLORI.neutro
  const frasi  = data.riassunto?.split('.').filter(f => f.trim().length > 5) || []

  return (
    <div style={cardStyle(colori.bg, colori.border)}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <span style={{
          fontSize: 11, fontWeight: 600, letterSpacing: '0.05em',
          color: '#7c3aed', background: '#f3e8ff',
          padding: '3px 10px', borderRadius: 100,
          border: '1px solid #c4b5fd',
        }}>✨ AI Summary</span>

        <span style={{
          fontSize: 11, fontWeight: 600,
          color: colori.testo, background: colori.bg,
          padding: '3px 10px', borderRadius: 100,
          border: `1px solid ${colori.border}`,
          textTransform: 'uppercase',
        }}>
          {colori.emoji} {data.giudizio}
        </span>

        <span style={{ marginLeft: 'auto', fontSize: 11, color: '#94a3b8' }}>
          {data.news_analizzate} news analizzate
        </span>
      </div>

      {/* Riassunto — FREE vede solo prima frase */}
      <div style={{ position: 'relative' }}>
        {frasi.map((frase, i) => {
          const visibile = isPro || i === 0
          return (
            <p key={i} style={{
              fontSize: 13,
              lineHeight: 1.7,
              color: visibile ? '#334155' : '#94a3b8',
              margin: '0 0 4px 0',
              filter: visibile ? 'none' : 'blur(4px)',
              userSelect: visibile ? 'auto' : 'none',
              transition: 'filter 0.2s',
            }}>
              {frase.trim()}.
            </p>
          )
        })}

        {/* Overlay upgrade per FREE */}
        {!isPro && (
          <div style={{
            position: 'absolute', bottom: 0, left: 0, right: 0,
            background: 'linear-gradient(to bottom, transparent, white 80%)',
            padding: '32px 0 8px',
            textAlign: 'center',
          }}>
            <span style={{
              fontSize: 12, color: '#7c3aed', fontWeight: 500,
              cursor: 'pointer',
              padding: '6px 16px',
              background: '#f3e8ff',
              borderRadius: 100,
              border: '1px solid #c4b5fd',
            }}>
              🔒 Passa a PRO per il riassunto completo
            </span>
          </div>
        )}
      </div>

      {/* Temi */}
      {isPro && data.temi?.length > 0 && (
        <div className="summary-temi" style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
          {data.temi.map((tema, i) => (
            <span key={i} style={{
              fontSize: 12, fontWeight: 500,
              color: colori.testo,
              background: 'white',
              padding: '4px 12px',
              borderRadius: 100,
              border: `1px solid ${colori.border}`,
            }}>
              {tema}
            </span>
          ))}
        </div>
      )}

      {/* Footer */}
      <p style={{ fontSize: 11, color: '#94a3b8', marginTop: 10, marginBottom: 0 }}>
        Generato da Llama 3 · aggiornato ogni 6 ore
      </p>
    </div>
  )
}

// ── Helpers ─────────────────────────────────────────────────────────────────
function cardStyle(bg, border) {
  return {
    background: bg,
    border: `1px solid ${border}`,
    borderRadius: 12,
    padding: '16px 20px',
    marginBottom: 16,
  }
}

function skeleton(w, h, mt = 0) {
  return {
    width: w, height: h, borderRadius: 6,
    background: 'linear-gradient(90deg, #e2e8f0 25%, #f1f5f9 50%, #e2e8f0 75%)',
    backgroundSize: '200% 100%',
    animation: 'shimmer 1.5s infinite',
    marginTop: mt,
    display: 'inline-block',
  }
}