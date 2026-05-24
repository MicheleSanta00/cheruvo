import { useState, useCallback } from 'react'

const BASE = 'https://financial-sentiment-analysis-20px.onrender.com/api'

export function useFinData() {
  const [tickerInfo, setTickerInfo]   = useState(null)
  const [news, setNews]               = useState([])
  const [stats, setStats]             = useState(null)
  const [prices, setPrices]           = useState([])
  const [sentiment, setSentiment]     = useState([])
  const [loading, setLoading]         = useState(false)
  const [fetching, setFetching]       = useState(false)
  const [error, setError]             = useState(null)

  const load = useCallback(async (ticker, days = 30, period = '3mo') => {
    setLoading(true)
    setError(null)
    try {
      // Validate ticker
      const vRes = await fetch(`${BASE}/validate/${ticker}`)
      if (!vRes.ok) throw new Error(`Ticker "${ticker}" non trovato`)
      const vData = await vRes.json()
      setTickerInfo(vData)

      // News + stats
      const nRes = await fetch(`${BASE}/news/${ticker}?days=${days}`)
      const nData = await nRes.json()
      setNews(nData.news || [])
      setStats({
        total:        nData.total,
        avg:          nData.avg_sentiment,
        max:          nData.max_sentiment,
        min:          nData.min_sentiment,
        sources:      nData.sources_count,
      })

      // Prices
      const pRes = await fetch(`${BASE}/prices/${ticker}?period=${period}`)
      if (pRes.ok) {
        const pData = await pRes.json()
        setPrices(pData.prices || [])
      }

      // Daily sentiment
      const sRes = await fetch(`${BASE}/sentiment/${ticker}`)
      if (sRes.ok) {
        const sData = await sRes.json()
        setSentiment(sData.sentiment || [])
      }

    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  const triggerFetch = useCallback(async (ticker) => {
    setFetching(true)
    try {
      await fetch(`${BASE}/fetch/${ticker}`, { method: 'POST' })
    } finally {
      setFetching(false)
    }
  }, [])

  return { tickerInfo, news, stats, prices, sentiment, loading, fetching, error, load, triggerFetch }
}
