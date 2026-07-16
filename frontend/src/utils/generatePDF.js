/**
 * generatePDF.js — Genera report PDF per Cheruvo (client-side, jsPDF)
 * Struttura: header (logo) → KPI → prezzi → grafico → correlazione →
 *            AI summary → top bullish/bearish → recenti → footer
 */
import { jsPDF } from 'jspdf'

// ── Colori ────────────────────────────────────────────────────────────────────
const C = {
  black:    [10,  13,  20],
  dark:     [18,  22,  32],
  card:     [26,  31,  44],
  border:   [45,  52,  70],
  white:    [241, 245, 249],
  muted:    [100, 116, 139],
  blue:     [30,  92,  255],
  azure:    [96,  165, 250],
  green:    [74,  222, 128],
  red:      [248, 113, 113],
  yellow:   [250, 204, 21],
  purple:   [167, 139, 250],
}

function sentColor(v) {
  if (v == null) return C.muted
  if (v > 0.1)  return C.green
  if (v < -0.1) return C.red
  return C.yellow
}

function sentLabel(v) {
  if (v == null) return '—'
  if (v > 0.1)  return 'Bullish'
  if (v < -0.1) return 'Bearish'
  return 'Neutro'
}

function fmt(v) {
  if (v == null || isNaN(v)) return '—'
  return (v >= 0 ? '+' : '') + Number(v).toFixed(3)
}

function fmtDate() {
  return new Date().toLocaleDateString('it-IT', { day: '2-digit', month: 'long', year: 'numeric' })
}

// ── Helpers grafici ───────────────────────────────────────────────────────────
function setFill(doc, rgb)   { doc.setFillColor(...rgb) }
function setDraw(doc, rgb)   { doc.setDrawColor(...rgb) }
function setTextColor(doc, rgb) { doc.setTextColor(...rgb) }
function setFont(doc, size, style = 'normal') {
  doc.setFontSize(size)
  doc.setFont('helvetica', style)
}

function rect(doc, x, y, w, h, rgb, radius = 0) {
  setFill(doc, rgb)
  if (radius > 0) doc.roundedRect(x, y, w, h, radius, radius, 'F')
  else doc.rect(x, y, w, h, 'F')
}

function text(doc, str, x, y, rgb, size, style = 'normal', align = 'left') {
  setFont(doc, size, style)
  setTextColor(doc, rgb)
  doc.text(String(str ?? ''), x, y, { align })
}

function line(doc, x1, y1, x2, y2, rgb, lw = 0.3) {
  setDraw(doc, rgb)
  doc.setLineWidth(lw)
  doc.line(x1, y1, x2, y2)
}

function badge(doc, label, x, y, bgRgb, textRgb) {
  setFont(doc, 7, 'bold')
  const w = doc.getTextWidth(label) + 6
  rect(doc, x, y - 4, w, 6, bgRgb, 1.5)
  setTextColor(doc, textRgb)
  doc.text(label, x + 3, y - 0.3)
  return w
}

// ── Logo (bianco su tile blu; fallback "C" se non caricabile) ─────────────────
async function loadLogoImage() {
  try {
    if (typeof Image === 'undefined') return null
    const img = new Image()
    img.src = '/logo-v2.png'
    await img.decode()
    return img
  } catch {
    return null
  }
}

// ── Correlazione sentiment(D) → rendimento(D+1), calcolata sui dati passati ──
function computeCorrelation(sentiment, prices) {
  const dOf = o => {
    const d = o?.date || o?.Date || o?.day
    return d ? String(d).slice(0, 10) : null
  }
  const closeByDate = new Map()
  const pDates = []
  for (const p of prices || []) {
    const d = dOf(p)
    if (d && p?.Close != null) { closeByDate.set(d, Number(p.Close)); pDates.push(d) }
  }
  if (closeByDate.size < 10) return null
  pDates.sort()
  const nextTrading = new Map()
  for (let i = 0; i < pDates.length - 1; i++) nextTrading.set(pDates[i], pDates[i + 1])

  const xs = [], ys = []
  for (const s of sentiment || []) {
    const d = dOf(s)
    if (!d || s?.sentiment == null) continue
    const nd = nextTrading.get(d)
    if (!nd) continue
    const c0 = closeByDate.get(d), c1 = closeByDate.get(nd)
    if (c0 == null || c1 == null || !c0) continue
    xs.push(Number(s.sentiment))
    ys.push(((c1 - c0) / c0) * 100)
  }
  if (xs.length < 10) return null

  const n = xs.length
  const mx = xs.reduce((a, b) => a + b, 0) / n
  const my = ys.reduce((a, b) => a + b, 0) / n
  let num = 0, dx = 0, dy = 0
  for (let i = 0; i < n; i++) {
    const a = xs[i] - mx, b = ys[i] - my
    num += a * b; dx += a * a; dy += b * b
  }
  const den = Math.sqrt(dx * dy)
  if (!den) return null
  return { r: num / den, n }
}

function corrLabel(r) {
  if (r == null) return 'N/D'
  if (r > 0.5)  return 'Forte positiva'
  if (r > 0.3)  return 'Moderata positiva'
  if (r < -0.5) return 'Forte negativa'
  if (r < -0.3) return 'Moderata negativa'
  return 'Debole / assente'
}

// ── Grafico sentiment + prezzo (disegnato con primitive jsPDF) ───────────────
function drawChart(doc, sentiment, prices, x, y, w, h) {
  rect(doc, x, y, w, h, C.card, 3)
  setDraw(doc, C.border); doc.setLineWidth(0.2)
  doc.roundedRect(x, y, w, h, 3, 3, 'S')

  const pad = 7
  const cx = x + pad, cy = y + pad, cw = w - pad * 2, ch = h - pad * 2 - 6

  const sVals = (sentiment || []).map(s => (s && s.sentiment != null ? Number(s.sentiment) : null))
  const nonNull = sVals.filter(v => v != null)
  const n = sVals.length
  if (n < 2 || nonNull.length < 2) {
    text(doc, 'Dati insufficienti per il grafico', x + w / 2, y + h / 2, C.muted, 7, 'normal', 'center')
    return
  }

  // Scala sentiment adattiva (range minimo 0.3 per non appiattire)
  let sMin = Math.min(...nonNull), sMax = Math.max(...nonNull)
  const range = Math.max(0.3, sMax - sMin)
  const mid = (sMax + sMin) / 2
  sMin = mid - range / 2 - 0.05
  sMax = mid + range / 2 + 0.05
  const SY = v => cy + ch - ((v - sMin) / (sMax - sMin)) * ch
  const SX = i => cx + (i / (n - 1)) * cw

  // Linea dello zero (tratteggiata)
  if (0 >= sMin && 0 <= sMax) {
    doc.setLineDashPattern([1, 1.2], 0)
    line(doc, cx, SY(0), cx + cw, SY(0), C.border, 0.25)
    doc.setLineDashPattern([], 0)
    text(doc, '0', cx - 3, SY(0) + 1, C.muted, 5)
  }

  // Prezzo normalizzato (linea azzurra sottile)
  const pVals = (prices || []).map(p => (p && p.Close != null ? Number(p.Close) : null)).filter(v => v != null)
  if (pVals.length > 1) {
    const pMin = Math.min(...pVals), pMax = Math.max(...pVals)
    const pr = (pMax - pMin) || 1
    const PY = v => cy + ch - ((v - pMin) / pr) * ch
    const PX = i => cx + (i / (pVals.length - 1)) * cw
    for (let i = 1; i < pVals.length; i++) {
      line(doc, PX(i - 1), PY(pVals[i - 1]), PX(i), PY(pVals[i]), C.azure, 0.35)
    }
  }

  // Sentiment: segmenti colorati per segno (verde/rosso/giallo)
  for (let i = 1; i < n; i++) {
    const a = sVals[i - 1], b = sVals[i]
    if (a == null || b == null) continue
    const m = (a + b) / 2
    const col = m > 0.05 ? C.green : m < -0.05 ? C.red : C.yellow
    line(doc, SX(i - 1), SY(a), SX(i), SY(b), col, 0.7)
  }

  // Date inizio/fine
  const dOf = s => (s && (s.date || s.Date || s.day) ? String(s.date || s.Date || s.day).slice(0, 10) : '')
  text(doc, dOf(sentiment[0]), cx, y + h - 2.5, C.muted, 5.5)
  text(doc, dOf(sentiment[n - 1]), cx + cw, y + h - 2.5, C.muted, 5.5, 'normal', 'right')

  // Legenda in alto a destra
  const lx = x + w - pad
  text(doc, 'Sentiment', lx - 22, y + 5.5, C.green, 5.5)
  line(doc, lx - 30, y + 4.5, lx - 24, y + 4.5, C.green, 0.7)
  text(doc, 'Prezzo', lx, y + 5.5, C.azure, 5.5, 'normal', 'right')
  line(doc, lx - 14, y + 4.5, lx - 9.5, y + 4.5, C.azure, 0.35)
}

// ── Export principale ─────────────────────────────────────────────────────────
export async function generateReport({ ticker, tickerInfo, stats, news, sentiment, prices, summary }) {
  const doc  = new jsPDF({ unit: 'mm', format: 'a4' })
  const W    = 210  // larghezza A4
  const H    = 297
  const ML   = 14   // margin left
  const MR   = 14   // margin right
  const CW   = W - ML - MR  // content width

  const logo = await loadLogoImage()

  let y = 0  // cursore verticale corrente

  // Se il blocco successivo non entra nella pagina, vai a pagina nuova
  const ensure = (need) => {
    if (y + need > H - 16) {
      doc.addPage()
      rect(doc, 0, 0, W, H, C.black)
      y = 16
    }
  }

  // ── SFONDO PAGINA ──────────────────────────────────────────────────────────
  rect(doc, 0, 0, W, H, C.black)

  // ── HEADER ─────────────────────────────────────────────────────────────────
  rect(doc, 0, 0, W, 38, C.dark)
  line(doc, 0, 38, W, 38, C.border)

  // Logo su tile blu (fallback: lettera C)
  rect(doc, ML, 8, 10, 10, C.blue, 2)
  let logoOk = false
  if (logo) {
    try { doc.addImage(logo, 'PNG', ML + 1.6, 9.6, 6.8, 6.8); logoOk = true } catch { logoOk = false }
  }
  if (!logoOk) text(doc, 'C', ML + 2.8, 15.5, C.white, 9, 'bold')

  // Nome app
  text(doc, 'Cheruvo', ML + 13, 15, C.white, 13, 'bold')
  text(doc, 'Sentiment Report', ML + 13, 20, C.muted, 8)

  // Ticker a destra
  const tickerName = tickerInfo?.nome ? `${ticker} — ${tickerInfo.nome}` : ticker
  text(doc, tickerName, W - MR, 14, C.azure, 14, 'bold', 'right')
  text(doc, fmtDate(), W - MR, 20, C.muted, 8, 'normal', 'right')
  if (tickerInfo?.settore && tickerInfo.settore !== 'N/A') {
    text(doc, tickerInfo.settore, W - MR, 26, C.muted, 7, 'normal', 'right')
  }

  y = 48

  // ── KPI CARDS ──────────────────────────────────────────────────────────────
  text(doc, 'RIEPILOGO', ML, y, C.muted, 7, 'bold')
  y += 4

  const kpis = [
    { label: 'News totali',     value: stats?.total?.toLocaleString() ?? '—',  color: C.azure },
    { label: 'Sentiment medio', value: fmt(stats?.avg),                          color: sentColor(stats?.avg) },
    { label: 'Picco positivo',  value: fmt(stats?.max),                          color: C.green },
    { label: 'Picco negativo',  value: fmt(stats?.min),                          color: C.red },
    { label: 'Fonti attive',    value: String(stats?.sources ?? '—'),            color: C.azure },
  ]

  const cardW = (CW - 8) / 5
  kpis.forEach((k, i) => {
    const cx = ML + i * (cardW + 2)
    rect(doc, cx, y, cardW, 18, C.card, 2)
    setDraw(doc, C.border)
    doc.setLineWidth(0.2)
    doc.roundedRect(cx, y, cardW, 18, 2, 2, 'S')
    text(doc, k.label, cx + cardW / 2, y + 6.5, C.muted, 6, 'normal', 'center')
    text(doc, k.value, cx + cardW / 2, y + 13, k.color, 10, 'bold', 'center')
  })

  y += 24

  // ── PREZZI DEL PERIODO ─────────────────────────────────────────────────────
  const closes = (prices || []).map(p => (p && p.Close != null ? Number(p.Close) : null)).filter(v => v != null)
  if (closes.length > 1) {
    const first = closes[0], last = closes[closes.length - 1]
    const chg = last - first
    const pct = (chg / first) * 100
    const hi = Math.max(...closes), lo = Math.min(...closes)
    const sign = chg >= 0 ? '+' : ''
    const pcol = chg >= 0 ? C.green : C.red

    text(doc, 'PREZZI DEL PERIODO', ML, y, C.muted, 7, 'bold')
    y += 4

    const pk = [
      { label: 'Ultimo prezzo',       value: last.toFixed(2),                              color: C.white },
      { label: 'Variazione periodo',  value: `${sign}${chg.toFixed(2)} (${sign}${pct.toFixed(2)}%)`, color: pcol },
      { label: 'Massimo',             value: hi.toFixed(2),                                color: C.azure },
      { label: 'Minimo',              value: lo.toFixed(2),                                color: C.azure },
    ]
    const pw = (CW - 6) / 4
    pk.forEach((k, i) => {
      const cx = ML + i * (pw + 2)
      rect(doc, cx, y, pw, 16, C.card, 2)
      setDraw(doc, C.border)
      doc.setLineWidth(0.2)
      doc.roundedRect(cx, y, pw, 16, 2, 2, 'S')
      text(doc, k.label, cx + pw / 2, y + 6, C.muted, 6, 'normal', 'center')
      text(doc, k.value, cx + pw / 2, y + 12, k.color, 8.5, 'bold', 'center')
    })
    y += 22
  }

  // ── GRAFICO SENTIMENT + PREZZO ─────────────────────────────────────────────
  const sVals = (sentiment || []).map(s => (s && s.sentiment != null ? Number(s.sentiment) : null))
  const nonNull = sVals.filter(v => v != null)
  if (nonNull.length > 1) {
    ensure(62)
    text(doc, 'ANDAMENTO NEL PERIODO', ML, y, C.muted, 7, 'bold')
    y += 4
    drawChart(doc, sentiment, prices, ML, y, CW, 44)
    y += 48

    // Riga statistiche giorni
    const bullish = nonNull.filter(v => v > 0.1).length
    const bearish = nonNull.filter(v => v < -0.1).length
    const neutral = nonNull.length - bullish - bearish
    const tot = nonNull.length || 1
    const lastS = nonNull[nonNull.length - 1]
    const pctOf = v => Math.round((v / tot) * 100)
    text(doc,
      `Giorni con dati: ${tot}  ·  bullish ${bullish} (${pctOf(bullish)}%)  ·  bearish ${bearish} (${pctOf(bearish)}%)  ·  neutri ${neutral} (${pctOf(neutral)}%)  —  Sentiment recente: ${fmt(lastS)} (${sentLabel(lastS)})`,
      ML, y, C.muted, 6.5)
    y += 8
  }

  // ── CORRELAZIONE SENTIMENT → PREZZO (D+1) ──────────────────────────────────
  const corr = computeCorrelation(sentiment, prices)
  if (corr) {
    ensure(26)
    text(doc, 'CORRELAZIONE SENTIMENT → PREZZO GIORNO DOPO', ML, y, C.muted, 7, 'bold')
    y += 4
    rect(doc, ML, y, CW, 16, C.card, 3)
    setDraw(doc, C.border); doc.setLineWidth(0.2)
    doc.roundedRect(ML, y, CW, 16, 3, 3, 'S')
    const rcol = corr.r > 0.3 ? C.green : corr.r < -0.3 ? C.red : C.yellow
    rect(doc, ML, y, 2, 16, rcol)
    text(doc, (corr.r >= 0 ? '+' : '') + corr.r.toFixed(3), ML + 8, y + 10, rcol, 13, 'bold')
    text(doc, corrLabel(corr.r), ML + 34, y + 7, C.white, 8, 'bold')
    text(doc, `Pearson su ${corr.n} coppie sentiment/rendimento — vicino a 0 = nessuna relazione`, ML + 34, y + 12, C.muted, 6)
    y += 22
  }

  // ── AI SUMMARY ─────────────────────────────────────────────────────────────
  if (summary?.giudizio) {
    const sc = sentColor(summary.giudizio === 'bullish' ? 0.5 : summary.giudizio === 'bearish' ? -0.5 : 0)
    const lines = summary.riassunto ? doc.splitTextToSize(summary.riassunto, CW - 12).slice(0, 6) : []
    const boxH = 12 + (lines.length ? 3 + lines.length * 4.6 : 0) + (summary.temi?.length ? 8 : 2)

    ensure(boxH + 8)
    rect(doc, ML, y, CW, boxH, C.card, 3)
    setDraw(doc, C.border)
    doc.setLineWidth(0.2)
    doc.roundedRect(ML, y, CW, boxH, 3, 3, 'S')

    // Linea colorata sinistra
    rect(doc, ML, y, 2, boxH, sc)

    // Badge AI
    badge(doc, 'AI SUMMARY', ML + 6, y + 6, [40, 30, 80], C.purple)
    badge(doc, summary.giudizio.toUpperCase(), ML + 42, y + 6, C.card, sc)

    if (summary.news_analizzate) {
      text(doc, `${summary.news_analizzate} news analizzate`, W - MR, y + 5.5, C.muted, 6, 'normal', 'right')
    }

    if (lines.length) {
      setFont(doc, 8)
      setTextColor(doc, C.white)
      lines.forEach((l, i) => {
        doc.text(l, ML + 6, y + 13 + i * 4.6)
      })
    }

    // Temi
    if (summary.temi?.length) {
      let tx = ML + 6
      const ty = y + boxH - 4
      summary.temi.slice(0, 5).forEach(tema => {
        const bw = badge(doc, tema, tx, ty, C.card, sc)
        tx += bw + 3
      })
    }

    y += boxH + 8
  }

  // ── SEZIONI NEWS ───────────────────────────────────────────────────────────
  const byScoreDesc = [...news].sort((a, b) => b.sentiment - a.sentiment)
  const bullishNews = byScoreDesc.filter(n => n.sentiment > 0).slice(0, 8)
  const bearishNews = [...news].sort((a, b) => a.sentiment - b.sentiment).filter(n => n.sentiment < 0).slice(0, 8)
  const recentNews  = [...news]
    .filter(n => n.published_date)
    .sort((a, b) => String(b.published_date).localeCompare(String(a.published_date)))
    .slice(0, 6)

  function newsSection(title, items, color, startY, { scoreColorPerItem = false } = {}) {
    let cy = startY
    text(doc, title, ML, cy, C.muted, 7, 'bold')
    cy += 4

    items.forEach(item => {
      // Check se serve nuova pagina
      if (cy > H - 32) {
        doc.addPage()
        rect(doc, 0, 0, W, H, C.black)
        cy = 16
      }

      const rowH = 13
      const rowColor = scoreColorPerItem ? sentColor(item.sentiment) : color
      rect(doc, ML, cy, CW, rowH, C.card, 2)
      // Bordo sinistro colorato
      rect(doc, ML, cy, 2, rowH, rowColor)

      const score = (item.sentiment >= 0 ? '+' : '') + Number(item.sentiment).toFixed(3)
      text(doc, score, ML + 6, cy + 5, rowColor, 7, 'bold')
      text(doc, sentLabel(item.sentiment), ML + 6, cy + 9.5, C.muted, 6)

      const titleStr = item.title?.length > 84 ? item.title.slice(0, 84) + '…' : (item.title ?? '')
      text(doc, titleStr, ML + 22, cy + 5.5, C.white, 7)

      const meta = [item.source, item.published_date?.slice(0, 10)].filter(Boolean).join('  ·  ')
      text(doc, meta, ML + 22, cy + 9.5, C.muted, 6)

      cy += rowH + 2
    })

    return cy + 5
  }

  if (bullishNews.length > 0) {
    ensure(30)
    y = newsSection('TOP BULLISH', bullishNews, C.green, y)
  }

  if (bearishNews.length > 0) {
    ensure(30)
    y = newsSection('TOP BEARISH', bearishNews, C.red, y)
  }

  if (recentNews.length > 0) {
    ensure(30)
    y = newsSection('PIÙ RECENTI', recentNews, C.azure, y, { scoreColorPerItem: true })
  }

  // ── FOOTER ─────────────────────────────────────────────────────────────────
  const pageCount = doc.internal.getNumberOfPages()
  for (let p = 1; p <= pageCount; p++) {
    doc.setPage(p)
    line(doc, 0, H - 12, W, H - 12, C.border)
    text(doc, `Generato da Cheruvo · cheruvo.com · ${fmtDate()} — Solo a scopo informativo, non è consulenza finanziaria`, ML, H - 7, C.muted, 6)
    text(doc, `${p} / ${pageCount}`, W - MR, H - 7, C.muted, 6, 'normal', 'right')
  }

  // ── SALVA ──────────────────────────────────────────────────────────────────
  const filename = `cheruvo_${ticker}_${new Date().toISOString().slice(0, 10)}.pdf`
  doc.save(filename)
}
