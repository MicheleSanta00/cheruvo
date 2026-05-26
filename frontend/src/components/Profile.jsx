import { useState, useEffect } from 'react'
import { supabase } from '../supabase.js'
import { useLang } from '../LangContext.jsx'

export default function Profile({ user, isPro, onClose, onUpgrade }) {
  const { t, lang } = useLang()
  const [createdAt, setCreatedAt] = useState('')

  useEffect(() => {
    if (user?.created_at) {
      setCreatedAt(new Date(user.created_at).toLocaleDateString(
        lang === 'it' ? 'it-IT' : 'en-US',
        { day: '2-digit', month: 'long', year: 'numeric' }
      ))
    }
  }, [user, lang])

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: '16px',
    }} onClick={onClose}>
      <div
        onClick={e => e.stopPropagation()}
        style={{
          width: '100%', maxWidth: 420, background: 'var(--near-black)',
          border: '1px solid var(--border)', borderRadius: 16,
          padding: 32, position: 'relative',
        }}
      >
        <button
          onClick={onClose}
          style={{
            position: 'absolute', top: 16, right: 16,
            background: 'transparent', color: 'var(--muted)',
            fontSize: 18, border: 'none', cursor: 'pointer',
          }}
        >✕</button>

        <div style={{
          width: 56, height: 56, borderRadius: '50%',
          background: 'var(--blue)', display: 'flex',
          alignItems: 'center', justifyContent: 'center',
          fontSize: 22, fontWeight: 500, marginBottom: 16,
        }}>
          {user?.email?.[0].toUpperCase()}
        </div>

        <h2 style={{ fontSize: 18, fontWeight: 500, margin: '0 0 4px', letterSpacing: '-0.01em' }}>
          {t.profile.title}
        </h2>
        <p style={{ fontSize: 13, color: 'var(--muted)', margin: '0 0 28px' }}>
          {t.profile.subtitle}
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 28 }}>
          <Row label={t.profile.email} value={user?.email} />
          <Row label={t.profile.joinedAt} value={createdAt} />
          <Row
            label={t.profile.plan}
            value={
              <span style={{
                fontSize: 12, padding: '3px 10px', borderRadius: 6,
                background: isPro ? 'rgba(74,222,128,0.1)' : 'rgba(255,255,255,0.05)',
                border: `1px solid ${isPro ? 'rgba(74,222,128,0.3)' : 'var(--border)'}`,
                color: isPro ? '#4ade80' : 'var(--muted)',
              }}>
                {isPro ? t.profile.planPro : t.profile.planFree}
              </span>
            }
          />
        </div>

        {!isPro && (
          <button
            onClick={onUpgrade}
            style={{
              width: '100%', background: 'var(--blue)', color: 'white',
              borderRadius: 8, padding: '11px 0', fontSize: 14,
              fontWeight: 500, marginBottom: 12, cursor: 'pointer',
            }}
          >
            {t.profile.upgradePro}
          </button>
        )}

        <a
          href="https://appcheruvo.vercel.app"
          style={{
            display: 'block', width: '100%', textAlign: 'center',
            background: 'transparent', color: 'var(--muted)',
            border: '1px solid var(--border)', borderRadius: 8,
            padding: '10px 0', fontSize: 13, textDecoration: 'none',
            marginBottom: 8,
          }}
        >
          {t.profile.homepage}
        </a>

        <button
          onClick={() => supabase.auth.signOut()}
          style={{
            width: '100%', background: 'transparent', color: 'var(--muted)',
            border: '1px solid var(--border)', borderRadius: 8,
            padding: '10px 0', fontSize: 13, cursor: 'pointer',
          }}
        >
          {t.profile.logout}
        </button>
      </div>
    </div>
  )
}

function Row({ label, value }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      padding: '10px 14px', background: 'var(--dark)',
      borderRadius: 8, border: '1px solid var(--border)',
    }}>
      <span style={{ fontSize: 13, color: 'var(--muted)' }}>{label}</span>
      <span style={{ fontSize: 13, color: 'var(--white)' }}>{value}</span>
    </div>
  )
}