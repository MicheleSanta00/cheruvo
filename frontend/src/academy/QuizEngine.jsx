/**
 * QuizEngine.jsx — motore "quiz a tempo", riusato sia per giocare sia per l'anteprima.
 * Props: content {questions:[{q,options,correct,explain}]}, lang, mode 'play'|'preview',
 *        strings (testi UI), onComplete({correct}).
 */
import { useState } from 'react'
import Icon from '../components/Icon.jsx'
import { pick } from './academyStrings.js'

const GREEN = '#34d399'
const RED = '#f2729b'

export default function QuizEngine({ content, lang = 'it', mode = 'play', strings = {}, onComplete }) {
  const questions = (content && content.questions) || []
  const [idx, setIdx] = useState(0)
  const [sel, setSel] = useState(null)
  const [correct, setCorrect] = useState(0)
  const [done, setDone] = useState(false)

  if (!questions.length) {
    return <div style={{ color: 'var(--muted)', fontSize: 13 }}>—</div>
  }

  const reset = () => { setIdx(0); setSel(null); setCorrect(0); setDone(false) }

  if (done) {
    return (
      <div style={{ textAlign: 'center', padding: '8px 0' }}>
        <div><Icon name="celebrate" size={38} color="#f5c451" /></div>
        <div style={{ fontSize: 18, fontWeight: 600, margin: '6px 0' }}>{strings.lessonDone}</div>
        <div style={{ color: 'var(--muted)', fontSize: 14 }}>{correct}/{questions.length} · +{correct * 20 + 50} {strings.xpEarned}</div>
        {mode === 'play' ? (
          <button onClick={() => onComplete && onComplete({ correct })} style={primaryBtn}>{strings.backToPaths}</button>
        ) : (
          <button onClick={reset} style={ghostBtn}>{strings.restart}</button>
        )}
      </div>
    )
  }

  const q = questions[idx]
  const answered = sel !== null

  const choose = (i) => {
    if (answered) return
    setSel(i)
    if (i === q.correct) setCorrect(c => c + 1)
  }
  const next = () => {
    if (idx + 1 < questions.length) { setIdx(idx + 1); setSel(null) }
    else setDone(true)
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--muted)', fontSize: 12, marginBottom: 10 }}>
        <span>{strings.question} {idx + 1}/{questions.length}</span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>{correct} <Icon name="check" size={12} color="#34d399" /></span>
      </div>
      <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 14 }}>{pick(q.q, lang)}</div>

      <div style={{ display: 'grid', gap: 8 }}>
        {q.options.map((opt, i) => {
          let bg = 'var(--near-black)', bd = 'var(--border)', col = 'var(--white)'
          if (answered && i === q.correct) { bg = 'rgba(52,211,153,0.14)'; bd = GREEN; col = GREEN }
          else if (answered && i === sel) { bg = 'rgba(242,114,155,0.12)'; bd = RED; col = RED }
          return (
            <button key={i} onClick={() => choose(i)} disabled={answered}
              style={{ textAlign: 'left', background: bg, border: `1px solid ${bd}`, color: col,
                borderRadius: 10, padding: '12px 14px', fontSize: 14, cursor: answered ? 'default' : 'pointer' }}>
              {pick(opt, lang)}
            </button>
          )
        })}
      </div>

      {answered && (
        <div style={{ marginTop: 12, fontSize: 13.5, color: 'var(--muted)', background: 'var(--near-black)',
          border: '1px solid var(--border)', borderRadius: 10, padding: '11px 13px' }}>
          <b style={{ color: sel === q.correct ? GREEN : RED }}>{sel === q.correct ? strings.correct : strings.wrong}</b>
          {q.explain ? ' — ' + pick(q.explain, lang) : ''}
        </div>
      )}

      {answered && (
        <button onClick={next} style={{ ...primaryBtn, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          {idx + 1 < questions.length ? <>{strings.next} <Icon name="arrow-right" size={14} color="#04221a" /></> : strings.finish}
        </button>
      )}
    </div>
  )
}

const primaryBtn = {
  marginTop: 16, border: 'none', borderRadius: 10, padding: '11px 18px', cursor: 'pointer',
  fontSize: 14, fontWeight: 600, background: '#34d399', color: '#04221a',
}
const ghostBtn = {
  marginTop: 16, border: '1px solid var(--border)', borderRadius: 10, padding: '11px 18px',
  cursor: 'pointer', fontSize: 14, fontWeight: 600, background: 'transparent', color: 'var(--white)',
}
