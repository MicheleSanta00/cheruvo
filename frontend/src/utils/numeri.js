/**
 * numeri.js — Prezzi, variazioni e percentuali scritti tutti allo stesso modo.
 *
 * PERCHE' ESISTE (24 settembre 2026)
 *
 * `formattaPrezzo` stava in LogoCrypto.jsx ed era nato per togliere i
 * toFixed(2) che su Dogecoin buttavano via le cifre. Ne erano rimasti
 * parecchi, e l'app vera ne mostrava tre effetti:
 *
 *   1. La variazione passava da `formattaPrezzo`, che sceglie i decimali in
 *      base al numero che riceve. Tesla a 379,18 che perde 53 centesimi
 *      usciva "−0,5300": quattro decimali, perche' 0,53 e' sotto 1 e la
 *      regola e' pensata per le monete da pochi centesimi. I decimali di una
 *      variazione sono quelli del PREZZO a cui si riferisce, non i suoi.
 *   2. Sulla stessa riga "−0,5300 (−0.14%)": virgola nel prezzo, punto nella
 *      percentuale, perche' la percentuale usava toFixed.
 *   3. Apertura, massimo e minimo del periodo, e il prezzo accanto al nome in
 *      alto, usavano ancora toFixed(2): Shiba, che vale 0,00001, diventava
 *      "$0.00" in tutte e quattro le caselle.
 *
 * Qui le regole stanno in un posto solo, e sono funzioni pure: si provano con
 * `node --test` senza tirarsi dietro React.
 */

const LOCALE = 'it-IT'

/** Quanti decimali servono a un prezzo di questo ordine di grandezza. */
export function decimaliPrezzo(v) {
  const a = Math.abs(Number(v))
  if (!Number.isFinite(a)) return 2
  return a >= 1 ? 2          // 64.366,85 · 3,42
    : a >= 0.01 ? 4          // 0,0812
    : a >= 0.0001 ? 6        // 0,000834
    : 8                      // monete micro
}

function scrivi(v, decimali) {
  return Number(v).toLocaleString(LOCALE, {
    minimumFractionDigits: decimali,
    maximumFractionDigits: decimali,
  })
}

/**
 * Prezzo con la precisione giusta per il suo ordine di grandezza.
 *
 * Serviva perché il grafico usava toFixed(2) ovunque. Su Bitcoin a 64.366,85
 * va benissimo. Su Dogecoin, che vale 0,08 dollari, mostrava "0.08" buttando
 * via tutta l'informazione: due monete diverse a 0,081 e 0,084 sarebbero
 * apparse identiche, e una variazione del 4% invisibile.
 */
export function formattaPrezzo(v) {
  if (v == null || Number.isNaN(Number(v)) || !Number.isFinite(Number(v))) return '—'
  return scrivi(v, decimaliPrezzo(v))
}

/**
 * Una variazione di prezzo, col segno, con i decimali del prezzo a cui si
 * riferisce: "+29,19" su Nvidia, "−0,53" su Tesla, "+0,000001" su Shiba.
 * Il meno e' quello tipografico (U+2212), come nel resto delle intestazioni.
 */
export function formattaVariazione(delta, riferimento) {
  const d = Number(delta)
  if (delta == null || !Number.isFinite(d)) return '—'
  const decimali = decimaliPrezzo(riferimento ?? delta)
  // Arrotondata PRIMA di decidere il segno: -0,001 su un prezzo a due
  // decimali si scrive "+0,00", non "−0,00".
  const arrotondata = Number(d.toFixed(decimali))
  const segno = arrotondata < 0 ? '−' : '+'
  return segno + scrivi(Math.abs(arrotondata), decimali)
}

/** Una percentuale col segno e due decimali: "+15,16%", "−0,14%". */
export function formattaPct(p) {
  const v = Number(p)
  if (p == null || !Number.isFinite(v)) return '—'
  const arrotondata = Number(v.toFixed(2))
  const segno = arrotondata < 0 ? '−' : '+'
  return segno + scrivi(Math.abs(arrotondata), 2) + '%'
}
