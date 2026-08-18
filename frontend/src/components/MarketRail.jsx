import { useLang } from '../LangContext.jsx'
import LogoCrypto, { eCrypto } from './LogoCrypto.jsx'
import { fasce } from '../utils/incertezza.js'

/**
 * Colonna destra con le classifiche di mercato, sempre visibile.
 *
 * In un terminale il contesto non sparisce quando apri un titolo: continui a
 * vedere come si muove il resto. Prima queste classifiche stavano dietro un
 * bottone "Mercato", quindi erano un posto dove andare invece che qualcosa
 * che hai sempre sott'occhio.
 *
 * NIENTE PIU' NUMERI DI POSIZIONE
 *
 * Fino al 18 agosto 2026 qui c'era 1, 2, 3... accanto a ogni titolo. Quel
 * numero era falso: misurando la classifica vera di quel giorno, nessuna
 * delle 25 coppie adiacenti era distinguibile, e per renderle tali
 * servirebbero in mediana 7.938 notizie per titolo ogni 48 ore contro le 23
 * che ci sono. Non e' un problema di volume da colmare, e' un ordine che non
 * esiste.
 *
 * Quello che i dati reggono sono le FASCE (vedi `fasce` in incertezza.js):
 * dentro una fascia l'ordine e' casuale e non si mostra, fra una fascia e
 * l'altra la differenza esclude lo zero. Qui si mostrano la prima e
 * l'ultima, che sono le due che rispondono alla domanda "cosa sale e cosa
 * scende", e si dice quanti titoli stanno in mezzo senza distinguersi.
 *
 * Se in un giorno nessuna fascia si separa, la colonna lo scrive invece di
 * mostrare un ordine inventato.
 */
const TXT = {
  it: { bulls: 'Fascia alta', bears: 'Fascia bassa', cover: 'Copertura',
        tickers: 'Titoli seguiti', news: 'Notizie totali', today: 'Ultime 24 ore',
        ranked: 'In classifica', empty: 'Dati in aggiornamento',
        mezzo: (n) => `${n} in mezzo, non distinguibili`,
        piatto: 'Oggi nessuna differenza regge la misura',
        dentro: 'ordine casuale dentro la fascia' },
  en: { bulls: 'Top band', bears: 'Bottom band', cover: 'Coverage',
        tickers: 'Stocks tracked', news: 'Total news', today: 'Last 24 hours',
        ranked: 'In ranking', empty: 'Data updating',
        mezzo: (n) => `${n} in between, not distinguishable`,
        piatto: 'Nothing separates today',
        dentro: 'order inside a band is arbitrary' },
}

const numStyle = {
  fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums', fontWeight: 700,
}
const colore = (v) => (v > 0.08 ? 'var(--green)' : v < -0.08 ? 'var(--red)' : 'var(--muted)')
const fmt = (v) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(Number(v)).toFixed(2)}`

export default function MarketRail({ rows, stats, attivo, onPick }) {
  const { lang } = useLang()
  const s = TXT[lang] || TXT.it
  const righe = rows || []
  const gruppi = fasce(righe)
  const alta = gruppi[0]
  const bassa = gruppi.length > 1 ? gruppi[gruppi.length - 1] : null
  const inMezzo = gruppi.slice(1, -1).reduce((n, g) => n + g.righe.length, 0)

  const Intestazione = ({ testo, extra }) => (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '7px 12px', background: 'var(--near-black)',
      borderBottom: '1px solid var(--border)',
      position: 'sticky', top: 0, zIndex: 1,
    }}>
      <span style={{ fontSize: 10, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--muted)', fontWeight: 700 }}>{testo}</span>
      {extra != null && <span style={{ ...numStyle, fontSize: 10, color: 'var(--muted)' }}>{extra}</span>}
    </div>
  )

  // Niente indice: la posizione dentro la fascia non significa niente.
  const Riga = ({ r }) => (
    <button
      onClick={() => onPick?.(r.ticker)}
      style={{
        display: 'grid', gridTemplateColumns: '1fr auto auto', gap: 9,
        alignItems: 'center', width: '100%', padding: '6px 12px',
        background: attivo === r.ticker ? 'rgba(30,92,255,0.10)' : 'transparent',
        border: 'none', borderBottom: '1px solid var(--border)', borderRadius: 0,
        color: 'var(--white)', cursor: 'pointer', textAlign: 'left', fontSize: 12.5,
      }}
      onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(var(--rgb-contrasto), 0.04)' }}
      onMouseLeave={(e) => { e.currentTarget.style.background = attivo === r.ticker ? 'rgba(30,92,255,0.10)' : 'transparent' }}
    >
      <span style={{ fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: 5 }}>
        {eCrypto(r.ticker) && <LogoCrypto ticker={r.ticker} size={14} />}
        {eCrypto(r.ticker) ? r.ticker.replace('-USD', '') : r.ticker}
      </span>
      <span style={{ fontSize: 10, color: 'var(--muted)' }}>{r.news}n</span>
      <span style={{ ...numStyle, fontSize: 12, color: colore(r.sentiment) }}>{fmt(r.sentiment)}</span>
    </button>
  )

  // La media della fascia con la sua banda: e' il numero che regge, mentre
  // quelli dei singoli titoli dentro la fascia non si distinguono fra loro.
  const Fascia = ({ testo, g }) => (
    <>
      <Intestazione testo={testo} extra={g.righe.length} />
      <div style={{
        display: 'flex', alignItems: 'baseline', gap: 6,
        padding: '5px 12px', borderBottom: '1px solid var(--border)',
      }}>
        <span style={{ ...numStyle, fontSize: 12.5, color: colore(g.media) }}>{fmt(g.media)}</span>
        <span style={{ ...numStyle, fontSize: 10, color: 'var(--muted)' }}>
          {fmt(g.lo)} / {fmt(g.hi)}
        </span>
      </div>
      {g.righe.map((r) => <Riga key={r.ticker} r={r} />)}
    </>
  )

  const Voce = ({ etichetta, valore }) => (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 12px', fontSize: 11.5 }}>
      <span style={{ color: 'var(--muted)' }}>{etichetta}</span>
      <span style={{ ...numStyle, fontSize: 11.5 }}>{valore ?? '—'}</span>
    </div>
  )

  return (
    <aside className="market-rail" style={{
      width: 268, flexShrink: 0, borderLeft: '1px solid var(--border)',
      overflowY: 'auto', background: 'var(--black)',
    }}>
      {!righe.length && (
        <>
          <Intestazione testo={s.bulls} />
          <div style={{ padding: 14, fontSize: 12, color: 'var(--muted)' }}>{s.empty}…</div>
        </>
      )}

      {righe.length > 0 && alta && (
        <>
          <Fascia testo={s.bulls} g={alta} />

          {/* Chi sta in mezzo si conta, non si ordina. */}
          {inMezzo > 0 && (
            <div style={{
              padding: '7px 12px', fontSize: 11, color: 'var(--muted)',
              borderBottom: '1px solid var(--border)', textAlign: 'center',
            }}>
              {s.mezzo(inMezzo)}
            </div>
          )}

          {bassa && <Fascia testo={s.bears} g={bassa} />}

          {/* Il giorno in cui non si separa niente va detto, non nascosto. */}
          {!bassa && (
            <div style={{ padding: '10px 12px', fontSize: 11.5, color: 'var(--muted)' }}>
              {s.piatto}
            </div>
          )}

          <div style={{ padding: '7px 12px', fontSize: 10.5, color: 'var(--muted)' }}>
            {s.dentro}
          </div>
        </>
      )}

      <Intestazione testo={s.cover} />
      <div style={{ padding: '6px 0 12px' }}>
        <Voce etichetta={s.tickers} valore={stats?.tickers} />
        <Voce etichetta={s.news} valore={stats?.news_total?.toLocaleString(lang === 'it' ? 'it-IT' : 'en-US')} />
        <Voce etichetta={s.today} valore={stats?.news_today} />
        <Voce etichetta={s.ranked} valore={righe.length || null} />
      </div>
    </aside>
  )
}
