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
      {/*
        Era una scritta e basta. I termini di GDELT, letti dal testo originale
        il 19 settembre 2026, chiedono due cose e non una: "any use or
        redistribution of the data must include a citation to the GDELT
        Project AND A LINK to this website". La citazione c'era, il link no.

        È il genere di inadempienza che costa niente a sanare e che nessuno
        perdona se la scopre lui: la fonte è l'unica del progetto con licenza
        davvero libera, e l'intero archivio ci sta sopra.
      */}
      <a href="https://www.gdeltproject.org/" target="_blank" rel="noopener noreferrer"
         title={it ? 'Dati da The GDELT Project' : 'Data from The GDELT Project'}
         style={{ ...cella, color: 'inherit', textDecoration: 'none',
                  borderBottom: '1px dotted var(--border-br)' }}>
        GDELT
      </a>
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
