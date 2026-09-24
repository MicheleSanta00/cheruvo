/**
 * testo.js — Testo che arriva da fuori, messo a schermo senza sorprese.
 *
 * Due regole piccole, in un file loro perché si possono provare senza
 * browser (npm test), come richiesta.js e incertezza.js.
 */

/**
 * Un indirizzo che si può mettere in un href, oppure null.
 *
 * Gli indirizzi delle notizie arrivano da GDELT, dai feed RSS di Fed, BCE ed
 * ESMA e dalla SEC: fonti che non controlliamo. React 18 mette in un href
 * anche un "javascript:..." (si limita ad avvisare in console), e un clic su
 * quella riga eseguirebbe codice dentro app.cheruvo.com, dove c'è la
 * sessione dell'utente. Passano solo http e https. 24 settembre 2026.
 */
export function urlSicuro (u) {
  const s = String(u ?? '').trim()
  return /^https?:\/\//i.test(s) ? s : null
}

/**
 * Le frasi di un testo, senza spezzare i numeri.
 *
 * Il riquadro del riassunto AI faceva `riassunto.split('.')`, quindi ogni
 * numero decimale diventava due frasi: "il tono medio è 0.31 e in salita"
 * usciva come "il tono medio è 0." e "31 e in salita.". Con i riassunti
 * dei conti, pieni di cifre come 4.5 miliardi, succedeva quasi sempre.
 *
 * Si spezza solo dopo un punto (o ! o ?) seguito da uno spazio e da una
 * lettera maiuscola o una cifra: "0.31" non ha lo spazio, quindi resta
 * intero. Niente lookbehind nell'espressione, apposta: Safari su iPhone lo
 * supporta solo dalla 16.4, e un'espressione che un browser non capisce fa
 * cadere l'intero file.
 */
export function frasiDi (testo) {
  if (!testo) return []
  const pezzi = String(testo).split(/([.!?])\s+(?=[A-ZÀ-ÖØ-Ý0-9"«(])/)
  const frasi = []
  for (let i = 0; i < pezzi.length; i += 2) {
    const f = (pezzi[i] + (pezzi[i + 1] || '')).trim()
    if (f.length > 1) frasi.push(f)
  }
  return frasi
}

/**
 * Un titolo di GDELT senza gli spazi prima della punteggiatura.
 *
 * GDELT estrae il titolo dalla pagina già spezzato in parole, e in archivio
 * arriva "Tesla Is Supplying the Trucks . Nvidia Is Supplying the Compute" o
 * "Tesla car crashes into parked taxi at Auckland waterfront , two in
 * hospital". Visto nell'elenco notizie dell'app vera il 24 settembre 2026,
 * accanto alla versione pulita dello stesso titolo.
 *
 * Si corregge solo a schermo: il testo in archivio non cambia, quindi i
 * doppioni per (titolo, testata) di save_news e la chiave delle riprese
 * (`chiave_titolo`, che toglie comunque la punteggiatura) restano identici.
 * Il trattino in "Record - breaking" resta com'è: da solo non si distingue
 * da "Tesla - Reuters", e un titolo sbagliato è peggio di uno brutto.
 */
export function pulisciTitolo (t) {
  if (t == null) return ''
  return String(t)
    .replace(/\s+([.,;:!?%)\]])/g, '$1')
    .replace(/([(\[])\s+/g, '$1')
    .replace(/\s{2,}/g, ' ')
    .trim()
}
