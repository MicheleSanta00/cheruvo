// Cheruvo Service Worker v3
//
// Strategia pensata per NON servire mai versioni vecchie dell'app:
//   - navigazioni (index.html)  → network-first (fallback cache solo offline)
//   - /assets/* di Vite (hash nel nome, immutabili) → cache-first
//   - altri GET same-origin (icone, manifest)       → stale-while-revalidate
//   - API e cross-origin → passthrough, mai in cache
//
// La v2 era cache-first anche su index.html: dopo ogni deploy gli utenti
// restavano sulla versione precedente finché non facevano hard-refresh.
const CACHE = 'cheruvo-v3'

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(['/'])))
  self.skipWaiting()
})

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  )
  self.clients.claim()
})

self.addEventListener('fetch', (e) => {
  const req = e.request
  if (req.method !== 'GET') return

  const url = new URL(req.url)

  // API e domini esterni: sempre rete, mai cache
  if (url.origin !== self.location.origin || url.pathname.startsWith('/api')) return

  // Navigazioni: network-first, la cache serve solo da fallback offline
  if (req.mode === 'navigate') {
    e.respondWith(
      fetch(req)
        .then((resp) => {
          const clone = resp.clone()
          caches.open(CACHE).then((c) => c.put('/', clone))
          return resp
        })
        .catch(() => caches.match('/'))
    )
    return
  }

  // Bundle Vite con hash nel nome: immutabili → cache-first
  if (url.pathname.startsWith('/assets/')) {
    e.respondWith(
      caches.match(req).then((cached) => {
        if (cached) return cached
        return fetch(req).then((resp) => {
          if (resp.ok) {
            const clone = resp.clone()
            caches.open(CACHE).then((c) => c.put(req, clone))
          }
          return resp
        })
      })
    )
    return
  }

  // Icone, manifest, immagini: stale-while-revalidate
  e.respondWith(
    caches.match(req).then((cached) => {
      const fresh = fetch(req)
        .then((resp) => {
          if (resp.ok) {
            const clone = resp.clone()
            caches.open(CACHE).then((c) => c.put(req, clone))
          }
          return resp
        })
        .catch(() => cached)
      return cached || fresh
    })
  )
})
