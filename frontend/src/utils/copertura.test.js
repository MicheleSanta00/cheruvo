import test from 'node:test'
import assert from 'node:assert/strict'
import {
  statoCopertura, etichettaCopertura, coloreCopertura, offriScarico,
  IGNOTO, VUOTA, SCARSA, PIENA,
} from './copertura.js'

const RISPOSTA = {
  min_news: 5,
  finestra_ore: 48,
  giorni_base: 7,
  titoli: {
    'NVDA': { ora: 21, settimana: 96 },
    'ENI.MI': { ora: 2, settimana: 9 },
    'SHEL.L': { ora: 0, settimana: 3 },
  },
}

// ── I quattro stati ────────────────────────────────────────────────────────

test('finche il dato non e arrivato non si dice niente', () => {
  // Il caso che conta: un "0 notizie" mostrato per un secondo mentre la
  // risposta e' in volo fa scartare un titolo che ne ha novantasei.
  for (const vuoto of [null, undefined, {}, { titoli: null }]) {
    const c = statoCopertura(vuoto, 'NVDA')
    assert.equal(c.stato, IGNOTO)
    assert.equal(etichettaCopertura(c, 'it'), '',
      'a copertura ignota l\'etichetta deve essere vuota, non uno zero')
  }
})

test('un titolo con abbastanza notizie e pieno', () => {
  const c = statoCopertura(RISPOSTA, 'NVDA')
  assert.equal(c.stato, PIENA)
  assert.equal(c.ora, 21)
})

test('sotto la soglia della classifica e scarso, non vuoto', () => {
  const c = statoCopertura(RISPOSTA, 'ENI.MI')
  assert.equal(c.stato, SCARSA)
  assert.equal(c.settimana, 9, 'qualcosa da leggere c\'e\' eccome')
})

test('zero in 48 ore ma qualcosa nella settimana resta scarso', () => {
  // Se questo diventasse VUOTA, l\'app proporrebbe di riscaricare un titolo
  // che ha gia' tre notizie in archivio.
  const c = statoCopertura(RISPOSTA, 'SHEL.L')
  assert.equal(c.stato, SCARSA)
  assert.equal(offriScarico(c), false)
})

test('un titolo che non c\'e in archivio e vuoto', () => {
  // ADIL e BB: quello che ha scritto a mano la sessione del 17 agosto 2026.
  for (const tk of ['ADIL', 'BB']) {
    const c = statoCopertura(RISPOSTA, tk)
    assert.equal(c.stato, VUOTA, tk)
    assert.equal(offriScarico(c), true, tk)
  }
})

test('la soglia arriva col dato invece di essere riscritta qui', () => {
  const severa = { ...RISPOSTA, min_news: 30 }
  assert.equal(statoCopertura(severa, 'NVDA').stato, SCARSA,
    'con la soglia a 30, ventuno notizie non bastano piu\'')
  assert.equal(statoCopertura(RISPOSTA, 'NVDA').stato, PIENA)
})

test('senza min_news si ripiega su cinque invece di rompersi', () => {
  const senza = { titoli: { 'NVDA': { ora: 6, settimana: 10 } } }
  assert.equal(statoCopertura(senza, 'NVDA').stato, PIENA)
})

// ── Le etichette ───────────────────────────────────────────────────────────

test('l\'etichetta piena parla delle 48 ore, la scarsa dei 7 giorni', () => {
  assert.equal(etichettaCopertura(statoCopertura(RISPOSTA, 'NVDA'), 'it'),
    '21 notizie in 48 ore')
  assert.equal(etichettaCopertura(statoCopertura(RISPOSTA, 'ENI.MI'), 'it'),
    '9 notizie in 7 giorni')
})

test('il vuoto lo dice, non lo lascia indovinare', () => {
  const c = statoCopertura(RISPOSTA, 'ADIL')
  assert.equal(etichettaCopertura(c, 'it'), 'nessuna notizia in archivio')
  assert.equal(etichettaCopertura(c, 'en'), 'no news in archive')
})

test('il singolare non diventa "1 notizie"', () => {
  const uno = { min_news: 5, titoli: { X: { ora: 1, settimana: 1 } } }
  assert.equal(etichettaCopertura(statoCopertura(uno, 'X'), 'it'),
    '1 notizia in 7 giorni')
  assert.equal(etichettaCopertura(statoCopertura(uno, 'X'), 'en'),
    '1 story in 7 days')
})

test('esiste anche in inglese', () => {
  assert.equal(etichettaCopertura(statoCopertura(RISPOSTA, 'NVDA'), 'en'),
    '21 stories in 48h')
})

// ── Il colore ──────────────────────────────────────────────────────────────

test('a copertura ignota la pastiglia non si vede', () => {
  assert.equal(coloreCopertura(IGNOTO), 'transparent')
})

test('solo il pieno e verde', () => {
  assert.equal(coloreCopertura(PIENA), 'var(--green)')
  assert.notEqual(coloreCopertura(SCARSA), 'var(--green)')
  assert.notEqual(coloreCopertura(VUOTA), 'var(--green)')
})

// ── Lo scarico su richiesta ────────────────────────────────────────────────

test('non si propone lo scarico mentre il dato e in volo', () => {
  // Altrimenti il bottone lampeggia al caricamento su OGNI titolo.
  assert.equal(offriScarico(statoCopertura(null, 'NVDA')), false)
})

test('non si propone lo scarico dove c\'e gia tutto', () => {
  assert.equal(offriScarico(statoCopertura(RISPOSTA, 'NVDA')), false)
})
