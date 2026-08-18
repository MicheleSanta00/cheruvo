import { createContext, useContext, useState } from 'react'
import { translations } from './translations.js'

const LangContext = createContext()

export function LangProvider({ children }) {
  // Inglese di default dal 18 agosto 2026. Il traffico che arriva non e'
  // italiano: i post che portano gente stanno su r/datasets, r/algotrading e
  // Hacker News, e chi apre il sito da li' trovava una schermata in italiano.
  // Il bottone della lingua resta, chi vuole l'italiano lo sceglie.
  const [lang, setLang] = useState('en')
  const t = translations[lang]
  const toggleLang = () => setLang(l => l === 'it' ? 'en' : 'it')

  return (
    <LangContext.Provider value={{ lang, t, toggleLang }}>
      {children}
    </LangContext.Provider>
  )
}

export function useLang() {
  return useContext(LangContext)
}