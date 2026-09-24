import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { LangProvider } from './LangContext.jsx'
import App, { applicaTemaSalvato } from './App.jsx'
import CookieBanner from './components/CookieBanner.jsx'
// I caratteri stanno nel bundle e non su Google (24 settembre 2026).
//
// Prima arrivavano da fonts.googleapis.com: ogni visita passava a Google
// l'indirizzo IP del visitatore, senza consenso e senza una riga
// nell'informativa. Un tribunale tedesco (LG München, 20 gennaio 2022) lo ha
// già giudicato una violazione del GDPR. Serviti da noi costano lo stesso
// peso e tolgono una richiesta a un dominio esterno. Il 700 non c'era: il
// grassetto usato ovunque nell'interfaccia veniva inventato dal browser.
import '@fontsource/dm-sans/300.css'
import '@fontsource/dm-sans/400.css'
import '@fontsource/dm-sans/500.css'
import '@fontsource/dm-sans/700.css'
import '@fontsource/dm-sans/300-italic.css'
import '@fontsource/dm-serif-display/400.css'
import '@fontsource/dm-serif-display/400-italic.css'
import './index.css'
import { initAnalytics } from './analytics.js'

// Il tema va applicato PRIMA che React disegni qualcosa: se lo facessimo
// dentro un componente, chi usa il tema chiaro vedrebbe un lampo nero a ogni
// caricamento della pagina.
applicaTemaSalvato()

initAnalytics()   // parte solo se il consenso è già stato dato (vedi analytics.js)

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <LangProvider>
      <App />
      <CookieBanner />
    </LangProvider>
  </StrictMode>
)
