import { useState, useCallback } from 'react'
import apiFetch from '../apiFetch.js'

export function useFinData() {
  const [tickerInfo, setTickerInfo]   = useState(null)
  const [news, setNews]               = useState([])
  const [stats, setStats]             = useState(null)
  const [prices, setPrices]           = useState([])
  const [mercato, setMercato]         = useState(null)   // stato borsa (solo vista Oggi)
  const [sentiment, setSentiment]     = useState([])
  const [loading, setLoading]         = useState(false)
  const [fetching, setFetching]       = useState(false)
  const [error, setError]             = useState(null)
  const BASE = import.meta.env.VITE_API_BASE 
  || 'https://financial-sentiment-analysis-20px.onrender.com/api'

  const load = useCallback(async (ticker, days = 30, period = '3mo') => {
    setLoading(true)
    setError(null)
    let newsCount = 0
    let failed = null
    try {
      // Validate ticker
      const vData = await apiFetch(`/validate/${ticker}`)
      setTickerInfo(vData)

      // News + stats
      const nData = await apiFetch(`/news/${ticker}?days=${days}`)
      const items = nData.news || []
      newsCount = items.length
      setNews(items)
      setStats({
        total:   nData.total,
        avg:     nData.avg_sentiment,
        max:     nData.max_sentiment,
        min:     nData.min_sentiment,
        sources: nData.sources_count,
      })

      // Prices
      try {
        const pData = await apiFetch(`/prices/${ticker}?period=${period}`)
        setPrices(pData.prices || [])
        // Sulla vista "Oggi" il backend allega anche lo stato della borsa:
        // serve a sapere se continuare ad aggiornare e a scrivere l'ora vera
        // dell'ultimo scambio accanto al prezzo.
        setMercato(pData.mercato || null)
      } catch (e) {
        // Il periodo potrebbe essere PRO-only — non bloccare il resto
        if (!e.message.includes('PRO')) throw e
        setPrices([])
        setMercato(null)
      }

      // Daily sentiment
      const sData = await apiFetch(`/sentiment/${ticker}`)
      setSentiment(sData.sentiment || [])

    } catch (e) {
      failed = e.message
      setError(e.message)
    } finally {
      setLoading(false)
    }
    // Chi chiama usa newsCount per capire se l'archivio era vuoto e, in quel
    // caso, far partire il fetch al volo invece di mostrare una pagina vuota.
    return { newsCount, error: failed }
  }, [])

  const triggerFetch = useCallback(async (ticker) => {
    setFetching(true)
    try {
      await apiFetch(`/fetch/${ticker}`, { method: 'POST' })
    } catch (e) {
      // Non bloccare l'UI per un errore di fetch in background
      console.error('triggerFetch error:', e.message)
    } finally {
      setFetching(false)
    }
  }, [])

  // Ricarica SOLO i prezzi. Serve alla vista "Oggi", che si aggiorna ogni
  // minuto: rifare tutto il giro (validate, news, statistiche, sentiment)
  // sessanta volte all'ora sarebbe assurdo, perché quelle cose cambiano al
  // massimo una volta ogni sei ore. E niente setLoading: lo spinner che
  // lampeggia in faccia ogni minuto darebbe l'idea di un'app che arranca,
  // mentre il punto è che si aggiorni senza farsi notare.
  const refreshPrezzi = useCallback(async (ticker, period) => {
    try {
      const pData = await apiFetch(`/prices/${ticker}?period=${period}`)
      setPrices(pData.prices || [])
      setMercato(pData.mercato || null)
      return pData.mercato || null
    } catch (_) {
      return null   // silenzioso: se un giro salta, riproverà il prossimo
    }
  }, [])

  return { tickerInfo, news, stats, prices, mercato, sentiment, loading, fetching,
           error, load, triggerFetch, setFetching, refreshPrezzi }
}