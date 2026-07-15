/**
 * CookieBanner.jsx — banner di consenso per gli analytics (GDPR).
 * Compare solo se l'utente non ha ancora scelto. Gli analytics (PostHog)
 * partono SOLO dopo "Accetta" (vedi analytics.js). "Solo necessari" li
 * tiene spenti. La scelta si cambia in ogni momento dal Profilo.
 */
import { useState } from 'react'
import { useLang } from '../LangContext.jsx'
import { getConsent, setConsent } from '../analytics.js'

const TXT = {
  it: {
    body: 'Usiamo solo cookie tecnici e, con il tuo consenso, statistiche anonime per migliorare Cheruvo. Niente pubblicità, niente rivendita dati.',
    more: 'Privacy & Cookie',
    accept: 'Accetta',
    deny: 'Solo necessari',
  },
  en: {
    body: 'We use technical cookies only and, with your consent, anonymous statistics to improve Cheruvo. No ads, no data resale.',
    more: 'Privacy & Cookies',
    accept: 'Accept',
    deny: 'Necessary only',
  },
}

export default function CookieBanner() {
  const { lang } = useLang()
  const [choice, setChoice] = useState(getConsent())
  const s = TXT[lang] || TXT.it

  if (choice) return null

  const decide = (v) => { setConsent(v); setChoice(v) }

  return (
    <div style={{
      position: 'fixed', left: 14, right: 14, bottom: 14, zIndex: 10000,
      maxWidth: 680, margin: '0 auto',
      background: 'rgba(13,17,23,0.98)', border: '1px solid var(--border, #1f2937)',
      borderRadius: 16, padding: '18px 22px',
      display: 'flex', alignItems: 'center', gap: 18, flexWrap: 'wrap',
      boxShadow: '0 12px 44px rgba(0,0,0,0.6)',
    }}>
      <p style={{ margin: 0, flex: '1 1 280px', fontSize: 14, lineHeight: 1.6, color: 'var(--off-white, #c9d1d9)' }}>
        🍪 {s.body}{' '}
        <a href="https://cheruvo.com/privacy.html" target="_blank" rel="noreferrer" style={{ color: 'var(--azure, #60a5fa)' }}>{s.more}</a>
      </p>
      <div style={{ display: 'flex', gap: 10 }}>
        <button onClick={() => decide('denied')} style={{
          fontSize: 13.5, padding: '10px 18px', borderRadius: 9, cursor: 'pointer',
          background: 'transparent', color: 'var(--white, #e6edf3)', border: '1px solid var(--border, #1f2937)',
        }}>{s.deny}</button>
        <button onClick={() => decide('granted')} style={{
          fontSize: 13.5, padding: '10px 20px', borderRadius: 9, cursor: 'pointer', fontWeight: 600,
          background: 'var(--blue, #1e5cff)', color: '#fff', border: 'none',
        }}>{s.accept}</button>
      </div>
    </div>
  )
}
