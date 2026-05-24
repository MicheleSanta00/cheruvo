import { useState } from 'react'
import { supabase } from '../supabase'

export default function Auth({ onLogin }) {
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
      const { error } = await supabase.auth.signUp({ email, password })
      if (error) setError(error.message)
      else setMessage('Check your email to confirm your registration!')
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
      }}>
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 28 }}>
          <div style={{
            width: 32, height: 32, background: 'var(--blue)',
            borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M1.5 10.5L5 6.5L8 9L12.5 4" stroke="white" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
              <circle cx="12.5" cy="4" r="1.2" fill="white"/>
            </svg>
          </div>
          <span style={{ fontSize: 15, fontWeight: 500 }}>FinSentinel</span>
        </div>

        <h2 style={{ fontSize: 20, fontWeight: 500, marginBottom: 6, letterSpacing: '-0.02em' }}>
          {isLogin ? 'Sign in' : 'Create account'}
        </h2>
        <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 24 }}>
          {isLogin ? 'Welcome back to FinSentinel' : 'Start for free, no credit card required'}
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <input
            type="email"
            placeholder="Email"
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
            placeholder="Password"
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

        {error && (
          <p style={{ fontSize: 13, color: '#f87171', marginTop: 12 }}>{error}</p>
        )}
        {message && (
          <p style={{ fontSize: 13, color: '#4ade80', marginTop: 12 }}>{message}</p>
        )}

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
          {loading ? 'Loading...' : isLogin ? 'Sign in' : 'Sign up'}
        </button>

        <p style={{ fontSize: 13, color: 'var(--muted)', textAlign: 'center', marginTop: 16 }}>
          {isLogin ? "Don't have an account?" : 'Already have an account?'}{' '}
          <span
            onClick={() => { setIsLogin(!isLogin); setError(''); setMessage('') }}
            style={{ color: 'var(--azure)', cursor: 'pointer' }}
          >
            {isLogin ? 'Sign up' : 'Sign in'}
          </span>
        </p>
      </div>
    </div>
  )
}
