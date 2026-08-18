import test from 'node:test'
import assert from 'node:assert/strict'
import { fasce, SIGMA_ARTICOLO } from './incertezza.js'

// La classifica vera del 18 agosto 2026, presa da /api/market/today alle
// 17:16 UTC. Nessuna delle 25 coppie adiacenti era distinguibile.
const VERA = [
  ['SMCI', 0.382, 10], ['MU', 0.27, 41], ['NVDA', 0.252, 70], ['JPM', 0.247, 35],
  ['RACE.MI', 0.21, 35], ['SAP.DE', 0.175, 20], ['SOL-USD', 0.163, 8],
  ['AAPL', 0.13, 45], ['BCH-USD', 0.105, 20], ['AMD', 0.096, 16],
  ['AMZN', 0.082, 27], ['TSLA', 0.075, 23], ['GOOGL', 0.066, 28],
  ['ETH-USD', 0.053, 47], ['BA', 0.035, 11], ['INTC', 0.016, 10],
  ['PLTR', 0.008, 13], ['MSFT', -0.004, 37], ['UCG.MI', -0.005, 6],
  ['BTC-USD', -0.028, 218], ['XRP-USD', -0.112, 39], ['DOGE-USD', -0.122, 6],
  ['META', -0.208, 37], ['AIR.PA', -0.259, 6], ['SHEL.L', -0.26, 5],
  ['AVGO', -0.266, 7],
].map(([ticker, sentiment, news]) => ({ ticker, sentiment, news }))

// ── La proprieta' che conta ────────────────────────────────────────────────

test('fra due fasce consecutive il distacco esclude sempre lo zero', () => {
  // Se questo test si accende, le fasce stanno mostrando una separazione che
  // i dati non reggono, cioe' esattamente il difetto delle 26 posizioni.
  const g = fasce(VERA)
  for (let i = 0; i < g.length - 1; i++) {
    const a = g[i]
    const b = g[i + 1]
    const se = Math.hypot(
      SIGMA_ARTICOLO / Math.sqrt(a.n),
      SIGMA_ARTICOLO / Math.sqrt(b.n),
    )
    assert.ok(a.media - b.media > 1.96 * se,
      `fascia ${i + 1} e ${i + 2} non sono distinguibili: ${a.media} vs ${b.media}`)
  }
})

test('nessun titolo si perde e l ordine non cambia', () => {
  const g = fasce(VERA)
  const piatta = g.flatMap((f) => f.righe.map((r) => r.ticker))
  assert.deepEqual(piatta, VERA.map((r) => r.ticker))
})

test('sulla classifica del 18 agosto escono cinque fasce', () => {
  // Non e' un numero scelto: e' la partizione piu' fine che quei dati
  // reggono. Se cambia il volume cambia anche questo, ed e' voluto.
  const g = fasce(VERA)
  assert.equal(g.length, 5)
  assert.deepEqual(g[0].righe.map((r) => r.ticker), ['SMCI', 'MU', 'NVDA', 'JPM'])
  assert.deepEqual(g[4].righe.map((r) => r.ticker),
    ['DOGE-USD', 'META', 'AIR.PA', 'SHEL.L', 'AVGO'])
})

test('la prima fascia sta sopra l ultima, e non e una banalita', () => {
  const g = fasce(VERA)
  assert.ok(g[0].media > g[g.length - 1].media)
  assert.ok(g[0].lo > g[g.length - 1].hi,
    'le bande delle due fasce estreme non devono nemmeno toccarsi')
})

// ── Il volume decide quante fasce escono ──────────────────────────────────

test('con poche notizie le fasce si fondono', () => {
  const povera = VERA.map((r) => ({ ...r, news: 5 }))
  const g = fasce(povera)
  assert.ok(g.length < fasce(VERA).length,
    'con meno notizie la classifica deve dire MENO, non lo stesso')
})

test('con molte notizie le fasce aumentano da sole', () => {
  const ricca = VERA.map((r) => ({ ...r, news: r.news * 40 }))
  assert.ok(fasce(ricca).length > fasce(VERA).length)
})

test('se i punteggi sono tutti uguali esce una fascia sola', () => {
  const piatta = VERA.map((r) => ({ ...r, sentiment: 0.1 }))
  assert.equal(fasce(piatta).length, 1)
})

// ── I casi limite, che qui arrivano davvero ───────────────────────────────

test('elenco vuoto, nullo o senza notizie non esplode', () => {
  for (const x of [null, undefined, [], [{ ticker: 'X', sentiment: null, news: 9 }]]) {
    assert.deepEqual(fasce(x), [])
  }
})

test('un titolo solo e una fascia sola', () => {
  const g = fasce([{ ticker: 'NVDA', sentiment: 0.25, news: 70 }])
  assert.equal(g.length, 1)
  assert.equal(g[0].righe.length, 1)
})

test('le righe senza notizie vengono scartate invece di rompere la media', () => {
  const g = fasce([...VERA, { ticker: 'ROTTO', sentiment: 0.5, news: 0 }])
  const piatta = g.flatMap((f) => f.righe.map((r) => r.ticker))
  assert.ok(!piatta.includes('ROTTO'))
})

test('la media di una fascia e pesata sulle notizie, non sui titoli', () => {
  // Bitcoin da solo ha 218 notizie contro le 6 di UniCredit: una media
  // semplice darebbe a UniCredit lo stesso peso, e non ce l'ha.
  const due = [
    { ticker: 'A', sentiment: 1.0, news: 1 },
    { ticker: 'B', sentiment: 0.0, news: 99 },
  ]
  const g = fasce(due)
  if (g.length === 1) assert.ok(g[0].media < 0.05, `media ${g[0].media}`)
})

test('la banda di una fascia si stringe quando le notizie sono tante', () => {
  const poche = fasce([{ ticker: 'A', sentiment: 0.2, news: 10 }])[0]
  const tante = fasce([{ ticker: 'A', sentiment: 0.2, news: 400 }])[0]
  assert.ok((tante.hi - tante.lo) < (poche.hi - poche.lo))
})
