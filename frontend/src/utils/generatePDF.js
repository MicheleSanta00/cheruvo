/**
 * generatePDF.js — Genera report PDF per Cheruvo (client-side, jsPDF)
 * Struttura: header (logo) → KPI → prezzi → grafico → correlazione →
 *            AI summary → top bullish/bearish → recenti → footer
 */
import { jsPDF } from 'jspdf'
import {
  MIN_COPPIE, correlazione, compatibileConZero, etichetta, spiegazione,
} from './incertezza.js'

// ── Colori ────────────────────────────────────────────────────────────────────
//
// Tavolozza DA STAMPA, non da schermo.
//
// Il report era disegnato come l'app: fondo nero, testo chiaro, verdi e azzurri
// accesi. A schermo funziona, su carta no. Un A4 a fondo nero consuma mezza
// cartuccia, in fotocopia diventa una macchia, e allegato a una mail o
// stampato per un commercialista non sembra un documento, sembra uno
// screenshot. I nomi delle chiavi restano quelli di prima per non toccare le
// duecento righe che li usano: `black` adesso vale bianco, `white` vale quasi
// nero. Leggile come "sfondo" e "testo".
//
// I colori d'accento sono stati SCURITI, non riusati: il verde #4ade80 su
// bianco è illeggibile, e stampato in scala di grigi sparisce del tutto.
const C = {
  black:    [255, 255, 255],   // sfondo pagina
  dark:     [246, 247, 250],   // fascia intestazione
  card:     [250, 251, 253],   // riquadri
  border:   [214, 220, 230],   // bordi, visibili anche in fotocopia
  white:    [17,  24,  39],    // testo principale
  muted:    [107, 114, 128],   // testo secondario
  blue:     [30,  92,  255],
  azure:    [29,  78,  216],   // era #60a5fa: su bianco spariva
  green:    [4,   120, 87],    // verde scuro, leggibile anche in grigio
  red:      [185, 28,  28],
  yellow:   [161, 98,  7],     // ocra: il giallo puro su bianco non si vede
  purple:   [109, 40,  217],
}

// Colori ufficiali delle criptovalute, per il disco accanto al nome.
// Gli stessi dell'app, così il documento e la schermata si somigliano.
const MONETE_PDF = {
  'BTC-USD':  { s: 'B',  c: [247, 147, 26] },
  'ETH-USD':  { s: 'E',  c: [98,  126, 234] },
  'SOL-USD':  { s: 'SO', c: [20,  180, 140] },
  'XRP-USD':  { s: 'XR', c: [35,  41,  47] },
  'ADA-USD':  { s: 'AD', c: [0,   51,  173] },
  'DOGE-USD': { s: 'DO', c: [186, 160, 51] },
  'AVAX-USD': { s: 'AV', c: [232, 65,  66] },
  'LINK-USD': { s: 'LI', c: [42,  90,  218] },
  'DOT-USD':  { s: 'DT', c: [230, 0,   122] },
  'LTC-USD':  { s: 'LT', c: [130, 133, 134] },
  'UNI-USD':  { s: 'UN', c: [230, 0,   110] },
  'ATOM-USD': { s: 'AT', c: [46,  49,  72] },
  'XLM-USD':  { s: 'XL', c: [12,  140, 180] },
  'NEAR-USD': { s: 'NE', c: [0,   150, 110] },
  'BCH-USD':  { s: 'BC', c: [110, 155, 65] },
  'SHIB-USD': { s: 'SH', c: [200, 128, 8] },
}

function eCryptoPdf(tk) {
  return typeof tk === 'string' && tk.toUpperCase().endsWith('-USD')
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

// ── Logo Cheruvo ─────────────────────────────────────────────────────────────
//
// Incorporato nel codice come immagine, non caricato dalla rete.
//
// Prima veniva letto da /logo-v2.png con `new Image()`. Funziona quasi sempre,
// ma "quasi" non basta per un documento che l'utente scarica e magari
// stampa: se la richiesta fallisce, se il file è in cache in modo strano, o
// se il PDF viene generato in un contesto senza immagini, al posto del
// marchio compariva una "C" solitaria. Un report con una lettera al posto del
// logo sembra rotto.
//
// Ridimensionato a 160x160: nel PDF è largo 6,8 mm, quindi a 300 dpi
// basterebbero 80 pixel. Il doppio garantisce nitidezza anche ingrandendo la
// pagina, e pesa 7 KB invece dei 209 KB dell'originale.
const LOGO_B64 = 'data:image/png;base64,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'

async function loadLogoImage() {
  return LOGO_B64
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
  // La formula e la soglia stanno in utils/incertezza.js. Qui c'è solo la
  // costruzione delle coppie, che è l'unica cosa specifica del report: il PDF
  // aveva una soglia sua (10 coppie) e una scala di aggettivi sua, e finiva
  // per stampare su carta un giudizio che a schermo era già stato tolto.
  return correlazione(xs, ys)
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
  // Metadati: un documento che si allega o si archivia deve avere un nome
  // anche dentro, non solo nel file. Senza, i lettori PDF mostrano
  // "Senza titolo" nella barra e nelle proprietà.
  doc.setProperties({
    title: `Cheruvo — Report sentiment ${ticker}`,
    subject: 'Analisi del sentiment delle notizie finanziarie',
    author: 'Cheruvo', creator: 'cheruvo.com',
  })
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

  // Logo su tile scuro. Il logo Cheruvo è disegnato in chiaro: su una pagina
  // bianca serve il suo fondo scuro, esattamente come nell'app.
  rect(doc, ML, 8, 10, 10, [10, 13, 20], 2)
  let logoOk = false
  if (logo) {
    try { doc.addImage(logo, 'PNG', ML + 1.6, 9.6, 6.8, 6.8); logoOk = true } catch { logoOk = false }
  }
  if (!logoOk) text(doc, 'C', ML + 3.2, 15.2, [255, 255, 255], 9, 'bold')

  // Nome app
  text(doc, 'Cheruvo', ML + 13, 14.5, C.white, 13, 'bold')
  text(doc, 'Report sentiment', ML + 13, 19.5, C.muted, 7.5)

  // Titolo a destra, col disco della moneta quando è una criptovaluta
  const pulito = eCryptoPdf(ticker) ? String(ticker).replace('-USD', '') : ticker
  const moneta = MONETE_PDF[String(ticker).toUpperCase()]
  const tickerName = tickerInfo?.nome ? `${pulito} — ${tickerInfo.nome}` : pulito

  text(doc, tickerName, W - MR, 14, C.white, 14, 'bold', 'right')
  if (moneta) {
    // Il disco va a sinistra del testo: ne misuro la larghezza per sapere dove
    doc.setFontSize(14); doc.setFont('helvetica', 'bold')
    const larg = doc.getTextWidth(tickerName)
    const cx = W - MR - larg - 6.5
    setFill(doc, moneta.c)
    doc.circle(cx, 12.6, 3.2, 'F')
    text(doc, moneta.s, cx, 14, [255, 255, 255], moneta.s.length > 1 ? 4.2 : 6, 'bold', 'center')
  }
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

    // Su carta il rischio è più alto che a schermo: un PDF viene inoltrato,
    // stampato e riletto mesi dopo senza il contesto. Se la banda comprende lo
    // zero, il numero non prende un colore che suggerisce una direzione.
    const rcol = compatibileConZero(corr) ? C.muted : corr.r > 0 ? C.green : C.red
    rect(doc, ML, y, 2, 16, rcol)
    text(doc, corr.r != null ? (corr.r >= 0 ? '+' : '') + corr.r.toFixed(3) : '—',
      ML + 8, y + 10, rcol, 13, 'bold')
    text(doc, etichetta(corr), ML + 34, y + 7, C.white, 8, 'bold')
    text(doc, corr.r != null
      ? `Pearson su ${corr.n} coppie, ${spiegazione(corr)}`
      : `Servono ${MIN_COPPIE} giorni con notizie e prezzo, ce ne sono ${corr.n}`,
      ML + 34, y + 12, C.muted, 6)
    y += 22
  }

  // ── AI SUMMARY ─────────────────────────────────────────────────────────────
  if (summary?.giudizio) {
    const sc = sentColor(summary.giudizio === 'bullish' ? 0.5 : summary.giudizio === 'bearish' ? -0.5 : 0)
    // Il font va impostato PRIMA di splitTextToSize: misura con il font attivo
    setFont(doc, 8)
    const lines = summary.riassunto ? doc.splitTextToSize(summary.riassunto, CW - 14).slice(0, 6) : []
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
      // Contorno: su fondo bianco il riquadro chiaro sparirebbe, e le notizie
      // diventerebbero un blocco di testo senza righe separate.
      setDraw(doc, C.border); doc.setLineWidth(0.2)
      doc.roundedRect(ML, cy, CW, rowH, 2, 2, 'S')
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
    text(doc, `Cheruvo · cheruvo.com · generato il ${fmtDate()}`, ML, H - 8, C.muted, 6)
    text(doc, 'Documento informativo. Non costituisce consulenza finanziaria né raccomandazione di investimento.',
         ML, H - 4.5, C.muted, 5.5)
    text(doc, `${p} / ${pageCount}`, W - MR, H - 7, C.muted, 6, 'normal', 'right')
  }

  // ── SALVA ──────────────────────────────────────────────────────────────────
  const filename = `Cheruvo_${eCryptoPdf(ticker) ? String(ticker).replace('-USD', '') : ticker}_${new Date().toISOString().slice(0, 10)}.pdf`
  doc.save(filename)
}
