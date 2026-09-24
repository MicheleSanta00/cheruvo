import { test } from 'node:test'
import assert from 'node:assert/strict'
import { decimaliPrezzo, formattaPrezzo, formattaVariazione, formattaPct } from './numeri.js'

test('il prezzo tiene le cifre che servono al suo ordine di grandezza', () => {
  assert.equal(formattaPrezzo(64366.85), '64.366,85')
  assert.equal(formattaPrezzo(379.18), '379,18')
  assert.equal(formattaPrezzo(0.0812), '0,0812')
  assert.equal(formattaPrezzo(0.000834), '0,000834')
  assert.equal(formattaPrezzo(0.00001234), '0,00001234')
  assert.equal(formattaPrezzo(null), '—')
  assert.equal(formattaPrezzo(NaN), '—')
})

test('la variazione prende i decimali dal prezzo, non da se stessa', () => {
  // Il difetto visto su Tesla il 24 settembre 2026: "−0,5300".
  assert.equal(formattaVariazione(-0.53, 379.18), '−0,53')
  assert.equal(formattaVariazione(29.19, 221.72), '+29,19')
  // Su una moneta da pochi centesimi le cifre servono davvero.
  assert.equal(formattaVariazione(0.0031, 0.0812), '+0,0031')
  assert.equal(formattaVariazione(-0.000001, 0.00001234), '−0,00000100')
})

test('una variazione che si arrotonda a zero non porta il meno', () => {
  assert.equal(formattaVariazione(-0.001, 379.18), '+0,00')
  assert.equal(formattaPct(-0.001), '+0,00%')
})

test('la percentuale usa la virgola come il prezzo accanto', () => {
  // Prima: "−0,5300 (−0.14%)", due separatori diversi sulla stessa riga.
  assert.equal(formattaPct(-0.14), '−0,14%')
  assert.equal(formattaPct(15.1612), '+15,16%')
  assert.equal(formattaPct(null), '—')
})

test('shiba non diventa più 0.00', () => {
  // Apertura, massimo e minimo del periodo usavano toFixed(2).
  assert.equal(decimaliPrezzo(0.00001234), 8)
  assert.notEqual(formattaPrezzo(0.00001234), '0,00')
})
