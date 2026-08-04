import { useLang } from '../LangContext.jsx'
import LogoCrypto, { eCrypto } from './LogoCrypto.jsx'

/**
 * Colonna destra con le classifiche di mercato, sempre visibile.
 *
 * In un terminale il contesto non sparisce quando apri un titolo: continui a
 * vedere come si muove il resto. Prima queste classifiche stavano dietro un
 * bottone "Mercato", quindi erano un posto dove andare invece che qualcosa
 * che hai sempre sott'occhio.
 */
const TXT = {
  it: { bulls: 'Più rialzisti', bears: 'Più ribassisti', cover: 'Copertura',
        tickers: 'Titoli seguiti', news: 'Notizie totali', today: 'Ultime 24 ore',
        ranked: 'In classifica', empty: 'Dati in aggiornamento' },
  en: { bulls: 'Most bullish', bears: 'Most bearish', cover: 'Coverage',
        tickers: 'Stocks tracked', news: 'Total news', today: 'Last 24 hours',
        ranked: 'In ranking', empty: 'Data updating' },
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
  const rialzisti = righe.filter((r) => r.sentiment > 0).slice(0, 6)
  const ribassisti = righe.filter((r) => r.sentiment <= 0).slice(-5).reverse()

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

  const Riga = ({ r, i }) => (
    <button
      onClick={() => onPick?.(r.ticker)}
      style={{
        display: 'grid', gridTemplateColumns: '16px 1fr auto auto', gap: 9,
        alignItems: 'center', width: '100%', padding: '6px 12px',
        background: attivo === r.ticker ? 'rgba(30,92,255,0.10)' : 'transparent',
        border: 'none', borderBottom: '1px solid var(--border)', borderRadius: 0,
        color: 'var(--white)', cursor: 'pointer', textAlign: 'left', fontSize: 12.5,
      }}
      onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(var(--rgb-contrasto), 0.04)' }}
      onMouseLeave={(e) => { e.currentTarget.style.background = attivo === r.ticker ? 'rgba(30,92,255,0.10)' : 'transparent' }}
    >
      <span style={{ ...numStyle, fontWeight: 500, fontSize: 10, color: 'var(--muted)' }}>{i + 1}</span>
      <span style={{ fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: 5 }}>
        {eCrypto(r.ticker) && <LogoCrypto ticker={r.ticker} size={14} />}
        {eCrypto(r.ticker) ? r.ticker.replace('-USD', '') : r.ticker}
      </span>
      <span style={{ fontSize: 10, color: 'var(--muted)' }}>{r.news}n</span>
      <span style={{ ...numStyle, fontSize: 12, color: colore(r.sentiment) }}>{fmt(r.sentiment)}</span>
    </button>
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

      {righe.length > 0 && (
        <>
          <Intestazione testo={s.bulls} extra={rialzisti.length} />
          {rialzisti.map((r, i) => <Riga key={r.ticker} r={r} i={i} />)}

          <Intestazione testo={s.bears} extra={ribassisti.length} />
          {ribassisti.map((r, i) => <Riga key={r.ticker} r={r} i={i} />)}
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
