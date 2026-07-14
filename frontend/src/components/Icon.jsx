/**
 * Icon.jsx — set di icone Cheruvo.
 *
 * Due tipi, stessa API <Icon name="..." size={16} color="..." />:
 *  1. GLIFI UI (frecce, chevron, close, check, menu, plus, send): SVG inline
 *     con tratto 2px arrotondato — nitidi a ogni dimensione, ricolorabili.
 *  2. Icone illustrate (lock, book, quiz, bolt, …): PNG bianchi trasparenti in
 *     /public/icons, resi via CSS mask così prendono il colore del testo.
 *
 * I nomi PNG corrispondono ai file: name="lock" → /icons/ic-lock.png
 */

// ── Glifi vettoriali (stroke). viewBox 24×24, tratto 2px ────────────────────
const STROKE = {
  'arrow-right': 'M5 12h14M13 6l6 6-6 6',
  'arrow-left':  'M19 12H5M11 6l-6 6 6 6',
  'arrow-up':    'M12 19V5M6 11l6-6 6 6',
  'arrow-down':  'M12 5v14M6 13l6 6 6-6',
  'chevron-down':'M6 9l6 6 6-6',
  'chevron-right':'M9 6l6 6-6 6',
  close:         'M6 6l12 12M18 6L6 18',
  check:         'M5 13l4 4L19 7',
  plus:          'M12 5v14M5 12h14',
  menu:          'M4 7h16M4 12h16M4 17h16',
  send:          'M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z',
  external:      'M14 5h5v5M19 5l-8 8M12 5H6a1 1 0 00-1 1v12a1 1 0 001 1h12a1 1 0 001-1v-6',
}

export default function Icon({ name, size = 16, color = 'currentColor', style = {}, title }) {
  const path = STROKE[name]
  if (path) {
    return (
      <svg
        width={size} height={size} viewBox="0 0 24 24" fill="none"
        stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
        aria-hidden={title ? undefined : true}
        style={{ flexShrink: 0, verticalAlign: '-0.14em', ...style }}
      >
        {title ? <title>{title}</title> : null}
        <path d={path} />
      </svg>
    )
  }

  const m = `url(/icons/ic-${name}.png)`
  return (
    <span
      aria-hidden={title ? undefined : true}
      title={title}
      style={{
        display: 'inline-block',
        width: size,
        height: size,
        flexShrink: 0,
        verticalAlign: '-0.18em',
        backgroundColor: color,
        WebkitMask: `${m} center / contain no-repeat`,
        mask: `${m} center / contain no-repeat`,
        ...style,
      }}
    />
  )
}
