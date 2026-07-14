/**
 * ScenarioEngine.jsx — storia a bivi: testo, scelte, feedback e nodo successivo.
 * goto vuoto = fine. Riusato per giocare e per l'anteprima.
 */
import { useState } from 'react'
import { pick } from './academyStrings.js'
import Icon from '../components/Icon.jsx'

export default function ScenarioEngine({ content, lang = 'it', strings = {}, mode = 'play', onComplete }) {
  const nodes = (content && content.nodes) || {}
  const startId = (content && content.start) || Object.keys(nodes)[0]
  const [nodeId, setNodeId] = useState(startId)
  const [chosen, setChosen] = useState(null)
  const [done, setDone] = useState(false)

  const node = nodes[nodeId]
  if (!node) return <div style={{ color: 'var(--muted)', fontSize: 13 }}>—</div>

  const reset = () => { setNodeId(startId); setChosen(null); setDone(false) }

  if (done) {
    return (
      <div style={{ textAlign: 'center', padding: '8px 0' }}>
        <div><Icon name="celebrate" size={38} color="#f5c451" /></div>
        <div style={{ fontSize: 18, fontWeight: 600, margin: '6px 0' }}>{strings.lessonDone}</div>
        <div style={{ color: 'var(--muted)', fontSize: 14 }}>+50 {strings.xpEarned}</div>
        {mode === 'play'
          ? <button onClick={() => onComplete && onComplete({ correct: 0 })} style={primaryBtn}>{strings.backToPaths}</button>
          : <button onClick={reset} style={ghostBtn}>{strings.restart}</button>}
      </div>
    )
  }

  const proceed = () => {
    const goto = node.choices[chosen] && node.choices[chosen].goto
    if (goto && nodes[goto]) { setNodeId(goto); setChosen(null) }
    else setDone(true)
  }

  return (
    <div>
      {content.ticker && (
        <span style={{ fontSize: 11, fontWeight: 600, color: '#6aa6ff', background: 'rgba(106,166,255,0.12)',
          border: '1px solid rgba(106,166,255,0.25)', borderRadius: 99, padding: '3px 10px' }}>${content.ticker}</span>
      )}
      <div style={{ fontSize: 16, lineHeight: 1.6, margin: '12px 0 14px' }}>{pick(node.text, lang)}</div>

      {chosen === null ? (
        <div style={{ display: 'grid', gap: 8 }}>
          {node.choices.map((c, i) => (
            <button key={i} onClick={() => setChosen(i)} style={{ textAlign: 'left', background: 'var(--black)',
              border: '1px solid var(--border)', color: 'var(--white)', borderRadius: 10, padding: '12px 14px',
              fontSize: 14, cursor: 'pointer' }}>
              {pick(c.label, lang)}
            </button>
          ))}
        </div>
      ) : (
        <div>
          <div style={{ fontSize: 13.5, color: 'var(--muted)', background: 'var(--black)', border: '1px solid var(--border)',
            borderRadius: 10, padding: '12px 14px' }}>
            <b style={{ color: '#34d399' }}>{pick(node.choices[chosen].label, lang)}</b>
            {pick(node.choices[chosen].feedback, lang) ? ' — ' + pick(node.choices[chosen].feedback, lang) : ''}
          </div>
          <button onClick={proceed} style={{ ...primaryBtn, display: 'inline-flex', alignItems: 'center', gap: 6 }}>{strings.continue} <Icon name="arrow-right" size={14} color="#04221a" /></button>
        </div>
      )}
    </div>
  )
}

const primaryBtn = { marginTop: 16, border: 'none', borderRadius: 10, padding: '11px 18px', cursor: 'pointer', fontSize: 14, fontWeight: 600, background: '#34d399', color: '#04221a' }
const ghostBtn = { marginTop: 16, border: '1px solid var(--border)', borderRadius: 10, padding: '11px 18px', cursor: 'pointer', fontSize: 14, fontWeight: 600, background: 'transparent', color: 'var(--white)' }
