/**
 * analytics.js — PostHog wrapper per Cheruvo
 *
 * Uso:
 *   import { initAnalytics, track, identifyUser } from './analytics.js'
 *
 *   initAnalytics()                          // in main.jsx
 *   identifyUser(userId, email, tier)        // dopo il login
 *   track('ticker_searched', { ticker })     // eventi custom
 *
 * La chiave VITE_POSTHOG_KEY va in frontend/.env.production
 * Ottienila su: https://app.posthog.com → Project Settings → Project API Key
 * Formato: phc_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
 */

const POSTHOG_KEY  = import.meta.env.VITE_POSTHOG_KEY  || ''
const POSTHOG_HOST = import.meta.env.VITE_POSTHOG_HOST || 'https://eu.i.posthog.com'

let _ph = null  // istanza PostHog, inizializzata lazy

export function initAnalytics() {
  if (!POSTHOG_KEY || typeof window === 'undefined') return

  // Carica PostHog in modo asincrono (non blocca il bundle principale)
  import('posthog-js').then(({ default: posthog }) => {
    posthog.init(POSTHOG_KEY, {
      api_host:                    POSTHOG_HOST,
      autocapture:                 false,   // solo eventi espliciti, niente click-tracking automatico
      capture_pageview:            true,    // pageview automatico
      capture_pageleave:           true,
      persistence:                 'localStorage',
      disable_session_recording:   true,    // niente screen recording (privacy)
      respect_dnt:                 true,    // rispetta Do Not Track
    })
    _ph = posthog
  }).catch(() => {
    // PostHog non disponibile — silenzioso
  })
}

export function identifyUser(userId, email, tier = 'free') {
  if (!_ph) return
  _ph.identify(userId, { email, tier })
}

export function resetUser() {
  if (!_ph) return
  _ph.reset()
}

export function track(event, props = {}) {
  if (!_ph) return
  _ph.capture(event, props)
}
