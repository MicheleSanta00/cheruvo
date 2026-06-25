/**
 * Workspace.jsx — area admin: crea/modifica i quiz (template + contenuti) con anteprima live + AI.
 * Per ora gestisce il motore Quiz; gli altri motori arrivano nelle fasi successive.
 */
import { useState, useEffect } from 'react'
import { adminLessons, getLesson, createLesson, updateLesson, deleteLesson, aiDraft } from './academyApi.js'
import QuizEngine from './QuizEngine.jsx'
import AdminSettings from './AdminSettings.jsx'
import { pick } from './academyStrings.js'

const blankQ = () => ({ q: { it: '', en: '' }, options: [ {it:'',en:''}, {it:'',en:''}, {it:'',en:''}, {it:'',en:''} ], correct: 0, explain: { it: '', en: '' } })
const blankQuiz = () => ({ id: null, title: { it: '', en: '' }, status: 'draft', content: { timer_sec: 30, pass_score: 70, questions: [ blankQ() ] } })

function normalize(content) {
  const qs = (content && content.questions) || []
  return {
    timer_sec: content?.timer_sec ?? 30,
    pass_score: content?.pass_score ?? 70,
    questions: qs.map(q => {
      const opts = (q.options || []).map(o => ({ it: o?.it || '', en: o?.en || '' }))
      while (opts.length < 4) opts.push({ it: '', en: '' })
      return { q: { it: q?.q?.it || '', en: q?.q?.en || '' }, options: opts.slice(0, 4),
               correct: q?.correct ?? 0, explain: { it: q?.explain?.it || '', en: q?.explain?.en || '' } }
    }),
  }
}

export default function Workspace({ lang, strings, user }) {
  const s = strings
  const [tab, setTab] = useState('lessons')
  const [lessons, setLessons] = useState([])
  const [editing, setEditing] = useState(null)
  const [topic, setTopic] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const reload = () => adminLessons().then(d => setLessons(d.lessons)).catch(e => setErr(e.message))
  useEffect(() => { reload() }, [])

  const up = (mut) => setEditing(prev => { const n = JSON.parse(JSON.stringify(prev)); mut(n); return n })

  const openEdit = async (l) => {
    setErr('')
    try { const full = await getLesson(l.id); setEditing({ id: full.id, title: full.title || {it:'',en:''}, status: full.status, content: normalize(full.content) }) }
    catch (e) { setErr(e.message) }
  }

  const save = async (status) => {
    setBusy(true); setErr('')
    try {
      const payload = { type: 'quiz', title: editing.title, content: editing.content, status }
      if (editing.id) await updateLesson(editing.id, payload)
      else await createLesson(payload)
      setEditing(null); reload()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const runAI = async () => {
    if (!topic) return
    setBusy(true); setErr('')
    try { const c = await aiDraft(topic, 5); up(n => { n.content = normalize(c) }) }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const remove = async (id) => {
    if (!window.confirm(s.confirmDel)) return
    try { await deleteLesson(id); reload() } catch (e) { setErr(e.message) }
  }

  // ── Lista + Impostazioni ──
  if (!editing) {
    return (
      <div>
        <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
          <button style={tab === 'lessons' ? tabOn : tabOff} onClick={() => setTab('lessons')}>{s.lessonsTab}</button>
          <button style={tab === 'settings' ? tabOn : tabOff} onClick={() => setTab('settings')}>⚙ {s.settings}</button>
        </div>

        {tab === 'settings' ? (
          <AdminSettings lang={lang} strings={s} user={user} />
        ) : (
          <div>
            <div style={rowBetween}>
              <h2 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>{s.workspace}</h2>
              <button style={primary} onClick={() => setEditing(blankQuiz())}>{s.newLesson}</button>
            </div>
            {err && <div style={errBox}>{err}</div>}
            <div style={{ display: 'grid', gap: 8, marginTop: 16 }}>
              {lessons.map(l => (
                <div key={l.id} style={listRow}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={typeBadge}>{l.type}</span>
                    <span style={{ fontSize: 14 }}>{pick(l.title, lang) || '—'}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span style={l.status === 'published' ? livePill : draftPill}>{l.status === 'published' ? s.live : s.draft}</span>
                    <button style={link} onClick={() => openEdit(l)}>{s.edit}</button>
                    <button style={linkDanger} onClick={() => remove(l.id)}>{s.del}</button>
                  </div>
                </div>
              ))}
              {!lessons.length && <div style={{ color: 'var(--muted)', fontSize: 13 }}>—</div>}
            </div>
          </div>
        )}
      </div>
    )
  }

  // ── Editor quiz ──
  const c = editing.content
  return (
    <div>
      <button style={ghost} onClick={() => setEditing(null)}>{s.backToList}</button>
      {err && <div style={{ ...errBox, marginTop: 12 }}>{err}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16, marginTop: 14 }}>
        {/* form */}
        <div style={card}>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
            <input style={{ ...inp, flex: '1 1 140px', width: 'auto' }} placeholder={s.title + ' (IT)'} value={editing.title.it} onChange={e => up(n => n.title.it = e.target.value)} />
            <input style={{ ...inp, flex: '1 1 140px', width: 'auto' }} placeholder={s.title + ' (EN)'} value={editing.title.en} onChange={e => up(n => n.title.en = e.target.value)} />
          </div>

          <div style={aiBox}>
            <input style={{ ...inp, marginBottom: 0 }} placeholder={s.aiTopic} value={topic} onChange={e => setTopic(e.target.value)} />
            <button style={gold} disabled={busy} onClick={runAI}>{s.genAI}</button>
          </div>

          {c.questions.map((q, qi) => (
            <div key={qi} style={qBlock}>
              <div style={rowBetween}>
                <span style={{ fontSize: 12, color: 'var(--muted)' }}>{s.question} {qi + 1}</span>
                {c.questions.length > 1 && <button style={linkDanger} onClick={() => up(n => n.content.questions.splice(qi, 1))}>{s.removeQ}</button>}
              </div>
              <input style={inp} placeholder={s.question + ' (IT)'} value={q.q.it} onChange={e => up(n => n.content.questions[qi].q.it = e.target.value)} />
              <input style={inp} placeholder={s.question + ' (EN)'} value={q.q.en} onChange={e => up(n => n.content.questions[qi].q.en = e.target.value)} />
              <div style={{ fontSize: 12, color: 'var(--muted)', margin: '6px 0' }}>{s.options}</div>
              {q.options.map((o, oi) => (
                <div key={oi} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
                  <input type="radio" name={`c-${qi}`} checked={q.correct === oi} onChange={() => up(n => n.content.questions[qi].correct = oi)} />
                  <input style={{ ...inp, marginBottom: 0, flex: '1 1 130px', width: 'auto' }} placeholder={`IT ${oi + 1}`} value={o.it} onChange={e => up(n => n.content.questions[qi].options[oi].it = e.target.value)} />
                  <input style={{ ...inp, marginBottom: 0, flex: '1 1 130px', width: 'auto' }} placeholder={`EN ${oi + 1}`} value={o.en} onChange={e => up(n => n.content.questions[qi].options[oi].en = e.target.value)} />
                </div>
              ))}
              <input style={{ ...inp, marginTop: 6 }} placeholder={s.explanation + ' (IT)'} value={q.explain.it} onChange={e => up(n => n.content.questions[qi].explain.it = e.target.value)} />
              <input style={inp} placeholder={s.explanation + ' (EN)'} value={q.explain.en} onChange={e => up(n => n.content.questions[qi].explain.en = e.target.value)} />
            </div>
          ))}

          <button style={ghost} onClick={() => up(n => n.content.questions.push(blankQ()))}>{s.addQuestion}</button>

          <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
            <button style={primary} disabled={busy} onClick={() => save('published')}>{s.publish}</button>
            <button style={ghost} disabled={busy} onClick={() => save('draft')}>{s.saveDraft}</button>
          </div>
        </div>

        {/* anteprima live */}
        <div>
          <div style={{ fontSize: 11, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 8 }}>{s.preview}</div>
          <div style={{ ...card, borderStyle: 'dashed' }}>
            <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>{pick(editing.title, lang) || '—'}</div>
            <QuizEngine content={editing.content} lang={lang} mode="preview" strings={s} />
          </div>
        </div>
      </div>
    </div>
  )
}

const rowBetween = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }
const tabOff = { border: '1px solid var(--border)', background: 'transparent', color: 'var(--muted)', borderRadius: 9, padding: '7px 14px', cursor: 'pointer', fontSize: 13, fontWeight: 600 }
const tabOn = { ...tabOff, color: 'var(--white)', borderColor: '#34d399' }
const card = { background: 'var(--near-black)', border: '1px solid var(--border)', borderRadius: 14, padding: 16 }
const inp = { flex: 1, width: '100%', background: 'var(--black)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--white)', padding: '8px 10px', fontSize: 13, marginBottom: 6 }
const qBlock = { border: '1px solid var(--border)', borderRadius: 10, padding: 12, margin: '12px 0' }
const aiBox = { display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', background: 'rgba(245,196,81,0.06)', border: '1px solid rgba(245,196,81,0.2)', borderRadius: 10, padding: 8, marginBottom: 12 }
const primary = { border: 'none', borderRadius: 9, padding: '9px 16px', cursor: 'pointer', fontSize: 13, fontWeight: 600, background: '#34d399', color: '#04221a' }
const gold = { border: 'none', borderRadius: 9, padding: '9px 14px', cursor: 'pointer', fontSize: 12.5, fontWeight: 600, background: '#f5c451', color: '#3a2a02', whiteSpace: 'nowrap' }
const ghost = { border: '1px solid var(--border)', borderRadius: 9, padding: '9px 14px', cursor: 'pointer', fontSize: 13, fontWeight: 600, background: 'transparent', color: 'var(--white)' }
const link = { border: 'none', background: 'transparent', color: 'var(--azure)', cursor: 'pointer', fontSize: 12.5 }
const linkDanger = { border: 'none', background: 'transparent', color: '#f2729b', cursor: 'pointer', fontSize: 12.5 }
const listRow = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'var(--near-black)', border: '1px solid var(--border)', borderRadius: 10, padding: '11px 13px' }
const typeBadge = { fontSize: 10.5, fontWeight: 600, padding: '2px 8px', borderRadius: 99, background: 'rgba(106,166,255,0.16)', color: '#9cc0ff' }
const livePill = { fontSize: 10.5, fontWeight: 600, padding: '2px 8px', borderRadius: 99, background: 'rgba(52,211,153,0.16)', color: '#7fe9c6' }
const draftPill = { fontSize: 10.5, fontWeight: 600, padding: '2px 8px', borderRadius: 99, background: 'rgba(245,196,81,0.16)', color: '#f5c451' }
const errBox = { background: 'rgba(242,114,155,0.12)', border: '1px solid rgba(242,114,155,0.3)', color: '#f2729b', borderRadius: 10, padding: '10px 13px', fontSize: 13 }
