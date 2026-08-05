import { useState, useEffect, useCallback } from 'react'
import Icon from './Icon.jsx'

/**
 * OnboardingTooltip.jsx — Il giro guidato del primo accesso.
 *
 * Riscritto il 5 agosto 2026. La versione precedente aveva tre difetti che si
 * sommavano, e insieme facevano sembrare il tour impazzito.
 *
 * 1. POSIZIONAMENTO SBAGLIATO. Usava `position: absolute` sommando
 *    `window.scrollY` alle coordinate dell'elemento. Ma Cheruvo non fa
 *    scorrere la finestra: ha `overflow: hidden` e scorre i riquadri interni.
 *    Quindi scrollY vale sempre zero, mentre getBoundingClientRect restituisce
 *    coordinate relative allo SCHERMO. Due sistemi di riferimento diversi
 *    mescolati: il fumetto finiva ovunque tranne dove doveva.
 *    Ora è `position: fixed`, che parla la stessa lingua di
 *    getBoundingClientRect. Nessuna somma, nessuna correzione.
 *
 * 2. PASSI CHE PUNTAVANO AL NULLA. Tre dei quattro passi erano ancorati a
 *    elementi che esistono solo con un titolo aperto. Ma l'app adesso si apre
 *    sulla classifica del mercato, senza nessun titolo: quei passi non avevano
 *    bersaglio e il tour spariva a metà. Ora la sequenza si costruisce ogni
 *    volta con i soli passi il cui bersaglio esiste DAVVERO in quel momento.
 *
 * 3. SALTI AUTOMATICI. Un effetto forzava il passaggio da un passo all'altro
 *    quando arrivavano i dati, litigando con i click dell'utente. Tolto: si
 *    avanza solo premendo avanti.
 */

const PASSI = [
  {
    id: 'header-search',
    icona: 'search',
    titolo: 'Cerca una moneta',
    testo: 'Scrivi il nome o il simbolo. Da qualunque punto, Ctrl+K ti porta qui.',
  },
  {
    id: 'kpi-avg',
    icona: 'score',
    titolo: 'Il punteggio del sentiment',
    testo: 'Un numero da −1 a +1 che misura il tono delle notizie. Vicino a +1 ottimismo, vicino a −1 pessimismo.',
  },
  {
    id: 'chart-area',
    icona: 'charts',
    titolo: 'Il grafico',
    testo: 'Prezzo e sentiment sovrapposti. Con "Oggi" vedi la seduta minuto per minuto: sulle crypto si muove sempre.',
  },
  {
    id: 'top-news',
    icona: 'news',
    titolo: 'Le notizie che contano',
    testo: 'Quelle che generano il punteggio, con il loro peso. Clicca per leggere l\'originale.',
  },
]

const LARGHEZZA = 290
const MARGINE = 12

export default function OnboardingTooltip({ hasData }) {
  const [attivo, setAttivo] = useState(false)
  const [indice, setIndice] = useState(0)
  const [posizione, setPosizione] = useState(null)
  const [disponibili, setDisponibili] = useState([])

  useEffect(() => {
    try {
      if (!localStorage.getItem('cheruvo_onboarded')) setAttivo(true)
    } catch (_) { /* modalità privata */ }
  }, [])

  // Solo i passi il cui bersaglio è presente adesso. Si ricalcola quando
  // cambia lo stato dei dati, perché aprendo un titolo compaiono elementi
  // nuovi e il giro può allungarsi.
  useEffect(() => {
    if (!attivo) return
    const presenti = PASSI.filter(p => document.getElementById(p.id))
    setDisponibili(presenti)
    setIndice(i => Math.min(i, Math.max(0, presenti.length - 1)))
  }, [attivo, hasData])

  const passo = disponibili[indice]

  // Il calcolo della posizione. Coordinate dello schermo, punto. Il fumetto
  // viene messo sotto l'elemento se c'è spazio, altrimenti sopra, e non esce
  // mai dai bordi laterali.
  const calcola = useCallback(() => {
    if (!passo) return
    const el = document.getElementById(passo.id)
    if (!el) { setPosizione(null); return }
    const r = el.getBoundingClientRect()
    // Elemento fuori schermo o nascosto: niente fumetto appeso nel vuoto
    if (r.width === 0 && r.height === 0) { setPosizione(null); return }

    const sotto = r.bottom + 190 < window.innerHeight
    let left = r.left + r.width / 2 - LARGHEZZA / 2
    left = Math.max(MARGINE, Math.min(left, window.innerWidth - LARGHEZZA - MARGINE))

    setPosizione({
      top: sotto ? r.bottom + 14 : Math.max(MARGINE, r.top - 14),
      left,
      versoBasso: sotto,
      // Il riquadro luminoso attorno all'elemento indicato
      evidenzia: { top: r.top - 4, left: r.left - 4, width: r.width + 8, height: r.height + 8 },
    })
  }, [passo])

  useEffect(() => {
    if (!attivo || !passo) return
    calcola()
    // Il layout può muoversi dopo il primo calcolo (dati che arrivano, font
    // che finiscono di caricare, riquadri che si ridimensionano). Ricontrolla
    // per un attimo invece di fidarsi di una misura sola.
    const ripeti = setInterval(calcola, 400)
    const stop = setTimeout(() => clearInterval(ripeti), 3000)
    window.addEventListener('resize', calcola)
    return () => {
      clearInterval(ripeti); clearTimeout(stop)
      window.removeEventListener('resize', calcola)
    }
  }, [attivo, passo, calcola])

  const chiudi = () => {
    setAttivo(false)
    try { localStorage.setItem('cheruvo_onboarded', '1') } catch (_) {}
  }
  const avanti = () => {
    if (indice < disponibili.length - 1) setIndice(i => i + 1)
    else chiudi()
  }

  useEffect(() => {
    if (!attivo) return
    const tasto = (e) => { if (e.key === 'Escape') chiudi() }
    window.addEventListener('keydown', tasto)
    return () => window.removeEventListener('keydown', tasto)
  }, [attivo])

  if (!attivo || !passo || !posizione) return null

  const ultimo = indice === disponibili.length - 1

  return (
    <>
      {/* Velo scuro, con un buco luminoso sull'elemento indicato */}
      <div onClick={chiudi} style={{
        position: 'fixed', inset: 0, zIndex: 998,
        background: 'rgba(0,0,0,0.55)', pointerEvents: 'all',
      }} />
      <div style={{
        position: 'fixed', zIndex: 999, pointerEvents: 'none',
        borderRadius: 8, border: '1px solid var(--blue)',
        boxShadow: '0 0 0 9999px rgba(0,0,0,0.55)',
        ...posizione.evidenzia,
      }} />

      <div style={{
        position: 'fixed',
        top: posizione.top, left: posizione.left,
        transform: posizione.versoBasso ? 'none' : 'translateY(-100%)',
        width: LARGHEZZA, zIndex: 1000,
        background: 'var(--near-black)',
        border: '1px solid rgba(30,92,255,0.45)', borderRadius: 10,
        padding: '15px 17px', boxShadow: 'var(--ombra)', pointerEvents: 'all',
      }}>
        <div style={{ display: 'flex', gap: 4, marginBottom: 12 }}>
          {disponibili.map((_, i) => (
            <div key={i} style={{
              height: 3, flex: 1, borderRadius: 2,
              background: i <= indice ? 'var(--blue)' : 'rgba(var(--rgb-contrasto), 0.12)',
            }} />
          ))}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 7 }}>
          <Icon name={passo.icona} size={14} />
          <span style={{ fontSize: 14, fontWeight: 700, letterSpacing: '-.01em' }}>{passo.titolo}</span>
        </div>
        <p style={{ fontSize: 12.5, color: 'var(--muted)', lineHeight: 1.55, marginBottom: 14 }}>
          {passo.testo}
        </p>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={chiudi} style={{
            fontSize: 12, color: 'var(--muted)', background: 'transparent',
            border: 'none', cursor: 'pointer', padding: 0,
          }}>Salta</button>
          <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--muted)',
                         fontFamily: 'var(--mono)' }}>
            {indice + 1}/{disponibili.length}
          </span>
          <button onClick={avanti} className="btn-glow" style={{
            fontSize: 12.5, fontWeight: 700, color: '#fff', border: 'none',
            borderRadius: 6, padding: '7px 15px', cursor: 'pointer',
          }}>{ultimo ? 'Ho capito' : 'Avanti'}</button>
        </div>
      </div>
    </>
  )
}
