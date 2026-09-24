import { test } from 'node:test'
import assert from 'node:assert/strict'
import { urlSicuro, frasiDi, pulisciTitolo } from './testo.js'

test('gli indirizzi normali passano', () => {
  assert.equal(urlSicuro('https://www.reuters.com/a?b=1'), 'https://www.reuters.com/a?b=1')
  assert.equal(urlSicuro('http://example.com'), 'http://example.com')
  assert.equal(urlSicuro('  HTTPS://X.COM  '), 'HTTPS://X.COM')
})

test('un javascript: in un href non esce mai', () => {
  assert.equal(urlSicuro('javascript:alert(1)'), null)
  assert.equal(urlSicuro(' JavaScript:alert(1)'), null)
  assert.equal(urlSicuro('data:text/html,<script>'), null)
  assert.equal(urlSicuro(''), null)
  assert.equal(urlSicuro(null), null)
  assert.equal(urlSicuro(undefined), null)
})

test('un numero decimale non spezza la frase', () => {
  // Il difetto: split('.') dava "il tono medio è 0" e "31 e in salita".
  const f = frasiDi('Il tono medio è 0.31 e in salita. Nvidia vale 4.5 miliardi.')
  assert.deepEqual(f, ['Il tono medio è 0.31 e in salita.', 'Nvidia vale 4.5 miliardi.'])
})

test('le frasi normali si separano', () => {
  const f = frasiDi('Prima frase. Seconda frase! Terza? Quarta')
  assert.deepEqual(f, ['Prima frase.', 'Seconda frase!', 'Terza?', 'Quarta'])
})

test('un testo vuoto non produce frasi', () => {
  assert.deepEqual(frasiDi(''), [])
  assert.deepEqual(frasiDi(null), [])
})

test('le lettere accentate maiuscole contano come inizio di frase', () => {
  assert.deepEqual(frasiDi('Il titolo sale. È una notizia.'), ['Il titolo sale.', 'È una notizia.'])
})

test('gli spazi di GDELT prima della punteggiatura spariscono', () => {
  assert.equal(pulisciTitolo('Tesla Is Supplying the Trucks . Nvidia Is Supplying the Compute'),
    'Tesla Is Supplying the Trucks. Nvidia Is Supplying the Compute')
  assert.equal(pulisciTitolo('Auckland waterfront , two in hospital'), 'Auckland waterfront, two in hospital')
  assert.equal(pulisciTitolo('Profits up 12 % ( estimate )'), 'Profits up 12% (estimate)')
})

test('un titolo già pulito resta identico, trattini compresi', () => {
  const t = 'Record - breaking US order boosts Tesla: shares up 3.5%'
  assert.equal(pulisciTitolo(t), t)
  assert.equal(pulisciTitolo(null), '')
})
