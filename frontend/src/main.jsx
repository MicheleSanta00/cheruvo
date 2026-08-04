import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { LangProvider } from './LangContext.jsx'
import App, { applicaTemaSalvato } from './App.jsx'
import CookieBanner from './components/CookieBanner.jsx'
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
