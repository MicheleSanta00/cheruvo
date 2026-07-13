/**
 * LessonForm.jsx — form di authoring per ogni tipo di lezione + i contenuti "vuoti".
 * In cima c'è il box "Genera con AI" (per tutti i tipi); sotto il form specifico.
 */
import { useState } from 'react'
import { SIM_MODELS } from './simModels.js'
import { pick } from './academyStrings.js'

const EMPTY = { it: '', en: '' }
const blankL = () => ({ it: '', en: '' })
const blankQ = () => ({ q: blankL(), options: [blankL(), blankL(), blankL(), blankL()], correct: 0, explain: blankL() })
const blankCard = () => ({ term: blankL(), definition: blankL(), example: blankL() })
const blankChoice = () => ({ label: blankL(), feedback: blankL(), goto: '' })

export function blankContent(type) {
  if (type === 'quiz') return { timer_sec: 30, pass_score: 70, questions: [blankQ()] }
  if (type === 'simulator') return { model: 'compound_interest', teach: blankL() }
  if (type === 'flashcard') return { deck: [blankCard()] }
  if (type === 'scenario') return { start: 'n1', ticker: '', nodes: { n1: { text: blankL(), choices: [blankChoice()] } } }
  return {}
}

function Loc({ val, set, ph }) {
  const v = val || EMPTY
  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
      <input style={inp} placeholder={ph + ' (IT)'} value={v.it} onChange={(e) => set('it', e.target.value)} />
      <input style={inp} placeholder={ph + ' (EN)'} value={v.en} onChange={(e) => set('en', e.target.value)} />
    </div>
  )
}

export default function LessonForm({ type, content, onContent, lang, s, onAI, aiBusy }) {
  const [topic, setTopic] = useState('')
  const up = (mut) => { const n = JSON.parse(JSON.stringify(content)); mut(n); onContent(n) }

  const body = () => {
    if (type === 'quiz') {
      return (
        <div>
          {content.questions.map((q, qi) => (
            <div key={qi} style={qBlock}>
              <div style={rowBetween}>
                <span style={lblMuted}>{s.question} {qi + 1}</span>
                {content.questions.length > 1 && <button style={linkDanger} onClick={() => up((n) => n.questions.splice(qi, 1))}>{s.removeQ}</button>}
              </div>
              <Loc val={q.q} ph={s.question} set={(f, v) => up((n) => { n.questions[qi].q[f] = v })} />
              <div style={lblMuted}>{s.options}</div>
              {q.options.map((o, oi) => (
                <div key={oi} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
                  <input type="radio" name={`c-${qi}`} checked={q.correct === oi} onChange={() => up((n) => { n.questions[qi].correct = oi })} />
                  <input style={{ ...inp, marginBottom: 0, flex: '1 1 130px' }} placeholder={`IT ${oi + 1}`} value={o.it} onChange={(e) => up((n) => { n.questions[qi].options[oi].it = e.target.value })} />
                  <input style={{ ...inp, marginBottom: 0, flex: '1 1 130px' }} placeholder={`EN ${oi + 1}`} value={o.en} onChange={(e) => up((n) => { n.questions[qi].options[oi].en = e.target.value })} />
                </div>
              ))}
              <Loc val={q.explain} ph={s.explanation} set={(f, v) => up((n) => { n.questions[qi].explain[f] = v })} />
            </div>
          ))}
          <button style={ghost} onClick={() => up((n) => n.questions.push(blankQ()))}>{s.addQuestion}</button>
        </div>
      )
    }

    if (type === 'simulator') {
      return (
        <div>
          <label style={lbl}>{s.simModel}</label>
          <select style={{ ...inp, marginBottom: 12 }} value={content.model} onChange={(e) => up((n) => { n.model = e.target.value })}>
            {Object.entries(SIM_MODELS).map(([k, m]) => <option key={k} value={k}>{pick(m.label, lang)}</option>)}
          </select>
          <label style={lbl}>{s.teachText}</label>
          <Loc val={content.teach} ph={s.teachText} set={(f, v) => up((n) => { if (!n.teach) n.teach = blankL(); n.teach[f] = v })} />
        </div>
      )
    }

    if (type === 'flashcard') {
      return (
        <div>
          {content.deck.map((c, ci) => (
            <div key={ci} style={qBlock}>
              <div style={rowBetween}>
                <span style={lblMuted}>{s.term} {ci + 1}</span>
                {content.deck.length > 1 && <button style={linkDanger} onClick={() => up((n) => n.deck.splice(ci, 1))}>{s.removeQ}</button>}
              </div>
              <Loc val={c.term} ph={s.term} set={(f, v) => up((n) => { n.deck[ci].term[f] = v })} />
              <Loc val={c.definition} ph={s.definition} set={(f, v) => up((n) => { n.deck[ci].definition[f] = v })} />
              <Loc val={c.example} ph={s.example} set={(f, v) => up((n) => { if (!n.deck[ci].example) n.deck[ci].example = blankL(); n.deck[ci].example[f] = v })} />
            </div>
          ))}
          <button style={ghost} onClick={() => up((n) => n.deck.push(blankCard()))}>{s.addCard}</button>
        </div>
      )
    }

    if (type === 'scenario') {
      const ids = Object.keys(content.nodes)
      return (
        <div>
          <label style={lbl}>{s.scnTicker}</label>
          <input style={{ ...inp, marginBottom: 12 }} placeholder="NVDA" value={content.ticker || ''} onChange={(e) => up((n) => { n.ticker = e.target.value.toUpperCase() })} />
          {ids.map((id, ni) => (
            <div key={id} style={qBlock}>
              <div style={rowBetween}>
                <span style={lblMuted}>{s.scene} {ni + 1}{id === content.start ? ' · ' + s.startScene : ''}</span>
                {ids.length > 1 && <button style={linkDanger} onClick={() => up((n) => { delete n.nodes[id]; if (n.start === id) n.start = Object.keys(n.nodes)[0] })}>{s.removeQ}</button>}
              </div>
              <Loc val={content.nodes[id].text} ph={s.sceneText} set={(f, v) => up((n) => { n.nodes[id].text[f] = v })} />
              {content.nodes[id].choices.map((ch, chi) => (
                <div key={chi} style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 8, marginBottom: 8 }}>
                  <Loc val={ch.label} ph={s.choiceLabel} set={(f, v) => up((n) => { n.nodes[id].choices[chi].label[f] = v })} />
                  <Loc val={ch.feedback} ph={s.feedback} set={(f, v) => up((n) => { n.nodes[id].choices[chi].feedback[f] = v })} />
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <span style={lblMuted}>{s.goesTo}</span>
                    <select style={{ ...inp, marginBottom: 0, flex: '1 1 120px' }} value={ch.goto} onChange={(e) => up((n) => { n.nodes[id].choices[chi].goto = e.target.value })}>
                      <option value="">{s.theEnd}</option>
                      {ids.filter((x) => x !== id).map((x) => <option key={x} value={x}>{s.scene} {ids.indexOf(x) + 1}</option>)}
                    </select>
                    {content.nodes[id].choices.length > 1 && <button style={linkDanger} onClick={() => up((n) => n.nodes[id].choices.splice(chi, 1))}>×</button>}
                  </div>
                </div>
              ))}
              <button style={ghostSm} onClick={() => up((n) => n.nodes[id].choices.push(blankChoice()))}>{s.addChoice}</button>
            </div>
          ))}
          <button style={ghost} onClick={() => up((n) => { const nums = Object.keys(n.nodes).map((k) => parseInt(k.replace('n', '')) || 0); const id = 'n' + (Math.max(0, ...nums) + 1); n.nodes[id] = { text: blankL(), choices: [blankChoice()] } })}>{s.addNode}</button>
        </div>
      )
    }
    return null
  }

  return (
    <div>
      {onAI && (
        <div style={aiBox}>
          <input style={{ ...inp, marginBottom: 0, flex: '1 1 160px' }} placeholder={s.aiTopic} value={topic} onChange={(e) => setTopic(e.target.value)} />
          <button style={gold} disabled={aiBusy} onClick={() => onAI(topic)}>{s.genAI}</button>
        </div>
      )}
      {body()}
    </div>
  )
}

const inp = { flex: 1, width: '100%', background: 'var(--black)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--white)', padding: '8px 10px', fontSize: 13, marginBottom: 6 }
const qBlock = { border: '1px solid var(--border)', borderRadius: 10, padding: 12, margin: '12px 0' }
const aiBox = { display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', background: 'rgba(245,196,81,0.06)', border: '1px solid rgba(245,196,81,0.2)', borderRadius: 10, padding: 8, marginBottom: 14 }
const ghost = { border: '1px solid var(--border)', borderRadius: 9, padding: '9px 14px', cursor: 'pointer', fontSize: 13, fontWeight: 600, background: 'transparent', color: 'var(--white)' }
const ghostSm = { ...ghost, padding: '6px 10px', fontSize: 12 }
const gold = { border: 'none', borderRadius: 9, padding: '9px 14px', cursor: 'pointer', fontSize: 12.5, fontWeight: 600, background: '#f5c451', color: '#3a2a02', whiteSpace: 'nowrap' }
const rowBetween = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 6 }
const lbl = { display: 'block', fontSize: 12.5, color: 'var(--muted)', marginBottom: 6 }
const lblMuted = { fontSize: 12, color: 'var(--muted)', margin: '6px 0' }
const linkDanger = { border: 'none', background: 'transparent', color: '#f2729b', cursor: 'pointer', fontSize: 12.5 }
