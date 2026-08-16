/**
 * richiesta.js — Le due decisioni che si prendono attorno a ogni chiamata.
 *
 * Stanno qui, fuori da `apiFetch`, perché sono regole e non impianto: si
 * possono provare senza finto Supabase, senza finta rete e senza browser.
 *
 * Tutte e due nascono dallo stesso giorno, il 16 agosto 2026, quando l'app
 * si è aperta a chi non ha un account. `apiFetch` faceva così:
 *
 *     if (!token) { await supabase.auth.signOut(); throw ... }
 *
 * cioè senza sessione la richiesta non partiva nemmeno. Il server accettava
 * le chiamate anonime e il client si rifiutava di farle: un visitatore vedeva
 * "Sessione scaduta" su ogni schermata invece dei dati.
 */

/**
 * Le intestazioni da mandare.
 *
 * Senza token si parte lo stesso, solo senza `Authorization`: quali endpoint
 * siano aperti lo sa il server, il client non deve indovinarlo.
 */
export function intestazioni ({ token, isForm = false, sessione, extra } = {}) {
  return {
    ...(isForm ? {} : { 'Content-Type': 'application/json' }),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(sessione ? { 'X-Sessione': sessione } : {}),
    ...(extra || {}),
  }
}

/**
 * Che genere di rifiuto è un 401.
 *
 * A chi non era entrato non è scaduto niente: è una porta che chiede
 * l'account. Disconnettere chi non era connesso non ha senso, e il messaggio
 * sbagliato manda l'utente a cercare un problema che non esiste.
 */
export function generedelRifiuto (status, token) {
  if (status !== 401) return null
  return token ? 'sessione-scaduta' : 'serve-account'
}
