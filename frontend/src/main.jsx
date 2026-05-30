import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { LangProvider } from './LangContext.jsx'
import App from './App.jsx'
import './index.css'
import { initAnalytics } from './analytics.js'

initAnalytics()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <LangProvider>
      <App />
    </LangProvider>
  </StrictMode>
)