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
 *
 * Perché è chiuso di default. Nella prima versione era un riquadro alto quasi
 * duecento pixel fra le metriche e il grafico, e su un portatile spingeva il
 * grafico sotto la piega dello schermo. Ma il grafico è il motivo per cui uno
 * apre Cheruvo: l'indice è un contorno, e un contorno non può occupare il
 * posto della portata principale. Da chiuso dice comunque le tre cose che
 * contano (numero, etichetta, divergenza) su una riga sola, e chi vuole il
 * resto lo apre.
 */

const CHIAVE_APERTO = 'cheruvo:fng:aperto'

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
  // La scelta di tenerlo aperto resta: chi guarda l'indice tutti i giorni non
  // deve riaprirlo a ogni caricamento, e chi non lo guarda non se lo ritrova
  // più fra i piedi.
  const [aperto, setAperto] = useState(() => {
    try { return window.localStorage.getItem(CHIAVE_APERTO) === '1' } catch { return false }
  })
  const cambiaAperto = () => {
    setAperto((v) => {
      try { window.localStorage.setItem(CHIAVE_APERTO, v ? '0' : '1') } catch { /* incognito */ }
      return !v
    })
  }

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

  const mostraDivergenza = divergenza != null && Math.abs(divergenza) >= 12
  const testoDivergenza = !mostraDivergenza ? null : lang === 'it'
    ? (divergenza > 0 ? 'Notizie più ottimiste del mercato.'
                      : 'Notizie più cupe del mercato.')
    : (divergenza > 0 ? 'Press more optimistic than the market.'
                      : 'Press gloomier than the market.')

  // La barra 0-100 coi due indicatori sopra. Vive in due posti (riga chiusa e
  // riquadro aperto) con altezze diverse, quindi sta in una funzione invece
  // che copiata: due copie divergono al primo ritocco.
  const barra = (alta) => (
    <div style={{ position: 'relative', flex: alta ? 'none' : 1,
                  minWidth: alta ? 0 : 90, maxWidth: alta ? 'none' : 190 }}>
      <div style={{ display: 'flex', height: alta ? 6 : 4,
                    borderRadius: 3, overflow: 'hidden' }}>
        {SCALA.map((s, i) => (
          <div key={s.etichetta} style={{
            flex: i === 0 ? 25 : s.fino - SCALA[i - 1].fino,
            background: s.colore, opacity: 0.35,
          }} />
        ))}
      </div>
      <div title={`Mercato: ${v} (${d.etichetta})`} style={{
        position: 'absolute', top: alta ? -3 : -2, left: `${v}%`,
        transform: 'translateX(-50%)',
        width: 3, height: alta ? 12 : 8, background: colore, borderRadius: 2,
        boxShadow: '0 0 0 2px var(--black)',
      }} />
      {nostroSu100 != null && (
        <div title={`Notizie: ${sentimentNostro.toFixed(3)}`} style={{
          position: 'absolute', top: alta ? -3 : -2,
          left: `${Math.max(0, Math.min(100, nostroSu100))}%`,
          transform: 'translateX(-50%)',
          width: 3, height: alta ? 12 : 8, background: 'var(--azure)', borderRadius: 2,
          boxShadow: '0 0 0 2px var(--black)',
        }} />
      )}
    </div>
  )

  return (
    <div style={{
      border: '1px solid var(--border-br)', borderRadius: 8,
      overflow: 'hidden', marginBottom: 12,
    }}>
      {/* ── La riga sempre visibile ──────────────────────────────────────
          Tutta l'informazione essenziale su 44 pixel invece di 180: quanto
          vale, come si chiama, dove sta sulla scala e se diverge dalle
          notizie. È cliccabile su tutta la larghezza, non solo sulla
          freccetta, perché una zona di tocco larga un centimetro è un
          bersaglio che si prende anche col pollice. */}
      <div role="button" tabIndex={0} onClick={cambiaAperto}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); cambiaAperto() } }}
        title={aperto ? 'Comprimi' : 'Espandi: ieri, settimana e scala completa'}
        style={{
          display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px',
          background: 'var(--near-black)', cursor: 'pointer',
          borderBottom: aperto ? '1px solid var(--border)' : 'none',
        }}>
        {/* Da chiuso la riga È il riquadro, quindi porta tutto il contenuto.
            Da aperto diventa una semplice intestazione: ripetere qui numero,
            barra e divergenza li farebbe comparire due volte a schermo, a
            venti pixel di distanza. */}
        {aperto ? (
          <span style={{
            fontSize: 10, letterSpacing: '.12em', textTransform: 'uppercase',
            color: 'var(--muted)', fontWeight: 700,
          }}>
            {lang === 'it' ? 'Paura e avidità del mercato' : 'Market fear & greed'}
          </span>
        ) : (
          <>
            <span style={{
              fontFamily: 'var(--mono)', fontSize: 17, fontWeight: 700,
              fontVariantNumeric: 'tabular-nums', color: colore, lineHeight: 1,
            }}>{v}</span>
            <span style={{ fontSize: 11.5, fontWeight: 700, color: colore }}>{d.etichetta}</span>
            {barra(false)}
            {testoDivergenza && (
              <span style={{ fontSize: 11, color: 'var(--off-white)',
                             overflow: 'hidden', textOverflow: 'ellipsis',
                             whiteSpace: 'nowrap' }}>
                <span style={{ color: 'var(--azure)', fontWeight: 700 }}>
                  {lang === 'it' ? 'Divergenza. ' : 'Divergence. '}
                </span>
                {testoDivergenza}
              </span>
            )}
          </>
        )}
        <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor"
             strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
             style={{ marginLeft: 'auto', flexShrink: 0, color: 'var(--muted)',
                      transform: aperto ? 'rotate(180deg)' : 'none',
                      transition: 'transform .18s ease' }}>
          <path d="M3 6l5 5 5-5"/>
        </svg>
      </div>

      {aperto && (
      <div style={{ padding: '12px 14px' }}>
        {/* Attribuzione accanto al dato: alternative.me non la impone, ma
            regalano un servizio e costa una riga. */}
        <div style={{ display: 'flex', marginBottom: 10 }}>
          <a href="https://alternative.me/crypto/fear-and-greed-index/"
             target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}
             style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--muted)' }}>
            alternative.me
          </a>
        </div>
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

        {/* Stessa barra della riga chiusa, ma alta: qui c'è spazio. */}
        <div style={{ marginBottom: 6 }}>{barra(true)}</div>

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
      )}
    </div>
  )
}
