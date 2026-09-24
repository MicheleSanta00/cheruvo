import { useState } from 'react'
import { supabase } from '../supabase'
import { useLang } from '../LangContext.jsx'

export default function Auth({ onLogin, onIndietro }) {
  const { lang, t, toggleLang } = useLang()
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [isLogin, setIsLogin]   = useState(true)
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState('')
  const [message, setMessage]   = useState('')

  // PASSWORD DIMENTICATA (24 settembre 2026).
  //
  // Non c'era: chi dimenticava la password restava chiuso fuori per sempre,
  // con i suoi titoli in watchlist e i suoi avvisi, e l'unica via era
  // scrivere a mano all'indirizzo della privacy. Supabase manda l'email con
  // il link; al ritorno App.jsx riceve l'evento PASSWORD_RECOVERY e chiede la
  // password nuova.
  const recupera = async () => {
    setError('')
    setMessage('')
    if (!email.trim()) {
      setError(lang === 'it' ? 'Scrivi prima la tua email.' : 'Type your email first.')
      return
    }
    setLoading(true)
    const { error } = await supabase.auth.resetPasswordForEmail(email.trim(), {
      redirectTo: window.location.origin,
    })
    setLoading(false)
    // Stessa risposta che l'email esista o no: dire "questa email non è
    // registrata" permetterebbe a chiunque di scoprire chi usa Cheruvo.
    if (error && !/rate|limit/i.test(error.message || '')) {
      setError(error.message)
      return
    }
    setMessage(lang === 'it'
      ? 'Se l\'email è registrata, ti arriva un link per scegliere una password nuova.'
      : 'If the email is registered, you will receive a link to choose a new password.')
  }

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
        // L'email di benvenuto non parte più da qui: la chiede App.jsx al
        // primo accesso. Da qui partiva solo se Supabase dava subito una
        // sessione, e con la conferma dell'email attiva non la dà mai.
      }
    }
    setLoading(false)
  }

  return (
    <div style={{
      height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'var(--black)', padding: '16px', position: 'relative', overflow: 'hidden',
    }}>
      {/* Gioco di luce soffuso dietro la card */}
      <div aria-hidden="true" style={{
        position: 'absolute', top: '50%', left: '50%', width: 580, height: 580, borderRadius: '50%', pointerEvents: 'none',
        background: 'radial-gradient(circle, rgba(30,92,255,0.24), rgba(52,211,153,0.10) 45%, transparent 68%)',
        filter: 'blur(30px)', animation: 'authGlow 9s ease-in-out infinite',
      }} />
      <div style={{
        width: '100%', maxWidth: 360, background: 'var(--near-black)',
        border: '1px solid var(--border)', borderRadius: 16, padding: 32,
        position: 'relative', zIndex: 1,
      }}>

        {/* La via d'uscita.
            Da quando l'applicazione si apre anche a chi non ha un account,
            questa schermata non e' piu' il punto di partenza obbligato: ci si
            arriva da dentro, e da dentro si deve poter tornare. Senza questo
            pulsante uno che clicca "Entra" per curiosita' resta chiuso qui e
            l'unica uscita e' il tasto indietro del browser. */}
        {onIndietro && (
          <button onClick={onIndietro} style={{
            background: 'none', border: 'none', color: 'var(--dim)',
            fontSize: 13, cursor: 'pointer', padding: 0, marginBottom: 16,
          }}>
            &larr; {lang === 'en' ? 'Back to Cheruvo' : 'Torna a Cheruvo'}
          </button>
        )}

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
          {/* Stesso cerchio scuro della barra laterale: il bagliore bianco
              che c'era prima sul tema chiaro diventava una macchia grigia
              attorno a un logo già poco visibile. */}
          <span style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: 44, height: 44, borderRadius: '50%', background: '#06070a',
            boxShadow: '0 0 18px rgba(30,92,255,0.35)',
          }}>
            <img src="/logo-v2.png" alt="Cheruvo" style={{ width: 27, height: 27, objectFit: 'contain' }} />
          </span>
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

        {isLogin && (
          <p style={{ fontSize: 12.5, textAlign: 'center', marginTop: 12, marginBottom: 0 }}>
            <span onClick={loading ? undefined : recupera}
              style={{ color: 'var(--muted)', cursor: 'pointer', textDecoration: 'underline' }}>
              {lang === 'it' ? 'Password dimenticata?' : 'Forgot your password?'}
            </span>
          </p>
        )}

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