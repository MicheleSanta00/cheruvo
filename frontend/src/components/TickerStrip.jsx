import { useLang } from '../LangContext.jsx'

/**
 * Nastro dei ticker sotto l'intestazione.
 *
 * È il primo segnale che l'applicazione è viva: prima di leggere qualsiasi
 * cosa, si vedono dei numeri che si muovono. Riceve i dati già caricati da
 * App (una sola chiamata condivisa con la colonna di destra e la watchlist).
 */
export default function TickerStrip({ rows, onPick }) {
  const { lang } = useLang()
  if (!rows?.length) return null

  // Duplico la coda in fondo così il nastro riempie anche gli schermi larghi
  // Il nastro si ripete per riempire la larghezza, ma SOLO se ha abbastanza
  // elementi perché la ripetizione non si noti. Con due monete a schermo il
  // raddoppio produceva "ETH BTC ETH BTC", che sembra un errore e non un
  // nastro scorrevole.
  const elenco = (rows.length >= 6 && rows.length < 14)
    ? [...rows, ...rows.slice(0, 6)]
    : rows

  return (
    <div
      className="hide-mobile"
      style={{
        height: 30, flexShrink: 0, display: 'flex', alignItems: 'center',
        overflow: 'hidden', borderBottom: '1px solid var(--border)',
        background: 'var(--black)', fontSize: 11.5,
      }}
      title={lang === 'it' ? 'Sentiment delle ultime 48 ore' : 'Sentiment of the last 48 hours'}
    >
      {elenco.map((r, i) => (
        <button
          key={`${String(r.ticker).replace('-USD', '')}-${i}`}
          onClick={() => onPick?.(r.ticker)}
          style={{
            display: 'flex', alignItems: 'center', gap: 7, whiteSpace: 'nowrap',
            padding: '0 14px', height: '100%', background: 'transparent',
            border: 'none', borderRight: '1px solid var(--border)',
            color: 'var(--white)', cursor: 'pointer', fontSize: 11.5,
          }}
          onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(var(--rgb-contrasto), 0.04)' }}
          onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
        >
          <span style={{ fontWeight: 700, letterSpacing: '0.02em' }}>{String(r.ticker).replace('-USD', '')}</span>
          <span style={{
            fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums', fontWeight: 700,
            color: r.sentiment > 0.08 ? 'var(--green)' : r.sentiment < -0.08 ? 'var(--red)' : 'var(--muted)',
          }}>
            {r.sentiment > 0 ? '+' : r.sentiment < 0 ? '−' : ''}{Math.abs(r.sentiment).toFixed(2)}
          </span>
        </button>
      ))}
    </div>
  )
}
