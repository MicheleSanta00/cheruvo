import { useMemo, useRef, useEffect, useState } from 'react'

export default function Chart({ prices, sentiment, ticker }) {
  const svgRef = useRef(null)
  const [size, setSize] = useState({ w: 800, h: 320 })

  useEffect(() => {
    if (!svgRef.current) return
    const ro = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect
      setSize({ w: Math.max(400, width), h: Math.max(200, height) })
    })
    ro.observe(svgRef.current.parentElement)
    return () => ro.disconnect()
  }, [])

  const { candleSvg, sentSvg, lineSvg, areaSvg } = useMemo(() => {
    if (!prices.length) return {}
    const { w, h } = size
    const padL = 8, padR = 8, padT = 10, chartH = h * 0.65, sentH = h * 0.22
    const sentBase = chartH + 22

    const allH = prices.map(p => p.High), allL = prices.map(p => p.Low)
    const minP = Math.min(...allL), maxP = Math.max(...allH)
    const n = prices.length

    const sy = v => padT + chartH * (1 - (v - minP) / (maxP - minP))
    const sx = i => padL + (i / Math.max(n - 1, 1)) * (w - padL - padR)
    const cw = Math.max(3, ((w - padL - padR) / n) * 0.55)

    // Build sentiment map by date
    const sentMap = {}
    sentiment.forEach(s => { sentMap[s.date] = s.sentiment })

    let candleSvg = '', sentSvg = '', linePath = '', aPath = ''

    prices.forEach((p, i) => {
      const x = sx(i)
      const o = sy(p.Open), cl = sy(p.Close)
      const hi = sy(p.High), lo = sy(p.Low)
      const up = p.Close >= p.Open
      const col = up ? 'var(--green)' : 'var(--red)'
      const top = Math.min(o, cl), ht = Math.max(2, Math.abs(cl - o))

      // Candle
      candleSvg += `<line x1="${x}" y1="${hi}" x2="${x}" y2="${lo}" stroke="${col}" stroke-width="1" opacity="0.5"/>`
      candleSvg += `<rect x="${x - cw / 2}" y="${top}" width="${cw}" height="${ht}" fill="${col}" rx="1"/>`

      // Sentiment bar
      const sent = sentMap[p.date] ?? 0
      const bh = Math.abs(sent) * sentH * 0.8
      const bx = x - cw / 2
      const by = sent >= 0 ? sentBase - bh : sentBase
      const bc = sent >= 0 ? 'var(--green)' : 'var(--red)'
      sentSvg += `<rect x="${bx}" y="${by}" width="${cw}" height="${bh}" fill="${bc}" opacity="0.6" rx="1"/>`

      // Line
      linePath += i === 0 ? `M${x},${cl}` : ` L${x},${cl}`
      aPath    += i === 0 ? `M${x},${cl}` : ` L${x},${cl}`
    })

    const lastX = sx(n - 1), baseY = padT + chartH
    aPath += ` L${lastX},${baseY} L${padL},${baseY} Z`

    return {
      candleSvg,
      sentSvg,
      lineSvg: linePath,
      areaSvg: aPath,
      sentBase,
      chartH,
      h: size.h,
    }
  }, [prices, sentiment, size])

  if (!prices.length) return (
    <div style={{ height: 320, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 14 }}>
      Nessun dato prezzi disponibile.
    </div>
  )

  const { sentBase, chartH } = { sentBase: size.h * 0.65 + 22, chartH: size.h * 0.65 }

  return (
    <div ref={svgRef} style={{ width: '100%', height: '100%' }}>
      <svg
        width="100%" height="100%"
        viewBox={`0 0 ${size.w} ${size.h}`}
        preserveAspectRatio="none"
        style={{ display: 'block' }}
      >
        <defs>
          <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor="#1e5cff" stopOpacity="0.18"/>
            <stop offset="100%" stopColor="#1e5cff" stopOpacity="0"/>
          </linearGradient>
        </defs>

        {/* Grid lines */}
        {[0,1,2,3].map(j => {
          const y = 10 + chartH * j / 3
          return <line key={j} x1="8" y1={y} x2={size.w - 8} y2={y} stroke="rgba(255,255,255,0.04)" strokeWidth="1"/>
        })}

        {/* Divider price/sentiment */}
        <line x1="8" y1={chartH + 15} x2={size.w - 8} y2={chartH + 15} stroke="rgba(255,255,255,0.06)" strokeWidth="1" strokeDasharray="3,4"/>

        {/* Area fill */}
        {areaSvg && <path d={areaSvg} fill="url(#priceGrad)"/>}

        {/* Price line */}
        {lineSvg && <path d={lineSvg} fill="none" stroke="rgba(59,123,255,0.55)" strokeWidth="1.5"/>}

        {/* Candles */}
        {candleSvg && <g dangerouslySetInnerHTML={{ __html: candleSvg }}/>}

        {/* Sentiment bars */}
        {sentSvg && <g dangerouslySetInnerHTML={{ __html: sentSvg }}/>}

        {/* Zero line sentiment */}
        <line x1="8" y1={sentBase} x2={size.w - 8} y2={sentBase} stroke="rgba(255,255,255,0.1)" strokeWidth="1" strokeDasharray="2,4"/>

        {/* Labels */}
        <text x="12" y={chartH - 4} fill="rgba(255,255,255,0.2)" fontSize="10">PREZZO</text>
        <text x="12" y={sentBase + 16} fill="rgba(255,255,255,0.2)" fontSize="10">SENTIMENT</text>
      </svg>
    </div>
  )
}
