/**
 * apiFetch.js — wrapper fetch con JWT Supabase + auto-refresh on 401.
 *
 * Supabase JS v2: getSession() ritorna il token in cache anche se scaduto.
 * Se il backend risponde 401, questo wrapper forza refreshSession() e riprova
 * una volta prima di fare signOut e mostrare il login.
 */

import { supabase } from './supabase.js'

const BASE = import.meta.env.VITE_API_BASE

async function _getToken() {
  const { data: { session } } = await supabase.auth.getSession()
  return session?.access_token ?? null
}

export default async function apiFetch(path, options = {}, _isRetry = false) {
  const token = await _getToken()

  if (!token) {
    await supabase.auth.signOut()
    throw new Error('Sessione scaduta — effettua nuovamente il login')
  }

  // Con FormData (upload) il Content-Type lo imposta il browser (boundary inclusa)
  const isForm = typeof FormData !== 'undefined' && options.body instanceof FormData

  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      ...(isForm ? {} : { 'Content-Type': 'application/json' }),
      'Authorization': `Bearer ${token}`,
      ...(options.headers || {}),
    },
  })

  // ── 401: token scaduto ── prova a fare refresh e riprova UNA volta
  if (res.status === 401 && !_isRetry) {
    const { data: { session: newSession }, error } = await supabase.auth.refreshSession()

    if (newSession?.access_token) {
      // Retry con il token fresco
      return apiFetch(path, options, true)
    }

    // Refresh fallito (refresh token non valido) — logout e login
    await supabase.auth.signOut()
    throw new Error('Sessione scaduta — effettua nuovamente il login')
  }

  if (res.status === 401) {
    // Secondo 401 dopo refresh: secret sbagliato o token davvero invalido
    await supabase.auth.signOut()
    throw new Error('Sessione scaduta — effettua nuovamente il login')
  }

  if (res.status === 403) {
    // Mostra il motivo vero se il backend lo fornisce (es. "solo docenti"),
    // altrimenti il default storico (paywall PRO)
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || 'Questa funzione richiede un abbonamento PRO')
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Errore ${res.status}`)
  }

  return res.json()
}