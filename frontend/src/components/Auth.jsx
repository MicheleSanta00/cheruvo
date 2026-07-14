import { useState } from 'react'
import { supabase } from '../supabase'
import { useLang } from '../LangContext.jsx'
import apiFetch from '../apiFetch.js'

export default function Auth({ onLogin }) {
  const { lang, t, toggleLang } = useLang()
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [isLogin, setIsLogin]   = useState(true)
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState('')
  const [message, setMessage]   = useState('')

  const handle = async () => {
    setLoading(true)
    setError('')
    setMessage('')

    if (isLogin) {
      const { data, error } = await supabase.auth.signInWithPassword({ email, password })
      if (error) setError(error.message)
      else onLogin(data.user)
    } else {
      const { data, error } = await supabase.auth.signUp({ email, password })
      if (error) {
        setError(error.message)
      } else {
        setMessage(t.auth.confirmEmail)
        // Invia email di benvenuto (giorno 0) — fire and forget, non blocca l'UI
        if (data?.session) {
          apiFetch('/onboarding/welcome', { method: 'POST' }).catch(() => {})
        }
      }
    }
    setLoading(false)
  }

  return (
    <div style={{
      height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'var(--black)', padding: '16px',
    }}>
      <div style={{
        width: '100%', maxWidth: 360, background: 'var(--near-black)',
        border: '1px solid var(--border)', borderRadius: 16, padding: 32,
        position: 'relative',
      }}>

        {/* Switch lingua */}
        <button
          onClick={toggleLang}
          style={{
            position: 'absolute', top: 16, right: 16,
            fontSize: 16, background: 'transparent',
            border: '1px solid var(--border)', borderRadius: 6,
            padding: '4px 8px', cursor: 'pointer', lineHeight: 1,
          }}
          title={lang === 'it' ? 'Switch to English' : "Passa all'italiano"}
        >
          {lang === 'it' ? '🇮🇹' : '🇬🇧'}
        </button>

        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 28 }}>
          <img src="/logo-v2.png" alt="Cheruvo" style={{ width: 32, height: 32, filter: 'brightness(1) drop-shadow(0 0 8px rgba(255,255,255,0.9)) drop-shadow(0 0 16px rgba(255,255,255,0.4))' }} />
          <span style={{ fontSize: 15, fontWeight: 500 }}>Cheruvo</span>
        </div>

        <h2 style={{ fontSize: 20, fontWeight: 500, marginBottom: 6, letterSpacing: '-0.02em' }}>
          {isLogin ? t.auth.login : t.auth.register}
        </h2>
        <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 24 }}>
          {isLogin ? t.auth.welcome : t.auth.noCard}
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <input
            type="email"
            placeholder={t.auth.email}
            value={email}
            onChange={e => setEmail(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handle()}
            style={{
              background: 'var(--dark)', border: '1px solid var(--border)',
              color: 'var(--white)', borderRadius: 8, padding: '10px 14px',
              fontSize: 14, outline: 'none', fontFamily: 'var(--sans)',
            }}
          />
          <input
            type="password"
            placeholder={t.auth.password}
            value={password}
            onChange={e => setPassword(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handle()}
            style={{
              background: 'var(--dark)', border: '1px solid var(--border)',
              color: 'var(--white)', borderRadius: 8, padding: '10px 14px',
              fontSize: 14, outline: 'none', fontFamily: 'var(--sans)',
            }}
          />
        </div>

        {error && <p style={{ fontSize: 13, color: '#f87171', marginTop: 12 }}>{error}</p>}
        {message && <p style={{ fontSize: 13, color: '#4ade80', marginTop: 12 }}>{message}</p>}

        <button
          onClick={handle}
          disabled={loading}
          style={{
            width: '100%', background: 'var(--blue)', color: 'white',
            borderRadius: 8, padding: '11px 0', fontSize: 14, fontWeight: 500,
            marginTop: 20, opacity: loading ? 0.6 : 1, transition: 'opacity .2s',
            cursor: loading ? 'default' : 'pointer',
          }}
        >
          {loading ? t.auth.loading : isLogin ? t.auth.login : t.auth.register}
        </button>

        <p style={{ fontSize: 13, color: 'var(--muted)', textAlign: 'center', marginTop: 16 }}>
          {isLogin ? t.auth.noAccount : t.auth.hasAccount}{' '}
          <span
            onClick={() => { setIsLogin(!isLogin); setError(''); setMessage('') }}
            style={{ color: 'var(--azure)', cursor: 'pointer' }}
          >
            {isLogin ? t.auth.register : t.auth.login}
          </span>
        </p>

        <p style={{ fontSize: 11, color: 'var(--muted)', textAlign: 'center', marginTop: 12, lineHeight: 1.6 }}>
          {lang === 'it' ? (
            <>Continuando accetti i <a href="https://cheruvo.com/termini.html" target="_blank" rel="noreferrer" style={{ color: 'var(--azure)' }}>Termini di Servizio</a> e la <a href="https://cheruvo.com/privacy.html" target="_blank" rel="noreferrer" style={{ color: 'var(--azure)' }}>Privacy Policy</a>.</>
          ) : (
            <>By continuing you accept the <a href="https://cheruvo.com/termini.html" target="_blank" rel="noreferrer" style={{ color: 'var(--azure)' }}>Terms of Service</a> and the <a href="https://cheruvo.com/privacy.html" target="_blank" rel="noreferrer" style={{ color: 'var(--azure)' }}>Privacy Policy</a>.</>
          )}
        </p>
      </div>
    </div>
  )
}