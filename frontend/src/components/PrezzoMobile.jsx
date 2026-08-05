import LogoCrypto, { eCrypto, formattaPrezzo } from './LogoCrypto.jsx'

/**
 * PrezzoMobile.jsx — Il prezzo grande, in cima, solo su telefono.
 *
 * Perché esiste. Su desktop il prezzo e la variazione stanno nella barra in
 * alto, accanto al nome del titolo. Su mobile quella parte è nascosta
 * (`hide-mobile`) perché non ci sta, e il risultato era che aprendo Cheruvo
 * dal telefono la prima schermata mostrava "news totali", "sentiment medio",
 * "picco positivo", "picco negativo" e "fonti attive": cinque metriche
 * secondarie, e il prezzo da nessuna parte. Bisognava scorrere per trovarlo.
 *
 * Su un'app di criptovalute aperta dal telefono, il prezzo è il motivo per cui
 * l'hai aperta. Deve essere la prima cosa, senza scorrere e senza cercare.
 */
export default function PrezzoMobile({ ticker, tickerInfo, prices, statoBorsa }) {
  if (!prices?.length) return null

  const ultimo = prices[prices.length - 1]?.Close
  const primo  = prices[0]?.Close
  if (!isFinite(ultimo)) return null

  // Sull'intraday il confronto è col riferimento vero (24 ore o chiusura
  // precedente); sugli altri periodi è l'inizio del periodo mostrato.
  const base = statoBorsa?.chiusura_precedente ?? primo
  const variazione = isFinite(base) && base ? ultimo - base : null
  const pct = variazione != null ? (variazione / base) * 100 : null
  const su = (pct ?? 0) >= 0

  const etichetta = statoBorsa?.tipo_riferimento === '24h' ? 'in 24 ore'
    : statoBorsa ? 'da ieri' : 'sul periodo'

  const ora = statoBorsa?.ultimo_scambio
    ? new Date(statoBorsa.ultimo_scambio * 1000)
        .toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })
    : null

  return (
    <div className="solo-telefono" style={{
      padding: '14px 16px 12px',
      borderBottom: '1px solid var(--border)',
      flexDirection: 'column', gap: 3,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
        {eCrypto(ticker) && <LogoCrypto ticker={ticker} size={17} />}
        <span style={{ fontSize: 14, fontWeight: 700, letterSpacing: '-.01em' }}>
          {eCrypto(ticker) ? String(ticker).replace('-USD', '') : ticker}
        </span>
        <span style={{
          fontSize: 11.5, color: 'var(--muted)', overflow: 'hidden',
          textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>{tickerInfo?.nome}</span>
      </div>

      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <span style={{
          fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums',
          fontSize: 30, fontWeight: 700, lineHeight: 1.05,
        }}>{formattaPrezzo(ultimo)}</span>
        {pct != null && (
          <span style={{
            fontFamily: 'var(--mono)', fontSize: 14, fontWeight: 700,
            color: su ? 'var(--green)' : 'var(--red)',
          }}>
            {su ? '+' : '−'}{formattaPrezzo(Math.abs(variazione))}
            {' '}({su ? '+' : '−'}{Math.abs(pct).toFixed(2)}%)
          </span>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 10.5,
                    color: 'var(--muted)', marginTop: 2 }}>
        <span>{etichetta}</span>
        {ora && (
          <>
            <span style={{ opacity: .4 }}>·</span>
            {/* L'ora dell'ultimo scambio anche qui: i dati di Yahoo su diverse
                borse hanno un ritardo, e su mobile è ancora più facile
                scambiare un numero fermo per un numero in diretta. */}
            <span style={{ fontFamily: 'var(--mono)' }}>ultimo scambio {ora}</span>
          </>
        )}
        {statoBorsa?.sempre_aperto && (
          <>
            <span style={{ opacity: .4 }}>·</span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              <span style={{ width: 5, height: 5, borderRadius: '50%',
                             background: 'var(--green)' }} />
              24/7
            </span>
          </>
        )}
      </div>
    </div>
  )
}
