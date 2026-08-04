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
const MONETE = {
  'BTC-USD':  { sigla: '₿', colore: '#f7931a', nome: 'Bitcoin' },   // ₿
  'ETH-USD':  { sigla: 'Ξ', colore: '#627eea', nome: 'Ethereum' },  // Ξ
  'SOL-USD':  { sigla: 'SOL',    colore: '#14f195', nome: 'Solana' },
  'XRP-USD':  { sigla: 'XRP',    colore: '#23292f', nome: 'XRP' },
  'ADA-USD':  { sigla: 'ADA',    colore: '#0033ad', nome: 'Cardano' },
  'DOGE-USD': { sigla: 'DOGE',   colore: '#c2a633', nome: 'Dogecoin' },
  'AVAX-USD': { sigla: 'AVAX',   colore: '#e84142', nome: 'Avalanche' },
  'LINK-USD': { sigla: 'LINK',   colore: '#2a5ada', nome: 'Chainlink' },
}

export function eCrypto(ticker) {
  return typeof ticker === 'string' && ticker.toUpperCase().endsWith('-USD')
}

export default function LogoCrypto({ ticker, size = 18 }) {
  const m = MONETE[(ticker || '').toUpperCase()]
  // Moneta fuori elenco: primo carattere del ticker su fondo neutro, così
  // una crypto che non conosciamo non lascia un buco nella riga.
  const sigla  = m?.sigla  ?? (ticker || '?').replace('-USD', '').slice(0, 2)
  const colore = m?.colore ?? '#64748b'

  // Le sigle lunghe vanno rimpicciolite, altrimenti escono dal cerchio
  const scala = sigla.length >= 4 ? 0.30 : sigla.length === 3 ? 0.36 : 0.58

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
