/**
 * LogoCrypto.jsx — Il simbolo di una criptovaluta, disegnato in casa.
 *
 * Perché non usiamo un servizio esterno di loghi. Tre ragioni, in ordine di
 * peso. La prima è che l'API di Clearbit, che era lo standard, è stata chiusa
 * il primo dicembre 2025 lasciando a piedi chi la usava: una dipendenza in più
 * è una cosa in più che può sparire. La seconda è che i servizi gratuiti
 * rimasti chiedono l'attribuzione visibile nell'interfaccia. La terza è che
 * così non parte nessuna richiesta di rete: il simbolo c'è anche se la
 * connessione è lenta, e non rallenta una lista di venti righe.
 *
 * Non sono i loghi ufficiali, e non vogliono esserlo: sono dischi nel colore
 * della moneta con la sua sigla. Si riconoscono a colpo d'occhio, che è
 * l'unica cosa che serve in un elenco, e non c'è nessuna questione di marchi
 * perché non stiamo riproducendo il marchio di nessuno.
 */

// Colori presi dall'identità visiva di ciascuna moneta: sono quelli che la
// gente associa alla valuta, ed è ciò che rende la lista scorribile.
// La sigla dentro il cerchio è al massimo di DUE caratteri, di proposito.
// Con la sigla intera si leggeva "DOGE" dentro il disco e "DOGE" subito
// accanto: il cerchio smetteva di essere un marchio e diventava la ripetizione
// dell'etichetta. Due caratteri si leggono come un simbolo, non come testo.
const MONETE = {
  'BTC-USD':  { sigla: '₿',  colore: '#f7931a', nome: 'Bitcoin' },
  'ETH-USD':  { sigla: 'Ξ',  colore: '#627eea', nome: 'Ethereum' },
  'SOL-USD':  { sigla: 'SO', colore: '#14f195', nome: 'Solana' },
  'XRP-USD':  { sigla: 'XR', colore: '#23292f', nome: 'XRP' },
  'ADA-USD':  { sigla: 'AD', colore: '#0033ad', nome: 'Cardano' },
  'DOGE-USD': { sigla: 'DO', colore: '#c2a633', nome: 'Dogecoin' },
  'AVAX-USD': { sigla: 'AV', colore: '#e84142', nome: 'Avalanche' },
  'LINK-USD': { sigla: 'LI', colore: '#2a5ada', nome: 'Chainlink' },
  'DOT-USD':  { sigla: 'DT', colore: '#e6007a', nome: 'Polkadot' },
  'LTC-USD':  { sigla: 'LT', colore: '#a5a8a9', nome: 'Litecoin' },
  'UNI-USD':  { sigla: 'UN', colore: '#ff007a', nome: 'Uniswap' },
  'ATOM-USD': { sigla: 'AT', colore: '#2e3148', nome: 'Cosmos' },
  'XLM-USD':  { sigla: 'XL', colore: '#14b6e7', nome: 'Stellar' },
  'NEAR-USD': { sigla: 'NE', colore: '#00c08b', nome: 'NEAR' },
  'BCH-USD':  { sigla: 'BC', colore: '#8dc351', nome: 'Bitcoin Cash' },
  'SHIB-USD': { sigla: 'SH', colore: '#ffa409', nome: 'Shiba' },
  'MATIC-USD':{ sigla: 'PO', colore: '#8247e5', nome: 'Polygon' },
  'APT-USD':  { sigla: 'AP', colore: '#3b3b3b', nome: 'Aptos' },
  'ARB-USD':  { sigla: 'AR', colore: '#12aaff', nome: 'Arbitrum' },
  'OP-USD':   { sigla: 'OP', colore: '#ff0420', nome: 'Optimism' },
}

export function eCrypto(ticker) {
  return typeof ticker === 'string' && ticker.toUpperCase().endsWith('-USD')
}

/**
 * Il mercato scelto: 'azioni' oppure 'crypto'.
 *
 * Non sono due prodotti separati con due codebase, sono la STESSA app con un
 * filtro: watchlist, classifiche, nastro e suggerimenti mostrano solo quello
 * che appartiene al mercato attivo. Costa una variabile invece di un secondo
 * progetto da mantenere, e il giorno che uno dei due va davvero forte si
 * separa sul serio senza aver buttato lavoro.
 *
 * Perché comunque separarli: mischiare Bitcoin e Eni nella stessa lista rende
 * illeggibile entrambe le cose. E se un giorno si vende un abbonamento crypto,
 * chi arriva deve trovare un prodotto crypto, non un elenco misto.
 */
export const MERCATI = ['azioni', 'crypto']

export function leggiMercato() {
  try {
    const s = localStorage.getItem('cheruvo_mercato')
    // Si parte da CRYPTO: è la sezione che funziona. Aprire di default su
    // "azioni" vorrebbe dire accogliere ogni visitatore con la schermata di
    // una sezione chiusa, che è il modo peggiore di presentarsi.
    return MERCATI.includes(s) ? s : 'crypto'
  } catch (_) { return 'crypto' }
}

export function salvaMercato(m) {
  try { localStorage.setItem('cheruvo_mercato', m) } catch (_) {}
}

/** Un ticker appartiene al mercato attivo? */
export function nelMercato(ticker, mercato) {
  return mercato === 'crypto' ? eCrypto(ticker) : !eCrypto(ticker)
}

/** Il titolo da aprire quando si passa da un mercato all'altro. */
export const PREDEFINITO = { azioni: 'NVDA', crypto: 'BTC-USD' }

// Il formato dei prezzi sta in utils/numeri.js dal 24 settembre 2026, insieme
// a quello di variazioni e percentuali: stesse regole ovunque, e funzioni pure
// che si provano senza React. Resta esportato anche da qui perché mezzo
// frontend lo importa da questo file.
export { formattaPrezzo } from '../utils/numeri.js'

export default function LogoCrypto({ ticker, size = 18 }) {
  const m = MONETE[(ticker || '').toUpperCase()]
  // Moneta fuori elenco: primo carattere del ticker su fondo neutro, così
  // una crypto che non conosciamo non lascia un buco nella riga.
  const sigla  = m?.sigla  ?? (ticker || '?').replace('-USD', '').slice(0, 2)
  const colore = m?.colore ?? '#64748b'

  // Le sigle lunghe vanno rimpicciolite, altrimenti escono dal cerchio
  // Un carattere solo (₿, Ξ) puo' essere grande; due stanno un po' piu'
  // stretti per non toccare il bordo del cerchio.
  const scala = sigla.length === 1 ? 0.60 : sigla.length === 2 ? 0.42 : 0.34

  return (
    <span
      title={m?.nome || ticker}
      aria-label={m?.nome || ticker}
      style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: size, height: size, borderRadius: '50%',
        background: colore, color: '#fff', flexShrink: 0,
        fontSize: Math.round(size * scala), fontWeight: 700, lineHeight: 1,
        fontFamily: 'var(--sans)', letterSpacing: sigla.length > 2 ? '-.04em' : 0,
        // XRP è quasi nero: sul tema scuro sparirebbe contro lo sfondo
        boxShadow: colore === '#23292f' ? '0 0 0 1px var(--border-br)' : 'none',
      }}
    >
      {sigla}
    </span>
  )
}
