import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { LangProvider } from './LangContext.jsx'
import App from './App.jsx'
import CookieBanner from './components/CookieBanner.jsx'
import './index.css'
import { initAnalytics } from './analytics.js'

initAnalytics()   // parte solo se il consenso è già stato dato (vedi analytics.js)

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <LangProvider>
      <App />
      <CookieBanner />
    </LangProvider>
  </StrictMode>
)
