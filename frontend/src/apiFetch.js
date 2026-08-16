/**
 * apiFetch.js — wrapper fetch con JWT Supabase + auto-refresh on 401.
 *
 * Supabase JS v2: getSession() ritorna il token in cache anche se scaduto.
 * Se il backend risponde 401, questo wrapper forza refreshSession() e riprova
 * una volta prima di fare signOut e mostrare il login.
 *
 * IL SERVER CHE DORME
 *
 * Il backend sta sul piano gratuito di Render e si spegne dopo 15 minuti senza
 * richieste. La prima chiamata dopo lo spegnimento non fallisce: resta appesa
 * per circa un minuto mentre l'istanza riparte. Lo stesso succede per qualche
 * secondo a ogni ridistribuzione.
 *
 * Fino al 7 agosto 2026 questo file non aveva né timeout né tentativi ripetuti,
 * quindi in quel minuto l'app restava su "Caricamento dati di mercato..." per
 * sempre e bisognava ricaricare a mano. Chi arriva per la prima volta non sa
 * che deve aspettare, e non torna: vede un sito rotto.
 *
 * Adesso la chiamata ha un tempo massimo, riprova da sola con attese crescenti,
 * e soprattutto AVVISA. `onAttesa` viene chiamata quando il server sta
 * ripartendo, così l'interfaccia può dire "ci vuole un minuto" invece di girare
 * a vuoto. Una pagina che aspetta e lo dice è onesta; una che aspetta in
 * silenzio sembra guasta.
 */

import { supabase } from './supabase.js'
import { intestazioni, generedelRifiuto } from './utils/richiesta.js'

const BASE = import.meta.env.VITE_API_BASE

// Quanto aspettare un singolo tentativo prima di rinunciare.
//
// I tentativi qui dentro sono pochi apposta: chi chiama, per esempio App.jsx,
// ha già una sua sequenza di ritentativi con attese crescenti fino a otto giri.
// Se anche questo file insistesse a lungo, i due si moltiplicherebbero e la
// prima risposta negativa arriverebbe dopo minuti, ritardando proprio il
// messaggio che deve rassicurare l'utente.
//
// La divisione dei compiti è questa: qui si garantisce che una promessa prima
// o poi si CHIUDA, perché era esattamente questo che mancava. Il meccanismo di
// riprova in App.jsx era già scritto e corretto, ma non poteva scattare: senza
// scadenza la fetch restava appesa, il catch non veniva mai raggiunto e la
// pagina mostrava "Caricamento" all'infinito.
const TIMEOUT_MS = 15000
const TENTATIVI = 2
const ATTESE = [2000]

// Dopo quanto tempo si smette di far finta che sia veloce e si dice all'utente
// che il server si sta svegliando. Quattro secondi: abbastanza da non far
// lampeggiare l'avviso su una connessione lenta ma normale, abbastanza poco da
// non lasciare nessuno a fissare uno schermo muto.
const SOGLIA_AVVISO_MS = 4000

// Chi vuole essere avvisato che il server sta ripartendo. L'interfaccia si
// registra qui invece di ricevere una callback per chiamata: il risveglio è
// un fatto globale, non di una singola richiesta.
const ascoltatori = new Set()

export function onServerLento(fn) {
  ascoltatori.add(fn)
  return () => ascoltatori.delete(fn)
}

function avvisa(lento) {
  for (const fn of ascoltatori) {
    try { fn(lento) } catch { /* un ascoltatore rotto non deve fermare gli altri */ }
  }
}

const pausa = (ms) => new Promise((r) => setTimeout(r, ms))

// ── Il gettone di sessione ────────────────────────────────────────────────
//
// Un numero casuale per la singola sessione del browser, mandato al backend
// perché possa contare quante sessioni distinte arrivano in un giorno.
//
// Serve perché PostHog non vede quasi nessuno: non parte senza il consenso ai
// cookie, rispetta il Do Not Track e viene bloccato da ogni ad blocker. Il
// risultato era non avere idea di quanta gente passasse, proprio mentre si
// cercavano i primi utenti.
//
// Sta in `sessionStorage` e non in `localStorage`: muore quando si chiude la
// scheda. È un gettone per il turno, non un braccialetto. Non identifica
// nessuno, non attraversa i giorni, non è ricavato dal dispositivo, e per
// questo non ha bisogno di un consenso: contare quanti sono passati non è
// seguire chi è passato.
const CHIAVE_SESSIONE = 'cheruvo-sessione'

// Chi sviluppa il sito lo apre venti volte al giorno per controllare una cosa,
// e ogni volta finiva nel conteggio. Nelle prime quattordici sessioni raccolte
// una parte era Michele e non c'era modo di sapere quale, quindi il numero non
// rispondeva alla sola domanda per cui esiste: quanti sono venuti che non sono
// io.
//
// L'esclusione NON passa da una variabile d'ambiente. Il repo è pubblico e
// .env.production è tracciato, quindi un indirizzo o un id utente messo lì
// finirebbe in chiaro dentro il JavaScript servito a tutti. Invece si apre una
// volta sola, su ogni browser che si usa per provare:
//
//     app.cheruvo.com/?noncontarmi=1
//
// Da quel momento quel browser non manda più il gettone e sparisce dal
// conteggio. Sta in `localStorage` e non in `sessionStorage` proprio perché
// deve sopravvivere alla chiusura della scheda, al contrario del gettone.
// Si disattiva con ?noncontarmi=0. Vale anche per chi ci aiuta a provare.
const CHIAVE_ESCLUSO = 'cheruvo-non-contarmi'

function escluso() {
  try {
    const scelta = new URLSearchParams(window.location.search).get('noncontarmi')
    if (scelta === '1') {
      localStorage.setItem(CHIAVE_ESCLUSO, '1')
      console.info('Cheruvo: questo browser non viene più conteggiato fra le visite.')
    } else if (scelta === '0') {
      localStorage.removeItem(CHIAVE_ESCLUSO)
      console.info('Cheruvo: questo browser torna nel conteggio delle visite.')
    }
    return localStorage.getItem(CHIAVE_ESCLUSO) === '1'
  } catch {
    return false   // storage negato: si conta, che è il comportamento di prima
  }
}

function gettoneSessione() {
  if (escluso()) return ''
  try {
    let g = sessionStorage.getItem(CHIAVE_SESSIONE)
    if (!g) {
      g = (crypto?.randomUUID?.() ?? String(Math.random()).slice(2) + Date.now())
      sessionStorage.setItem(CHIAVE_SESSIONE, g)
    }
    return g
  } catch {
    return ''   // navigazione privata o storage negato: si rinuncia al conteggio
  }
}

async function _getToken() {
  const { data: { session } } = await supabase.auth.getSession()
  return session?.access_token ?? null
}

/**
 * fetch con tempo massimo, tentativi ripetuti e avviso di risveglio.
 *
 * Riprova SOLO sugli errori di rete e sui 5xx, cioè quando ritentare ha senso.
 * Un 401 o un 404 sono risposte definitive: ripeterle tre volte serve solo a
 * far aspettare l'utente il triplo per lo stesso errore.
 */
async function fetchTenace(url, opzioni) {
  let ultimoErrore
  let timerAvviso

  for (let i = 0; i < TENTATIVI; i++) {
    const stop = new AbortController()
    const scadenza = setTimeout(() => stop.abort(), TIMEOUT_MS)
    // L'avviso parte solo se la PRIMA chiamata è lenta: se il server risponde
    // subito, l'utente non deve vedere lampeggiare un messaggio di attesa.
    timerAvviso = setTimeout(() => avvisa(true), SOGLIA_AVVISO_MS)

    try {
      const res = await fetch(url, { ...opzioni, signal: stop.signal })
      clearTimeout(scadenza)
      clearTimeout(timerAvviso)

      if (res.status >= 500 && i < TENTATIVI - 1) {
        await pausa(ATTESE[i] ?? 3000)
        continue
      }
      avvisa(false)
      return res
    } catch (e) {
      clearTimeout(scadenza)
      clearTimeout(timerAvviso)
      ultimoErrore = e
      if (i < TENTATIVI - 1) {
        await pausa(ATTESE[i] ?? 3000)
        continue
      }
    }
  }

  // NIENTE avvisa(false) qui: se siamo arrivati fin qui il server è davvero
  // lento, e spegnere l'avviso proprio adesso lo farebbe comparire e sparire
  // sotto gli occhi di chi guarda, mentre App.jsx ricomincia i suoi tentativi.
  // L'avviso si spegne in un momento solo, quando una chiamata riesce.
  throw new Error(
    ultimoErrore?.name === 'AbortError'
      ? 'Il server non risponde. Sta probabilmente ripartendo: riprova fra un minuto.'
      : 'Impossibile raggiungere il server. Controlla la connessione e riprova.'
  )
}

export default async function apiFetch(path, options = {}, _isRetry = false) {
  const token = await _getToken()

  // SENZA TOKEN SI CHIEDE LO STESSO.
  //
  // Prima qui c'era `signOut()` e un errore: senza sessione la richiesta non
  // partiva nemmeno. Il 16 agosto 2026, aprendo il backend a chi non ha un
  // account, questa riga rendeva l'apertura inutile: il server accettava le
  // richieste anonime e il client si rifiutava di farle, quindi un visitatore
  // vedeva "Sessione scaduta" su ogni schermata invece dei dati.
  //
  // Le due regole stanno in `utils/richiesta.js` perché lì si possono provare
  // senza finto Supabase e senza finta rete.
  const isForm = typeof FormData !== 'undefined' && options.body instanceof FormData

  const res = await fetchTenace(`${BASE}${path}`, {
    ...options,
    headers: intestazioni({
      token, isForm, sessione: gettoneSessione(), extra: options.headers,
    }),
  })

  if (generedelRifiuto(res.status, token) === 'serve-account') {
    const e = new Error('Per questa funzione serve un account')
    e.serveAccount = true
    throw e
  }

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