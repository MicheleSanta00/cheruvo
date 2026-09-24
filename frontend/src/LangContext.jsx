import { createContext, useContext, useEffect, useState } from 'react'
import { translations } from './translations.js'

const LangContext = createContext()

export function LangProvider({ children }) {
  // Inglese di default dal 18 agosto 2026. Il traffico che arriva non e'
  // italiano: i post che portano gente stanno su r/datasets, r/algotrading e
  // Hacker News, e chi apre il sito da li' trovava una schermata in italiano.
  // Il bottone della lingua resta, chi vuole l'italiano lo sceglie.
  // ...ma un link può dire in che lingua aprirsi.
  //
  // Il 20 settembre 2026, preparando dei post in italiano, è saltato fuori che
  // chi li avesse cliccati sarebbe atterrato su una schermata in inglese e
  // avrebbe dovuto cercare il bottone della lingua. Chiedere a un visitatore
  // di fare un passo prima di capire cosa sta guardando è il modo più veloce
  // di perderlo, e vale il doppio per chi arriva da un post nella sua lingua.
  //
  // `?lang=it` risolve senza toccare il default: l'inglese resta per tutti
  // quelli che arrivano da Hacker News o r/datasets, l'italiano si sceglie nel
  // link. Un valore sconosciuto viene ignorato invece di rompere la pagina.
  const [lang, setLang] = useState(() => {
    try {
      const scelta = new URLSearchParams(window.location.search).get('lang')
      if (scelta && translations[scelta]) return scelta
    } catch { /* niente window o query illeggibile: resta il default */ }
    return 'en'
  })
  const t = translations[lang]
  const toggleLang = () => setLang(l => l === 'it' ? 'en' : 'it')

  // La lingua della pagina segue quella scelta. index.html dice "it" in
  // modo fisso, mentre l'app parte in inglese: lettori di schermo e
  // traduttori del browser leggevano un testo inglese come se fosse italiano.
  useEffect(() => {
    try { document.documentElement.lang = lang } catch { /* niente document */ }
  }, [lang])

  return (
    <LangContext.Provider value={{ lang, t, toggleLang }}>
      {children}
    </LangContext.Provider>
  )
}

export function useLang() {
  return useContext(LangContext)
}