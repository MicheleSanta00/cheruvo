/**
 * generatePDF.js — Genera report PDF per Cheruvo (client-side, jsPDF)
 * Struttura: header → KPI → sentiment summary → top news bullish/bearish → footer
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

// ── Export principale ─────────────────────────────────────────────────────────
export function generateReport({ ticker, tickerInfo, stats, news, sentiment, summary }) {
  const doc  = new jsPDF({ unit: 'mm', format: 'a4' })
  const W    = 210  // larghezza A4
  const H    = 297
  const ML   = 14   // margin left
  const MR   = 14   // margin right
  const CW   = W - ML - MR  // content width

  let y = 0  // cursore verticale corrente

  // ── SFONDO PAGINA ──────────────────────────────────────────────────────────
  rect(doc, 0, 0, W, H, C.black)

  // ── HEADER ─────────────────────────────────────────────────────────────────
  rect(doc, 0, 0, W, 38, C.dark)
  line(doc, 0, 38, W, 38, C.border)

  // Logo quadrato
  rect(doc, ML, 8, 10, 10, C.blue, 2)
  text(doc, 'C', ML + 2.8, 15.5, C.white, 9, 'bold')

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

  y = 50

  // ── KPI CARDS ──────────────────────────────────────────────────────────────
  text(doc, 'RIEPILOGO', ML, y, C.muted, 7, 'bold')
  y += 5

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
    rect(doc, cx, y, cardW, 20, C.card, 2)
    setDraw(doc, C.border)
    doc.setLineWidth(0.2)
    doc.roundedRect(cx, y, cardW, 20, 2, 2, 'S')
    text(doc, k.label, cx + cardW / 2, y + 7, C.muted, 6, 'normal', 'center')
    text(doc, k.value, cx + cardW / 2, y + 14, k.color, 10, 'bold', 'center')
  })

  y += 28

  // ── AI SUMMARY ─────────────────────────────────────────────────────────────
  if (summary?.giudizio) {
    const sc = sentColor(summary.giudizio === 'bullish' ? 0.5 : summary.giudizio === 'bearish' ? -0.5 : 0)
    const emoji = summary.giudizio === 'bullish' ? '📈' : summary.giudizio === 'bearish' ? '📉' : '➡️'

    rect(doc, ML, y, CW, summary.riassunto ? 36 : 16, C.card, 3)
    setDraw(doc, C.border)
    doc.setLineWidth(0.2)
    doc.roundedRect(ML, y, CW, summary.riassunto ? 36 : 16, 3, 3, 'S')

    // Linea colorata sinistra
    rect(doc, ML, y, 2, summary.riassunto ? 36 : 16, sc)

    // Badge AI
    badge(doc, '✨ AI SUMMARY', ML + 6, y + 6, [40, 30, 80], C.purple)
    badge(doc, `${emoji} ${summary.giudizio.toUpperCase()}`, ML + 50, y + 6, C.card, sc)

    if (summary.news_analizzate) {
      text(doc, `${summary.news_analizzate} news analizzate`, W - MR, y + 5.5, C.muted, 6, 'normal', 'right')
    }

    if (summary.riassunto) {
      const lines = doc.splitTextToSize(summary.riassunto, CW - 12)
      const visLines = lines.slice(0, 3)
      setFont(doc, 8)
      setTextColor(doc, C.white)
      visLines.forEach((l, i) => {
        doc.text(l, ML + 6, y + 14 + i * 5)
      })
    }

    // Temi
    if (summary.temi?.length) {
      let tx = ML + 6
      const ty = y + (summary.riassunto ? 32 : 12)
      summary.temi.slice(0, 5).forEach(tema => {
        const bw = badge(doc, tema, tx, ty, C.card, sc)
        tx += bw + 3
      })
    }

    y += (summary.riassunto ? 36 : 16) + 10
  }

  // ── TOP BULLISH NEWS ───────────────────────────────────────────────────────
  const sorted   = [...news].sort((a, b) => b.sentiment - a.sentiment)
  const bullish  = sorted.filter(n => n.sentiment > 0).slice(0, 5)
  const bearish  = [...news].sort((a, b) => a.sentiment - b.sentiment).filter(n => n.sentiment < 0).slice(0, 5)

  function newsSection(title, items, color, startY) {
    let cy = startY
    text(doc, title, ML, cy, C.muted, 7, 'bold')
    cy += 5

    items.forEach(item => {
      // Check se serve nuova pagina
      if (cy > H - 30) {
        doc.addPage()
        rect(doc, 0, 0, W, H, C.black)
        cy = 16
      }

      const rowH = 14
      rect(doc, ML, cy, CW, rowH, C.card, 2)
      // Bordo sinistro colorato
      rect(doc, ML, cy, 2, rowH, color)

      const score = (item.sentiment >= 0 ? '+' : '') + Number(item.sentiment).toFixed(3)
      text(doc, score, ML + 6, cy + 5, color, 7, 'bold')
      text(doc, score, ML + 6, cy + 9.5, C.muted, 6)

      const titleStr = item.title?.length > 80 ? item.title.slice(0, 80) + '…' : (item.title ?? '')
      text(doc, titleStr, ML + 22, cy + 5.5, C.white, 7)

      const meta = [item.source, item.published_date?.slice(0, 10)].filter(Boolean).join('  ·  ')
      text(doc, meta, ML + 22, cy + 10, C.muted, 6)

      cy += rowH + 2
    })

    return cy + 4
  }

  // Bullish
  if (bullish.length > 0) {
    y = newsSection('TOP BULLISH', bullish, C.green, y)
  }

  // Bearish
  if (bearish.length > 0) {
    if (y > H - 60) {
      doc.addPage()
      rect(doc, 0, 0, W, H, C.black)
      y = 16
    }
    y = newsSection('TOP BEARISH', bearish, C.red, y)
  }

  // ── FOOTER ─────────────────────────────────────────────────────────────────
  const pageCount = doc.internal.getNumberOfPages()
  for (let p = 1; p <= pageCount; p++) {
    doc.setPage(p)
    line(doc, 0, H - 12, W, H - 12, C.border)
    text(doc, `Generato da Cheruvo · ${fmtDate()} · Solo per utenti PRO`, ML, H - 7, C.muted, 6)
    text(doc, `${p} / ${pageCount}`, W - MR, H - 7, C.muted, 6, 'normal', 'right')
  }

  // ── SALVA ──────────────────────────────────────────────────────────────────
  const filename = `cheruvo_${ticker}_${new Date().toISOString().slice(0, 10)}.pdf`
  doc.save(filename)
}
