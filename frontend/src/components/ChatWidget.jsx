import { useState, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'
import apiFetch from '../apiFetch.js'

const SUGGESTED = [
  'Cosa significa il sentiment score?',
  'Cos\'è un\'azione bearish?',
  'Come si legge il grafico?',
  'Cosa significa +0.4 di sentiment?',
]

export default function ChatWidget({ ticker, sentimentScore, topNews }) {
  const [open, setOpen]       = useState(false)
  const [messages, setMessages] = useState([
    { role: 'assistant', text: `Ciao! 👋 Sono il tuo assistente finanziario. Posso spiegarti i dati che vedi, rispondere a domande sui mercati o aiutarti a capire il sentiment${ticker ? ` di ${ticker}` : ''}. Come posso aiutarti?` }
  ])
  const [input, setInput]     = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef             = useRef(null)
  const inputRef              = useRef(null)

  useEffect(() => {
    if (open) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [open, messages])

  const send = async (text) => {
    const msg = text || input.trim()
    if (!msg || loading) return
    setInput('')
    setMessages(prev => [...prev, { role: 'user', text: msg }])
    setLoading(true)

    try {
      const data = await apiFetch('/chat', {
        method: 'POST',
        body: JSON.stringify({
          message: msg,
          ticker: ticker || null,
          sentiment_score: sentimentScore || null,
          top_news: topNews?.slice(0, 3).map(n => n.title) || null,
        }),
      })
      setMessages(prev => [...prev, { role: 'assistant', text: data.reply }])
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', text: 'Mi dispiace, si è verificato un errore. Riprova tra poco.' }])
    } finally {
      setLoading(false)
    }
  }

  return createPortal(
    <>
      {/* Chat panel */}
      {open && (
        <div style={{
          position: 'fixed', bottom: 88, right: 24, zIndex: 1000,
          width: 360, height: 520,
          background: '#0a0d14',
          border: '1px solid rgba(30,92,255,0.3)',
          borderRadius: 18,
          display: 'flex', flexDirection: 'column',
          boxShadow: '0 24px 60px rgba(0,0,0,0.6), 0 0 0 1px rgba(30,92,255,0.1)',
          overflow: 'hidden',
          animation: 'chatOpen .2s ease',
        }}>
          <style>{`
            @keyframes chatOpen { from { opacity:0; transform: translateY(12px) scale(.97); } to { opacity:1; transform: none; } }
            .chat-msg { line-height: 1.65; font-size: 13px; }
            .chat-input:focus { outline: none; border-color: rgba(30,92,255,0.5) !important; }
            .chat-send:hover { opacity: .85; }
            .suggest-btn:hover { background: rgba(30,92,255,0.12) !important; border-color: rgba(30,92,255,0.3) !important; }
          `}</style>

          {/* Header */}
          <div style={{
            padding: '14px 16px', borderBottom: '1px solid rgba(255,255,255,0.06)',
            display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0,
            background: 'rgba(30,92,255,0.06)',
          }}>
            <div style={{
              width: 32, height: 32, borderRadius: 10,
              background: 'var(--blue)', display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 16,
            }}>🧠</div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600 }}>Assistente Cheruvo</div>
              <div style={{ fontSize: 11, color: 'var(--muted)' }}>Powered by Llama 3 · Groq</div>
            </div>
            <button
              onClick={() => setOpen(false)}
              style={{ marginLeft: 'auto', background: 'transparent', color: 'var(--muted)', fontSize: 18, border: 'none', cursor: 'pointer', lineHeight: 1, padding: '2px 6px' }}
            >✕</button>
          </div>

          {/* Messages */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '14px 14px 8px', display: 'flex', flexDirection: 'column', gap: 10 }}>
            {messages.map((m, i) => (
              <div key={i} style={{
                display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start',
              }}>
                <div className="chat-msg" style={{
                  maxWidth: '85%',
                  padding: '10px 13px',
                  borderRadius: m.role === 'user' ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
                  background: m.role === 'user' ? 'var(--blue)' : 'rgba(255,255,255,0.06)',
                  color: m.role === 'user' ? 'white' : 'var(--off-white)',
                  border: m.role === 'assistant' ? '1px solid rgba(255,255,255,0.06)' : 'none',
                }}>
                  {m.text}
                </div>
              </div>
            ))}

            {/* Typing indicator */}
            {loading && (
              <div style={{ display: 'flex', gap: 4, padding: '10px 13px', background: 'rgba(255,255,255,0.06)', borderRadius: '14px 14px 14px 4px', width: 'fit-content', border: '1px solid rgba(255,255,255,0.06)' }}>
                {[0,1,2].map(i => (
                  <div key={i} style={{
                    width: 6, height: 6, borderRadius: '50%', background: 'var(--muted)',
                    animation: `bounce .8s ${i * .15}s infinite`,
                  }}/>
                ))}
                <style>{`@keyframes bounce { 0%,80%,100%{transform:translateY(0)} 40%{transform:translateY(-5px)} }`}</style>
              </div>
            )}

            {/* Suggerimenti iniziali */}
            {messages.length === 1 && !loading && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
                {SUGGESTED.map((s, i) => (
                  <button
                    key={i}
                    className="suggest-btn"
                    onClick={() => send(s)}
                    style={{
                      fontSize: 11, padding: '5px 10px', borderRadius: 100,
                      background: 'rgba(30,92,255,0.06)',
                      border: '1px solid rgba(30,92,255,0.2)',
                      color: 'var(--azure)', cursor: 'pointer',
                      transition: 'background .15s, border-color .15s',
                    }}
                  >{s}</button>
                ))}
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div style={{
            padding: '10px 12px', borderTop: '1px solid rgba(255,255,255,0.06)',
            display: 'flex', gap: 8, flexShrink: 0,
            background: 'rgba(0,0,0,0.3)',
          }}>
            <input
              ref={inputRef}
              className="chat-input"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !e.shiftKey && send()}
              placeholder="Scrivi una domanda..."
              disabled={loading}
              style={{
                flex: 1, background: 'rgba(255,255,255,0.05)',
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: 10, padding: '9px 12px',
                fontSize: 13, color: 'var(--white)',
                fontFamily: 'var(--sans)',
                transition: 'border-color .2s',
              }}
            />
            <button
              className="chat-send"
              onClick={() => send()}
              disabled={loading || !input.trim()}
              style={{
                background: input.trim() ? 'var(--blue)' : 'rgba(255,255,255,0.06)',
                color: 'white', border: 'none', borderRadius: 10,
                padding: '0 14px', fontSize: 16, cursor: input.trim() ? 'pointer' : 'default',
                transition: 'background .2s',
                flexShrink: 0,
              }}
            >↑</button>
          </div>
        </div>
      )}

      {/* Floating button */}
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          position: 'fixed', bottom: 24, right: 24, zIndex: 1000,
          width: 56, height: 56, borderRadius: '50%',
          background: open ? 'rgba(30,92,255,0.8)' : 'var(--blue)',
          border: 'none', cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: '0 4px 24px rgba(30,92,255,0.5)',
          fontSize: 22, transition: 'transform .2s, background .2s',
          transform: open ? 'rotate(0deg)' : 'scale(1)',
        }}
        title="Assistente AI"
        onMouseEnter={e => e.currentTarget.style.transform = 'scale(1.1)'}
        onMouseLeave={e => e.currentTarget.style.transform = 'scale(1)'}
      >
        {open ? '✕' : '🧠'}
      </button>
    </>,
    document.body
  )
}
