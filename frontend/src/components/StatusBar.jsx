import { useLang } from '../LangContext.jsx'

/**
 * Barra di stato in fondo all'applicazione.
 *
 * Dice sempre da dove arrivano i dati, quanti sono e quando sono stati
 * aggiornati. È il dettaglio che distingue uno strumento professionale, che
 * lavora anche mentre non lo guardi, da una pagina che aspetta un comando.
 */
export default function StatusBar({ stats, updatedAt }) {
  const { lang } = useLang()
  const it = lang === 'it'

  const ora = updatedAt
    ? new Date(updatedAt).toLocaleTimeString(it ? 'it-IT' : 'en-US', { hour: '2-digit', minute: '2-digit' })
    : null

  const cella = { display: 'inline-flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap' }
  const sep = <span style={{ color: 'var(--border-br)' }}>│</span>

  return (
    <div style={{
      flexShrink: 0, height: 26, display: 'flex', alignItems: 'center', gap: 14,
      padding: '0 14px', background: 'var(--near-black)',
      borderTop: '1px solid var(--border)',
      fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums',
      fontSize: 10.5, color: 'var(--muted)', overflow: 'hidden',
    }}>
      <span style={cella}>GDELT</span>
      {sep}
      <span style={cella} className="hide-mobile">
        {stats?.tickers ?? '—'} {it ? 'titoli' : 'stocks'}
      </span>
      <span className="hide-mobile">{sep}</span>
      <span style={cella} className="hide-mobile">
        {stats?.news_total != null
          ? Number(stats.news_total).toLocaleString(it ? 'it-IT' : 'en-US')
          : '—'} {it ? 'notizie' : 'news'}
      </span>
      {ora && <>{sep}<span style={cella}>{it ? 'agg.' : 'upd.'} {ora}</span></>}
      {sep}
      <span style={{ ...cella, color: 'var(--green)' }}>● {it ? 'connesso' : 'online'}</span>
      {/*
        Diceva "Cheruvo · Pro". Un residuo del muro a pagamento, spento il 6
        agosto 2026: da allora `isPro` sta fisso a true per tutti, quindi
        quella scritta comparve a chiunque e annunciava un piano che non
        esiste. Compare in ogni screenshot che si manda in giro, ed è
        esattamente il tipo di contraddizione che qualcuno nota prima di te.
      */}
      <span style={{ marginLeft: 'auto', opacity: .75 }} className="hide-mobile">
        Cheruvo
      </span>
    </div>
  )
}
