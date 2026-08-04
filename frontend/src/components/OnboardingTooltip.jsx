import { useState, useEffect } from 'react'
import Icon from './Icon.jsx'

const STEPS = [
  {
    // Era 'sidebar-search'. Col passaggio all'interfaccia a terminale la
    // ricerca si è spostata dalla colonna di sinistra alla barra in alto, e
    // questo primo passo puntava a un elemento che non esiste più: il fumetto
    // restava incollato nell'angolo in alto a sinistra indicando il nulla.
    // Era la primissima cosa che vedeva un utente nuovo.
    target: 'header-search',
    icon: 'search',
    title: 'Cerca un\'azione',
    desc: 'Scrivi il simbolo di qualsiasi azione, americana o europea. Es: NVDA, AAPL, ENI.MI, ENEL.MI',
    position: 'bottom',
  },
  {
    target: 'kpi-avg',
    icon: 'score',
    title: 'Cos\'è il sentiment score?',
    desc: 'È un numero da −1 a +1 che misura l\'umore del mercato su quell\'azione. Vicino a +1 = ottimismo, vicino a −1 = pessimismo.',
    position: 'right',
  },
  {
    target: 'chart-area',
    icon: 'charts',
    title: 'Il grafico nel tempo',
    desc: 'Vedi come cambia il sentiment giorno per giorno sovrapposto al prezzo reale. Se il sentiment sale prima del prezzo, potresti coglierlo in anticipo.',
    position: 'top',
  },
  {
    target: 'top-news',
    icon: 'news',
    title: 'Le notizie più impattanti',
    desc: 'Le notizie più rialziste e ribassiste del momento, con il loro score. Clicca per leggere l\'articolo originale.',
    position: 'top',
  },
]

const isMobile = () => typeof window !== 'undefined' && window.innerWidth <= 640

export default function OnboardingTooltip({ hasData }) {
  const [step, setStep]       = useState(0)
  const [visible, setVisible] = useState(false)
  const [waiting, setWaiting] = useState(false)   // "Ho capito" premuto: in attesa del primo ticker
  const [pos, setPos]         = useState({ top: 0, left: 0 })
  const [mobile]              = useState(isMobile)   // su mobile i tooltip vanno centrati

  useEffect(() => {
    if (localStorage.getItem('cheruvo_onboarded')) return
    // Mostra subito il primo step (ricerca ticker)
    setVisible(true)
  }, [])

  useEffect(() => {
    // Quando arrivano i dati e siamo ancora allo step 0, il tour riprende dal passo 2
    // (anche se l'utente aveva premuto "Ho capito" ed era in attesa)
    if (hasData && step === 0) {
      setWaiting(false)
      setStep(1)
      return
    }
    if (step > 0 && !hasData) return
    if (!mobile) updatePosition()
  }, [step, hasData])

  // Mentre il tour è a schermo, nascondi il pulsante flottante della chat AI
  // (altrimenti si sovrappone al tasto "Avanti" del tooltip, soprattutto su mobile).
  useEffect(() => {
    const shown = visible && !(waiting && step === 0)
    document.body.classList.toggle('onboarding-active', shown)
    return () => document.body.classList.remove('onboarding-active')
  }, [visible, waiting, step])

  const updatePosition = () => {
    const current = STEPS[step]
    const el = document.getElementById(current.target)
    // Bersaglio sparito: il tour si chiude invece di restare appeso
    // nell'angolo. Prima usciva senza fare niente, e il fumetto rimaneva
    // fermo alle coordinate iniziali, cioè in alto a sinistra sopra il vuoto.
    // Meglio nessun tour che un tour che indica il nulla.
    if (!el) {
      console.warn(`[onboarding] elemento "${current.target}" non trovato: tour interrotto`)
      finish()
      return
    }
    const rect = el.getBoundingClientRect()
    const scrollY = window.scrollY

    if (current.position === 'right') {
      setPos({ top: rect.top + scrollY + rect.height / 2, left: rect.right + 16 })
    } else if (current.position === 'bottom') {
      setPos({ top: rect.bottom + scrollY + 12, left: rect.left + rect.width / 2 })
    } else {
      setPos({ top: rect.top + scrollY - 8, left: rect.left + rect.width / 2 })
    }
  }

  const next = () => {
    if (step < STEPS.length - 1) {
      const nextStep = step + 1
      // Se il prossimo step richiede dati e non ci sono, salta fino al primo step senza dati
      if (nextStep >= 1 && !hasData) {
        // Rimani sul tooltip attuale ma aggiorna il messaggio
        setStep(0)
        return
      }
      // Su desktop: se il target non esiste, chiudi. Su mobile i tooltip sono
      // centrati e non dipendono dagli elementi, quindi non serve il controllo.
      if (!mobile) {
        const el = document.getElementById(STEPS[nextStep].target)
        if (!el) { finish(); return }
      }
      setStep(nextStep)
    } else {
      finish()
    }
  }

  const finish = () => {
    setVisible(false)
    localStorage.setItem('cheruvo_onboarded', '1')
  }

  // In attesa: l'utente ha capito il primo passo, il tour riprenderà col primo ticker
  if (!visible || (waiting && step === 0)) return null

  const current = STEPS[step]
  const isRight = current.position === 'right'

  return (
    <>
      {/* Overlay scuro semi-trasparente (su mobile sempre attivo per mettere a fuoco) */}
      <div
        onClick={(mobile || step > 0) ? finish : undefined}
        style={{
          position: 'fixed', inset: 0, zIndex: 998,
          background: (mobile || step > 0) ? 'rgba(0,0,0,0.55)' : 'transparent',
          backdropFilter: (mobile || step > 0) ? 'blur(1px)' : 'none',
          pointerEvents: (mobile || step > 0) ? 'all' : 'none',
        }}
      />

      {/* Tooltip — ancorato all'elemento su desktop, centrato in basso su mobile */}
      <div style={mobile ? {
        position: 'fixed', left: 12, right: 12, bottom: 20, zIndex: 999,
        background: 'var(--near-black)', border: '1px solid rgba(30,92,255,0.4)', borderRadius: 16,
        padding: '18px 20px', boxShadow: '0 8px 40px rgba(0,0,0,0.6)', pointerEvents: 'all',
      } : {
        position: 'absolute',
        top: pos.top,
        left: pos.left,
        zIndex: 999,
        transform: isRight ? 'translateY(-50%)' : 'translate(-50%, -100%)',
        maxWidth: 280,
        background: 'var(--near-black)',
        border: '1px solid rgba(30,92,255,0.4)',
        borderRadius: 14,
        padding: '16px 18px',
        boxShadow: '0 8px 40px rgba(0,0,0,0.6), 0 0 0 1px rgba(30,92,255,0.15)',
        pointerEvents: 'all',
      }}>
        {/* Freccia (solo desktop) */}
        {!mobile && isRight && (
          <div style={{
            position: 'absolute', left: -8, top: '50%', transform: 'translateY(-50%)',
            width: 0, height: 0,
            borderTop: '8px solid transparent',
            borderBottom: '8px solid transparent',
            borderRight: '8px solid rgba(30,92,255,0.4)',
          }} />
        )}
        {!mobile && !isRight && (
          <div style={{
            position: 'absolute', bottom: -8, left: '50%', transform: 'translateX(-50%)',
            width: 0, height: 0,
            borderLeft: '8px solid transparent',
            borderRight: '8px solid transparent',
            borderTop: '8px solid rgba(30,92,255,0.4)',
          }} />
        )}

        {/* Indicatore step */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 12 }}>
          {STEPS.map((_, i) => (
            <div key={i} style={{
              height: 3, flex: 1, borderRadius: 2,
              background: i <= step ? 'var(--blue)' : 'rgba(var(--rgb-contrasto), 0.1)',
              transition: 'background .3s',
            }} />
          ))}
        </div>

        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, letterSpacing: '-.01em', display: 'flex', alignItems: 'center', gap: 7 }}>
          <Icon name={current.icon} size={16} color="var(--azure)" /> {current.title}
        </div>
        <div style={{ fontSize: 13, color: 'var(--off-white)', lineHeight: 1.65, marginBottom: 16 }}>
          {current.desc}
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
          <button
            onClick={finish}
            style={{ fontSize: 12, color: 'var(--muted)', background: 'transparent', border: 'none', cursor: 'pointer', flexShrink: 0 }}
          >
            Salta
          </button>
          <button
            onClick={step === 0 ? () => setWaiting(true) : next}
            style={{
              fontSize: 13, fontWeight: 500, color: 'white',
              background: 'var(--blue)', border: 'none',
              borderRadius: 8, padding: '7px 18px', cursor: 'pointer', whiteSpace: 'nowrap',
            }}
          >
            {step === 0 ? 'Ho capito' : step < STEPS.length - 1 ? 'Avanti' : 'Inizia'}
          </button>
        </div>
      </div>
    </>
  )
}
