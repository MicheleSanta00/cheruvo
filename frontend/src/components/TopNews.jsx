import { useState } from 'react'
import { useLang } from '../LangContext.jsx'
import Icon from './Icon.jsx'

/**
 * Flusso notizie in tabella densa.
 *
 * Prima erano schede affiancate: belle ma dispersive, e con poche notizie per
 * schermata. Un terminale mette le righe una sotto l'altra, con l'ora a
 * sinistra e il punteggio allineato a destra, così l'occhio scorre in colonna.
 * La barretta sotto al titolo dà l'intensità senza aggiungere un altro numero.
 */
const PAGINA = 12
const LIBERE = 5   // quante ne vede un utente Free prima dell'invito a Pro

const numStyle = { fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums', fontWeight: 700 }
const colore = (v) => (v > 0.08 ? 'var(--green)' : v < -0.08 ? 'var(--red)' : 'var(--muted)')
const fmt = (v) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(Number(v)).toFixed(2)}`

export default function TopNews({ news, isPro, onUpgrade }) {
  const { t, lang } = useLang()
  const [ordine, setOrdine] = useState('recenti')   // 'recenti' | 'forti'
  const [quante, setQuante] = useState(PAGINA)
  const it = lang === 'it'

  const elenco = [...news].sort((a, b) =>
    ordine === 'recenti'
      ? new Date(b.published_date) - new Date(a.published_date)
      : Math.abs(b.sentiment) - Math.abs(a.sentiment)
  )

  const limite = isPro ? quante : LIBERE
  const visibili = elenco.slice(0, limite)
  const nascoste = elenco.length - visibili.length

  const ora = (d) => {
    if (!d) return '—'
    const x = new Date(d)
    if (isNaN(x)) return '—'
    const oggi = new Date().toDateString() === x.toDateString()
    return oggi
      ? x.toLocaleTimeString(it ? 'it-IT' : 'en-US', { hour: '2-digit', minute: '2-digit' })
      : x.toLocaleDateString(it ? 'it-IT' : 'en-US', { day: '2-digit', month: '2-digit' })
  }

  const th = {
    textAlign: 'left', fontSize: 9.5, letterSpacing: '.12em', textTransform: 'uppercase',
    color: 'var(--muted)', fontWeight: 700, padding: '7px 12px',
    borderBottom: '1px solid var(--border)', background: 'var(--near-black)',
    position: 'sticky', top: 0, zIndex: 1,
  }
  const td = { padding: '7px 12px', borderBottom: '1px solid var(--border)', verticalAlign: 'top', fontSize: 12.5 }

  const Filtro = ({ id, testo }) => (
    <button
      onClick={() => { setOrdine(id); setQuante(PAGINA) }}
      style={{
        padding: '3px 9px', borderRadius: 5, fontSize: 11, fontWeight: 700,
        border: '1px solid ' + (ordine === id ? 'rgba(30,92,255,0.5)' : 'var(--border-br)'),
        background: ordine === id ? 'rgba(30,92,255,0.12)' : 'transparent',
        color: ordine === id ? 'var(--azure)' : 'var(--muted)', cursor: 'pointer',
      }}
    >{testo}</button>
  )

  return (
    <div style={{ border: '1px solid var(--border-br)', borderRadius: 8, overflow: 'hidden' }}>
      {/* intestazione pannello */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, padding: '7px 12px',
        background: 'var(--near-black)', borderBottom: '1px solid var(--border)',
      }}>
        <span style={{ fontSize: 10, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--muted)', fontWeight: 700 }}>
          {it ? 'Flusso notizie' : 'News flow'}
        </span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 5, alignItems: 'center' }}>
          <Filtro id="recenti" testo={it ? 'Recenti' : 'Recent'} />
          <Filtro id="forti" testo={it ? 'Più forti' : 'Strongest'} />
          <span style={{ ...numStyle, fontSize: 10, color: 'var(--muted)', marginLeft: 4 }}>{news.length}</span>
        </div>
      </div>

      <div style={{ maxHeight: 420, overflowY: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th style={{ ...th, width: 62 }}>{it ? 'Ora' : 'Time'}</th>
              <th style={th}>{it ? 'Titolo' : 'Headline'}</th>
              <th style={{ ...th, width: 108 }}>{it ? 'Fonte' : 'Source'}</th>
              <th style={{ ...th, width: 62, textAlign: 'right' }}>Score</th>
            </tr>
          </thead>
          <tbody>
            {visibili.map((n, i) => {
              const s = Number(n.sentiment)
              return (
                <tr key={i}
                  onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(var(--rgb-contrasto), 0.03)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
                >
                  <td style={{ ...td, ...numStyle, fontWeight: 500, color: 'var(--muted)', whiteSpace: 'nowrap' }}>
                    {ora(n.published_date)}
                  </td>
                  <td style={td}>
                    <a href={n.url} target="_blank" rel="noopener noreferrer"
                      style={{ color: 'var(--white)', textDecoration: 'none' }}>
                      {n.title}
                    </a>
                    {/* intensità del giudizio, senza aggiungere un altro numero */}
                    <div style={{ height: 3, borderRadius: 2, background: 'rgba(var(--rgb-contrasto), 0.06)', marginTop: 4, overflow: 'hidden' }}>
                      <div style={{
                        height: '100%', width: `${Math.min(100, Math.abs(s) * 100)}%`,
                        background: colore(s),
                      }} />
                    </div>
                  </td>
                  <td style={{ ...td, color: 'var(--muted)', fontSize: 10.5, whiteSpace: 'nowrap' }}>
                    {(n.source || '').replace(/^GDELT · /, '')}
                  </td>
                  <td style={{ ...td, ...numStyle, textAlign: 'right', color: colore(s), whiteSpace: 'nowrap' }}>
                    {fmt(s)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>

        {/* Free: invito a Pro. Pro: carica altre. */}
        {!isPro && nascoste > 0 && (
          <button onClick={onUpgrade} style={{
            width: '100%', padding: '11px 12px', background: 'rgba(30,92,255,0.05)',
            border: 'none', borderTop: '1px solid var(--border)', cursor: 'pointer',
            color: 'var(--azure)', fontSize: 12.5, display: 'flex',
            alignItems: 'center', justifyContent: 'center', gap: 7,
          }}>
            <Icon name="lock" size={12} />
            {it ? `Altre ${nascoste} notizie con Pro` : `${nascoste} more with Pro`}
          </button>
        )}
        {isPro && nascoste > 0 && (
          <button onClick={() => setQuante((q) => q + PAGINA)} style={{
            width: '100%', padding: '9px 12px', background: 'transparent',
            border: 'none', borderTop: '1px solid var(--border)', cursor: 'pointer',
            color: 'var(--muted)', fontSize: 12,
          }}>
            {it ? `Mostra altre ${Math.min(PAGINA, nascoste)}` : `Show ${Math.min(PAGINA, nascoste)} more`}
          </button>
        )}
        {!visibili.length && (
          <div style={{ padding: 18, textAlign: 'center', color: 'var(--muted)', fontSize: 12.5 }}>
            {it ? 'Nessuna notizia nel periodo selezionato.' : 'No news in the selected period.'}
          </div>
        )}
      </div>
    </div>
  )
}
