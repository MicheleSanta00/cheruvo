import { useState, useEffect } from 'react'
import { supabase } from '../supabase.js'

export default function Profile({ user, isPro, onClose, onUpgrade }) {
  const [createdAt, setCreatedAt] = useState('')

  useEffect(() => {
    if (user?.created_at) {
      setCreatedAt(new Date(user.created_at).toLocaleDateString('en-US', {
        day: '2-digit', month: 'long', year: 'numeric'
      }))
    }
  }, [user])

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
          Your profile
        </h2>
        <p style={{ fontSize: 13, color: 'var(--muted)', margin: '0 0 28px' }}>
          Manage your FinSentinel account
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 28 }}>
          <Row label="Email" value={user?.email} />
          <Row label="Member since" value={createdAt} />
          <Row
            label="Plan"
            value={
              <span style={{
                fontSize: 12, padding: '3px 10px', borderRadius: 6,
                background: isPro ? 'rgba(74,222,128,0.1)' : 'rgba(255,255,255,0.05)',
                border: `1px solid ${isPro ? 'rgba(74,222,128,0.3)' : 'var(--border)'}`,
                color: isPro ? '#4ade80' : 'var(--muted)',
              }}>
                {isPro ? '✓ Pro' : 'Free'}
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
            ⚡ Upgrade to Pro — €9/month
          </button>
        )}

        <button
          onClick={() => supabase.auth.signOut()}
          style={{
            width: '100%', background: 'transparent', color: 'var(--muted)',
            border: '1px solid var(--border)', borderRadius: 8,
            padding: '10px 0', fontSize: 13, cursor: 'pointer',
          }}
        >
          Sign out
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
