/**
 * Workspace.jsx — area admin: crea/modifica lezioni di OGNI tipo (template + contenuti),
 * con anteprima live; scheda Impostazioni per profilo e gestione admin.
 */
import { useState, useEffect } from 'react'
import { adminLessons, getLesson, createLesson, updateLesson, deleteLesson, aiDraft } from './academyApi.js'
import LessonRenderer from './LessonRenderer.jsx'
import LessonForm, { blankContent } from './LessonForm.jsx'
import AdminSettings from './AdminSettings.jsx'
import Icon from '../components/Icon.jsx'
import { pick } from './academyStrings.js'

const TYPES = [
  { t: 'quiz', icon: 'quiz', label: { it: 'Quiz a tempo', en: 'Timed quiz' } },
  { t: 'simulator', icon: 'simulator', label: { it: 'Simulatore', en: 'Simulator' } },
  { t: 'flashcard', icon: 'flashcards', label: { it: 'Flashcard', en: 'Flashcards' } },
  { t: 'scenario', icon: 'scenario', label: { it: 'Scenario', en: 'Scenario' } },
]
const newLesson = (type) => ({ id: null, type, title: { it: '', en: '' }, status: 'draft', level: 'base', content: blankContent(type) })

export default function Workspace({ lang, strings, user }) {
  const s = strings
  const [tab, setTab] = useState('lessons')
  const [lessons, setLessons] = useState([])
  const [editing, setEditing] = useState(null)
  const [picking, setPicking] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const reload = () => adminLessons().then((d) => setLessons(d.lessons)).catch((e) => setErr(e.message))
  useEffect(() => { reload() }, [])

  const openEdit = async (l) => {
    setErr('')
    try {
      const full = await getLesson(l.id)
      setEditing({ id: full.id, type: full.type, title: full.title || { it: '', en: '' }, status: full.status, level: full.level || 'base', content: full.content || blankContent(full.type) })
    } catch (e) { setErr(e.message) }
  }

  const save = async (status) => {
    setBusy(true); setErr('')
    try {
      const payload = { type: editing.type, title: editing.title, content: editing.content, status, level: editing.level }
      if (editing.id) await updateLesson(editing.id, payload)
      else await createLesson(payload)
      setEditing(null); reload()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const onAI = async (topic) => {
    if (!topic) return
    setBusy(true); setErr('')
    try { const c = await aiDraft(topic, editing.type, 5); setEditing((p) => ({ ...p, content: c })) }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const remove = async (id) => {
    if (!window.confirm(s.confirmDel)) return
    try { await deleteLesson(id); reload() } catch (e) { setErr(e.message) }
  }

  // ── Editor ──
  if (editing) {
    return (
      <div>
        <button style={ghost} onClick={() => setEditing(null)}>{s.backToList}</button>
        {err && <div style={{ ...errBox, marginTop: 12 }}>{err}</div>}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16, marginTop: 14 }}>
          <div style={card}>
            <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
              <input style={{ ...inp, flex: '1 1 140px', width: 'auto' }} placeholder={s.title + ' (IT)'} value={editing.title.it} onChange={(e) => setEditing((p) => ({ ...p, title: { ...p.title, it: e.target.value } }))} />
              <input style={{ ...inp, flex: '1 1 140px', width: 'auto' }} placeholder={s.title + ' (EN)'} value={editing.title.en} onChange={(e) => setEditing((p) => ({ ...p, title: { ...p.title, en: e.target.value } }))} />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <label style={{ fontSize: 12.5, color: 'var(--muted)' }}>{s.level}</label>
              <select style={{ ...inp, marginBottom: 0, flex: 1 }} value={editing.level} onChange={(e) => setEditing((p) => ({ ...p, level: e.target.value }))}>
                <option value="base">{s.levelBase}</option>
                <option value="intermedio">{s.levelInter}</option>
                <option value="avanzato">{s.levelAdv}</option>
              </select>
            </div>
            <LessonForm type={editing.type} content={editing.content} onContent={(c) => setEditing((p) => ({ ...p, content: c }))} lang={lang} s={s} onAI={onAI} aiBusy={busy} />
            <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
              <button style={primary} disabled={busy} onClick={() => save('published')}>{s.publish}</button>
              <button style={ghost} disabled={busy} onClick={() => save('draft')}>{s.saveDraft}</button>
            </div>
          </div>
          <div>
            <div style={{ fontSize: 11, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 8 }}>{s.preview}</div>
            <div style={{ ...card, borderStyle: 'dashed' }}>
              <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>{pick(editing.title, lang) || '—'}</div>
              <LessonRenderer type={editing.type} content={editing.content} lang={lang} mode="preview" strings={s} />
            </div>
          </div>
        </div>
      </div>
    )
  }

  // ── Lista + Impostazioni ──
  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <button style={tab === 'lessons' ? tabOn : tabOff} onClick={() => setTab('lessons')}>{s.lessonsTab}</button>
        <button style={{ ...(tab === 'settings' ? tabOn : tabOff), display: 'inline-flex', alignItems: 'center', gap: 6 }} onClick={() => setTab('settings')}><Icon name="settings" size={13} /> {s.settings}</button>
      </div>

      {tab === 'settings' ? (
        <AdminSettings lang={lang} strings={s} user={user} />
      ) : (
        <div>
          <div style={rowBetween}>
            <h2 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>{s.workspace}</h2>
            <button style={primary} onClick={() => setPicking((p) => !p)}>{s.newLesson}</button>
          </div>

          {picking && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 12.5, color: 'var(--muted)', marginBottom: 8 }}>{s.chooseType}</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 10 }}>
                {TYPES.map((ty) => (
                  <button key={ty.t} style={pickCard} onClick={() => { setPicking(false); setEditing(newLesson(ty.t)) }}>
                    <div><Icon name={ty.icon} size={24} /></div>
                    <div style={{ fontSize: 13, fontWeight: 600, marginTop: 6 }}>{pick(ty.label, lang)}</div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {err && <div style={{ ...errBox, marginTop: 12 }}>{err}</div>}

          <div style={{ display: 'grid', gap: 8, marginTop: 16 }}>
            {lessons.map((l) => (
              <div key={l.id} style={listRow}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                  <span style={typeBadge}>{l.type}</span>
                  <span style={levelBadge(l.level)}>{l.level === 'avanzato' ? s.levelAdv : l.level === 'intermedio' ? s.levelInter : s.levelBase}</span>
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

const card = { background: 'var(--near-black)', border: '1px solid var(--border)', borderRadius: 14, padding: 16 }
const inp = { flex: 1, width: '100%', background: 'var(--black)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--white)', padding: '8px 10px', fontSize: 13, marginBottom: 6 }
const primary = { border: 'none', borderRadius: 9, padding: '9px 16px', cursor: 'pointer', fontSize: 13, fontWeight: 600, background: '#34d399', color: '#04221a' }
const ghost = { border: '1px solid var(--border)', borderRadius: 9, padding: '9px 14px', cursor: 'pointer', fontSize: 13, fontWeight: 600, background: 'transparent', color: 'var(--white)' }
const link = { border: 'none', background: 'transparent', color: 'var(--azure)', cursor: 'pointer', fontSize: 12.5 }
const linkDanger = { border: 'none', background: 'transparent', color: '#f2729b', cursor: 'pointer', fontSize: 12.5 }
const rowBetween = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }
const tabOff = { border: '1px solid var(--border)', background: 'transparent', color: 'var(--muted)', borderRadius: 9, padding: '7px 14px', cursor: 'pointer', fontSize: 13, fontWeight: 600 }
const tabOn = { ...tabOff, color: 'var(--white)', borderColor: '#34d399' }
const pickCard = { background: 'var(--near-black)', border: '1px solid var(--border)', borderRadius: 12, padding: 14, cursor: 'pointer', textAlign: 'center', color: 'var(--white)' }
const listRow = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'var(--near-black)', border: '1px solid var(--border)', borderRadius: 10, padding: '11px 13px' }
const typeBadge = { fontSize: 10.5, fontWeight: 600, padding: '2px 8px', borderRadius: 99, background: 'rgba(106,166,255,0.16)', color: '#9cc0ff' }
const levelBadge = (lvl) => ({ fontSize: 10.5, fontWeight: 600, padding: '2px 8px', borderRadius: 99, background: lvl === 'avanzato' ? 'rgba(242,114,155,0.16)' : lvl === 'intermedio' ? 'rgba(245,196,81,0.16)' : 'rgba(52,211,153,0.16)', color: lvl === 'avanzato' ? '#ffa6c2' : lvl === 'intermedio' ? '#f5c451' : '#7fe9c6' })
const livePill = { fontSize: 10.5, fontWeight: 600, padding: '2px 8px', borderRadius: 99, background: 'rgba(52,211,153,0.16)', color: '#7fe9c6' }
const draftPill = { fontSize: 10.5, fontWeight: 600, padding: '2px 8px', borderRadius: 99, background: 'rgba(245,196,81,0.16)', color: '#f5c451' }
const errBox = { background: 'rgba(242,114,155,0.12)', border: '1px solid rgba(242,114,155,0.3)', color: '#f2729b', borderRadius: 10, padding: '10px 13px', fontSize: 13 }
