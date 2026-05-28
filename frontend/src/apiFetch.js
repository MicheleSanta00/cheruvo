/**
 * apiFetch.js — wrapper di fetch che allega automaticamente il JWT Supabase.
 *
 * Uso:
 *   import apiFetch from './apiFetch'
 *   const data = await apiFetch('/api/news/AAPL?days=30')
 */

import { supabase } from './supabase.js'

const BASE = import.meta.env.VITE_API_BASE

export default async function apiFetch(path, options = {}) {
  // Recupera il token corrente dalla sessione Supabase
  const { data: { session } } = await supabase.auth.getSession()
  const token = session?.access_token

  if (!token) {
    throw new Error('Sessione scaduta — effettua nuovamente il login')
  }

  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
      ...(options.headers || {}),
    },
  })

  if (res.status === 401) {
    // Token scaduto — forza il logout per far rifare il login
    await supabase.auth.signOut()
    throw new Error('Sessione scaduta — effettua nuovamente il login')
  }

  if (res.status === 403) {
    throw new Error('Questa funzione richiede un abbonamento PRO')
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Errore ${res.status}`)
  }

  return res.json()
}