// Cheruvo Service Worker — cache-first per asset statici, network-first per API
const CACHE  = 'cheruvo-v2'
const STATIC = ['/']

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(STATIC))
  )
  self.skipWaiting()
})

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  )
  self.clients.claim()
})

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url)

  // API → sempre network (niente cache)
  if (url.hostname.includes('onrender.com') || url.pathname.startsWith('/api')) {
    return
  }

  // Asset statici → cache-first
  e.respondWith(
    caches.match(e.request).then(cached => {
      if (cached) return cached
      return fetch(e.request).then(resp => {
        if (resp.ok && e.request.method === 'GET' && resp.status === 200) {
          const clone = resp.clone()
          caches.open(CACHE).then(c => c.put(e.request, clone))
        }
        return resp
      })
    })
  )
})
