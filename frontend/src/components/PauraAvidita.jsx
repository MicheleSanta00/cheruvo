import { useEffect, useState } from 'react'
import apiFetch from '../apiFetch.js'

/**
 * PauraAvidita.jsx — Fear & Greed Index del mercato crypto.
 *
 * Perché sta accanto al nostro sentiment e non da un'altra parte. Sono due
 * misure INDIPENDENTI dello stesso fenomeno: la loro nasce da volatilità,
 * volumi e dominanza, la nostra da come ne scrivono i giornali. Messe vicine
 * dicono qualcosa che nessuna delle due dice da sola. Se concordano, la
 * lettura è solida. Se divergono, quella divergenza è l'informazione: la
 * stampa può essere cupa mentre il mercato compra, e viceversa.
 *
 * Compare solo sulle criptovalute perché l'indice riguarda quel mercato.
 * Su un titolo azionario sarebbe un numero fuori posto.
 */

const SCALA = [
  { fino: 24,  etichetta: 'Paura estrema', colore: '#dc2626' },
  { fino: 44,  etichetta: 'Paura',         colore: '#f97316' },
  { fino: 55,  etichetta: 'Neutro',        colore: '#eab308' },
  { fino: 74,  etichetta: 'Avidità',       colore: '#84cc16' },
  { fino: 100, etichetta: 'Avidità estrema', colore: '#16a34a' },
]

export default function PauraAvidita({ sentimentNostro = null, lang = 'it' }) {
  const [d, setD] = useState(null)
  const [caricato, setCaricato] = useState(false)

  useEffect(() => {
    let vivo = true
    apiFetch('/fear-greed')
      .then((r) => { if (vivo) { setD(r?.disponibile ? r : null); setCaricato(true) } })
      .catch(() => { if (vivo) setCaricato(true) })
    return () => { vivo = false }
  }, [])

  // Finché non sappiamo, non occupiamo spazio; se la fonte è giù, spariamo del
  // tutto invece di mostrare un riquadro vuoto che sembra un guasto.
  if (!caricato || !d) return null

  const v = d.valore
  const colore = d.colore || SCALA.find(s => v <= s.fino)?.colore || 'var(--muted)'

  const freccia = (n) => n == null ? '' : n > 0 ? `▲ ${n}` : n < 0 ? `▼ ${Math.abs(n)}` : '= 0'
  const coloreVar = (n) => n == null ? 'var(--muted)' : n > 0 ? 'var(--green)' : n < 0 ? 'var(--red)' : 'var(--muted)'

  // Confronto con il nostro sentiment, che va da -1 a +1: lo portiamo sulla
  // stessa scala 0-100 per poterli mettere sulla stessa riga.
  const nostroSu100 = sentimentNostro == null ? null
    : Math.round((sentimentNostro + 1) * 50)
  const divergenza = nostroSu100 == null ? null : nostroSu100 - v

  return (
    <div style={{
      border: '1px solid var(--border-br)', borderRadius: 8,
      overflow: 'hidden', marginBottom: 16,
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10, padding: '7px 12px',
        background: 'var(--near-black)', borderBottom: '1px solid var(--border)',
      }}>
        <span style={{
          fontSize: 10, letterSpacing: '.12em', textTransform: 'uppercase',
          color: 'var(--muted)', fontWeight: 700,
        }}>
          {lang === 'it' ? 'Paura e avidità del mercato' : 'Market fear & greed'}
        </span>
        {/* Attribuzione accanto al dato: alternative.me non la impone, ma
            regalano un servizio e costa una riga. */}
        <a href="https://alternative.me/crypto/fear-and-greed-index/"
           target="_blank" rel="noreferrer"
           style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--muted)' }}>
          alternative.me
        </a>
      </div>

      <div style={{ padding: '12px 14px' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 10 }}>
          <span style={{
            fontFamily: 'var(--mono)', fontSize: 30, fontWeight: 700,
            fontVariantNumeric: 'tabular-nums', color: colore, lineHeight: 1,
          }}>{v}</span>
          <span style={{ fontSize: 13, fontWeight: 700, color: colore }}>{d.etichetta}</span>
          <span style={{ marginLeft: 'auto', display: 'flex', gap: 14, fontSize: 11 }}>
            <span style={{ color: 'var(--muted)' }}>
              {lang === 'it' ? 'ieri' : 'yesterday'}{' '}
              <span style={{ fontFamily: 'var(--mono)', fontWeight: 700, color: coloreVar(d.vs_ieri) }}>
                {freccia(d.vs_ieri)}
              </span>
            </span>
            <span style={{ color: 'var(--muted)' }}>
              {lang === 'it' ? 'settimana' : 'week'}{' '}
              <span style={{ fontFamily: 'var(--mono)', fontWeight: 700, color: coloreVar(d.vs_settimana) }}>
                {freccia(d.vs_settimana)}
              </span>
            </span>
          </span>
        </div>

        {/* Barra 0-100 coi cinque tratti della scala, e i due indicatori sopra */}
        <div style={{ position: 'relative', marginBottom: 6 }}>
          <div style={{ display: 'flex', height: 6, borderRadius: 3, overflow: 'hidden' }}>
            {SCALA.map((s, i) => (
              <div key={s.etichetta} style={{
                flex: i === 0 ? 25 : s.fino - SCALA[i - 1].fino,
                background: s.colore, opacity: 0.35,
              }} />
            ))}
          </div>
          {/* Indicatore del mercato */}
          <div title={`Mercato: ${v} (${d.etichetta})`} style={{
            position: 'absolute', top: -3, left: `${v}%`, transform: 'translateX(-50%)',
            width: 3, height: 12, background: colore, borderRadius: 2,
            boxShadow: '0 0 0 2px var(--black)',
          }} />
          {/* Indicatore del NOSTRO sentiment sulle notizie, se lo abbiamo */}
          {nostroSu100 != null && (
            <div title={`Notizie: ${sentimentNostro.toFixed(3)}`} style={{
              position: 'absolute', top: -3, left: `${Math.max(0, Math.min(100, nostroSu100))}%`,
              transform: 'translateX(-50%)',
              width: 3, height: 12, background: 'var(--azure)', borderRadius: 2,
              boxShadow: '0 0 0 2px var(--black)',
            }} />
          )}
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between',
                      fontSize: 9.5, color: 'var(--muted)', fontFamily: 'var(--mono)' }}>
          <span>0 {lang === 'it' ? 'paura' : 'fear'}</span>
          <span>100 {lang === 'it' ? 'avidità' : 'greed'}</span>
        </div>

        {/* La riga che rende utile il confronto: non i due numeri, ma la loro
            distanza. È l'unica cosa che nessuno dei due dice da solo. */}
        {divergenza != null && Math.abs(divergenza) >= 12 && (
          <div style={{
            marginTop: 10, paddingTop: 9, borderTop: '1px solid var(--border)',
            fontSize: 11.5, lineHeight: 1.5, color: 'var(--off-white)',
          }}>
            <span style={{ color: 'var(--azure)', fontWeight: 700 }}>
              {lang === 'it' ? 'Divergenza. ' : 'Divergence. '}
            </span>
            {lang === 'it'
              ? (divergenza > 0
                  ? 'Le notizie sono più ottimiste di quanto lo sia il mercato.'
                  : 'Le notizie sono più cupe di quanto lo sia il mercato.')
              : (divergenza > 0
                  ? 'The press is more optimistic than the market.'
                  : 'The press is gloomier than the market.')}
          </div>
        )}
      </div>
    </div>
  )
}
