import { createContext, useContext, useState } from 'react'
import { translations } from './translations.js'

const LangContext = createContext()

export function LangProvider({ children }) {
  const [lang, setLang] = useState('it') // italiano di default
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