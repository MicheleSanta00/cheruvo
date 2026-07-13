/**
 * Icon.jsx — set di icone Cheruvo (PNG bianchi con trasparenza in /public/icons).
 * Renderizza tramite CSS mask, così l'icona prende il colore del testo corrente
 * (o quello passato via prop) e resta nitida su qualsiasi sfondo.
 *
 * Uso: <Icon name="academy" />  ·  <Icon name="bolt" size={14} color="#f5c451" />
 * I nomi corrispondono ai file: name="academy" → /icons/ic-academy.png
 */
export default function Icon({ name, size = 16, color = 'currentColor', style = {}, title }) {
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
