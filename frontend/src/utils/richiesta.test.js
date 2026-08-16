import test from 'node:test'
import assert from 'node:assert/strict'
import { intestazioni, generedelRifiuto } from './richiesta.js'

// ── Le intestazioni ────────────────────────────────────────────────────────

test('senza token la richiesta parte lo stesso, senza Authorization', () => {
  const h = intestazioni({ token: null, sessione: 'abc' })
  assert.equal('Authorization' in h, false,
    'con Authorization assente il server decide; con la richiesta assente decide il client')
  assert.equal(h['X-Sessione'], 'abc')
  assert.equal(h['Content-Type'], 'application/json')
})

test('con il token Authorization ci va', () => {
  const h = intestazioni({ token: 'xyz', sessione: 'abc' })
  assert.equal(h.Authorization, 'Bearer xyz')
})

test('un token vuoto vale come nessun token', () => {
  assert.equal('Authorization' in intestazioni({ token: '' }), false)
})

test('con FormData il Content-Type lo mette il browser', () => {
  const h = intestazioni({ token: 'xyz', isForm: true })
  assert.equal('Content-Type' in h, false, 'serve la boundary, che sa solo il browser')
})

test('le intestazioni di chi chiama vincono sulle nostre', () => {
  const h = intestazioni({ token: 'xyz', extra: { 'Content-Type': 'text/csv' } })
  assert.equal(h['Content-Type'], 'text/csv')
})

// ── Che genere di rifiuto è un 401 ─────────────────────────────────────────

test('un 401 a chi non era entrato chiede un account, non un nuovo accesso', () => {
  assert.equal(generedelRifiuto(401, null), 'serve-account')
})

test('un 401 a chi aveva un token è una sessione scaduta', () => {
  assert.equal(generedelRifiuto(401, 'xyz'), 'sessione-scaduta')
})

test('quello che non e un 401 non e un rifiuto di accesso', () => {
  for (const s of [200, 204, 403, 404, 429, 500]) {
    assert.equal(generedelRifiuto(s, null), null, `stato ${s}`)
  }
})
