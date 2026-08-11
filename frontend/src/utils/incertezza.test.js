/**
 * Test di incertezza.js.
 *
 * Girano con il runner incluso in Node, senza aggiungere dipendenze:
 *
 *     cd frontend && npm test
 *
 * I casi che contano davvero sono gli ultimi di ogni sezione: sono i numeri
 * veri misurati l'11 agosto 2026, quelli che hanno fatto scoprire i difetti.
 * Se un domani qualcuno riabbassa una soglia, quei test si accendono.
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import {
  MIN_COPPIE, MIN_GIORNI_MEDIA, correlazione, mediaConBanda,
  compatibileConZero, etichetta, spiegazione,
} from './incertezza.js'

// Serie con correlazione perfetta, lunga quanto serve.
const seriePerfetta = (n) => {
  const xs = [], ys = []
  for (let i = 0; i < n; i++) { xs.push(i); ys.push(2 * i + 1) }
  return [xs, ys]
}

// ── La soglia ────────────────────────────────────────────────────────────
test('sotto il minimo non esce nessun numero, nemmeno se la relazione è perfetta', () => {
  const [xs, ys] = seriePerfetta(MIN_COPPIE - 1)
  const c = correlazione(xs, ys)
  assert.equal(c.r, null, 'ha prodotto un coefficiente sotto la soglia')
  assert.equal(c.n, MIN_COPPIE - 1, 'deve comunque dire quante coppie ha trovato')
})

test('esattamente al minimo il numero esce', () => {
  const [xs, ys] = seriePerfetta(MIN_COPPIE)
  assert.equal(correlazione(xs, ys).r, 1)
})

test('le coppie a metà non contano come coppie', () => {
  // Venticinque valori ma solo diciannove completi: sotto la soglia.
  const xs = [], ys = []
  for (let i = 0; i < 25; i++) { xs.push(i); ys.push(i < 19 ? i : null) }
  const c = correlazione(xs, ys)
  assert.equal(c.n, 19)
  assert.equal(c.r, null)
})

test('una serie piatta non ha correlazione definita, e non finge di averla', () => {
  const xs = Array.from({ length: 30 }, (_, i) => i)
  const ys = Array.from({ length: 30 }, () => 0.5)
  assert.equal(correlazione(xs, ys).r, null)
})

// ── La banda ─────────────────────────────────────────────────────────────
test('la banda contiene sempre il coefficiente', () => {
  const xs = [], ys = []
  for (let i = 0; i < 40; i++) { xs.push(Math.sin(i)); ys.push(Math.sin(i) + Math.cos(i * 3)) }
  const c = correlazione(xs, ys)
  assert.ok(c.lo <= c.r && c.r <= c.hi, `banda ${c.lo}..${c.hi} non contiene ${c.r}`)
})

test('più coppie, banda più stretta', () => {
  const rumore = (n, seme) => {
    const xs = [], ys = []
    let s = seme
    for (let i = 0; i < n; i++) {
      s = (s * 1103515245 + 12345) % 2147483648
      xs.push(s / 2147483648)
      s = (s * 1103515245 + 12345) % 2147483648
      ys.push(s / 2147483648)
    }
    return [xs, ys]
  }
  const larga  = correlazione(...rumore(25, 7))
  const stretta = correlazione(...rumore(400, 7))
  assert.ok((stretta.hi - stretta.lo) < (larga.hi - larga.lo),
    'con più dati la banda deve restringersi')
})

test('una relazione debole su tanti dati è distinguibile da zero, la stessa su pochi no', () => {
  // y segue x per metà, il resto è una dentellatura regolare che fa da rumore.
  const costruisci = (n) => {
    const xs = [], ys = []
    for (let i = 0; i < n; i++) {
      const x = (i % 17) / 17
      xs.push(x)
      ys.push(x + ((i % 5) - 2) * 0.55)
    }
    return [xs, ys]
  }
  const pochi = correlazione(...costruisci(20))
  const tanti = correlazione(...costruisci(400))
  assert.ok(Math.abs(tanti.r - pochi.r) < 0.25, 'i due r devono essere simili')
  assert.equal(compatibileConZero(pochi), true, 'con venti coppie non si può concludere')
  assert.equal(compatibileConZero(tanti), false, 'con quattrocento sì')
})

// ── Cosa viene detto all'utente ──────────────────────────────────────────
test('senza dati sufficienti non si dice né positiva né negativa', () => {
  const c = correlazione(...seriePerfetta(5))
  assert.equal(etichetta(c), 'Dati insufficienti')
  assert.match(spiegazione(c), /servono 20 giorni, ne hai 5/)
})

test('gli aggettivi di intensità non esistono più', () => {
  // Erano "Forte" e "Moderata": davano un giudizio di intensità a numeri che
  // spesso non erano nemmeno distinguibili da zero.
  const casi = [correlazione(...seriePerfetta(5)), correlazione(...seriePerfetta(30))]
  for (const c of casi) {
    assert.doesNotMatch(etichetta(c), /forte|moderata|debole/i)
  }
})

test('quando la banda comprende lo zero lo dice, invece di dare un verso', () => {
  const xs = [], ys = []
  for (let i = 0; i < 30; i++) { xs.push(i % 7); ys.push((i * 13) % 11) }
  const c = correlazione(xs, ys)
  if (compatibileConZero(c)) {
    assert.match(spiegazione(c), /comprende lo zero/)
    assert.equal(etichetta(c), 'Non distinguibile da zero')
  }
})

// ── Il caso vero, quello che ha fatto nascere il file ────────────────────
test('NVDA 11 agosto 2026: i cinque giorni che davano -0.712 adesso non danno niente', () => {
  // sentiment del giorno, variazione (Close-Open)/Open dello stesso giorno.
  const giorni = [
    ['2026-08-03', -0.3000,  0.0453],
    ['2026-08-04',  0.0750,  0.0030],
    ['2026-08-06',  0.2831, -0.0115],
    ['2026-08-07',  0.2098,  0.0109],
    ['2026-08-10',  0.0316, -0.0192],
  ]
  const c = correlazione(giorni.map(g => g[1]), giorni.map(g => g[2]))

  assert.equal(c.n, 5)
  assert.equal(c.r, null, 'su cinque giorni non deve uscire nessun coefficiente')
  assert.equal(etichetta(c), 'Dati insufficienti')

  // E il motivo per cui non deve uscire: togliendo il 3 agosto cambia segno.
  // Il calcolo qui sotto salta la soglia apposta, per documentare la fragilità.
  const senzaIlTre = giorni.slice(1)
  const grezzo = (pairs) => {
    const n = pairs.length
    const mx = pairs.reduce((s, p) => s + p[1], 0) / n
    const my = pairs.reduce((s, p) => s + p[2], 0) / n
    let num = 0, dx = 0, dy = 0
    for (const p of pairs) {
      num += (p[1] - mx) * (p[2] - my); dx += (p[1] - mx) ** 2; dy += (p[2] - my) ** 2
    }
    return num / Math.sqrt(dx * dy)
  }
  assert.ok(grezzo(giorni) < -0.7, 'con tutti e cinque i giorni era fortemente negativa')
  assert.ok(grezzo(senzaIlTre) > 0, 'togliendo un giorno solo cambiava segno')
})

// ── Le medie di rendimento, il secondo posto con lo stesso difetto ────────
test('un giorno solo non è una media', () => {
  const m = mediaConBanda([2.56])
  assert.equal(m.media, null, 'ha spacciato una giornata per una media')
  assert.equal(m.n, 1)
})

test('sotto la soglia il numero non esce, e viene detto quanti giorni mancano', () => {
  const m = mediaConBanda(Array.from({ length: 17 }, (_, i) => (i % 3) - 1))
  assert.equal(m.media, null)
  assert.equal(m.n, 17)
})

test('dalla soglia in su esce, sempre con la banda', () => {
  const m = mediaConBanda(Array.from({ length: MIN_GIORNI_MEDIA }, () => 0.5))
  assert.equal(m.media, 0.5)
  assert.ok(m.lo != null && m.hi != null, 'la banda deve esserci sempre')
})

test('i buchi non contano come giorni', () => {
  const v = Array.from({ length: MIN_GIORNI_MEDIA + 5 }, (_, i) => (i < 6 ? null : 1.0))
  assert.equal(mediaConBanda(v).n, MIN_GIORNI_MEDIA - 1)
  assert.equal(mediaConBanda(v).media, null, 'con i buchi tolti è sotto soglia')
})

test('una media piccola dentro rendimenti rumorosi resta compatibile con zero', () => {
  // Rendimenti realistici: media +0.14%, oscillazioni di quasi due punti.
  // È il caso ETH bearish misurato l'11 agosto 2026, allungato fino a soglia.
  const v = Array.from({ length: 40 }, (_, i) => 0.14 + ((i % 4) - 1.5) * 1.4)
  const m = mediaConBanda(v)
  assert.ok(Math.abs(m.media - 0.14) < 0.2)
  assert.equal(compatibileConZero(m), true,
    'con questa dispersione quaranta giorni non bastano a distinguerla da zero')
})

test('lo stesso scarto su rendimenti tranquilli invece si distingue', () => {
  const v = Array.from({ length: 40 }, (_, i) => 0.14 + ((i % 4) - 1.5) * 0.08)
  assert.equal(compatibileConZero(mediaConBanda(v)), false)
})

test('compatibileConZero legge la banda, non il tipo di numero', () => {
  // Deve funzionare uguale su una correlazione e su una media: è quello che
  // permette di colorare tutti e due i riquadri con la stessa regola.
  const xs = Array.from({ length: 30 }, (_, i) => i)
  assert.equal(compatibileConZero(correlazione(xs, xs.map(x => 2 * x))), false)
  assert.equal(compatibileConZero(mediaConBanda(Array(40).fill(5))), false)
  assert.equal(compatibileConZero(mediaConBanda([1, -1])), true, 'sotto soglia: non si sa')
  assert.equal(compatibileConZero(null), true)
})

test('i nove riquadri misurati l11 agosto 2026 non mostrerebbero più niente', () => {
  // ticker, gruppo, quanti giorni c'erano davvero.
  const misurati = [
    ['NVDA', 'bullish', 2], ['NVDA', 'bearish', 1],
    ['BTC',  'bullish', 6], ['BTC',  'bearish', 12],
    ['ETH',  'bullish', 16], ['ETH', 'bearish', 17],
    ['AAPL', 'bullish', 3], ['TSLA', 'bearish', 2],
    ['MSFT', 'bullish', 1],
  ]
  for (const [tk, gruppo, n] of misurati) {
    const m = mediaConBanda(Array.from({ length: n }, (_, i) => (i % 5) - 2))
    assert.equal(m.media, null, `${tk} ${gruppo}: con ${n} giorni non deve uscire un numero`)
  }
})
