/**
 * Classroom.jsx — elenco delle classi dell'utente, creazione (solo docenti) e ingresso con codice.
 */
import { useState, useEffect } from 'react'
import { myClasses, createClass, joinClass } from './classroomApi.js'

export default function Classroom({ s, isTeacher, onOpen }) {
  const [classes, setClasses] = useState([])
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const reload = () => myClasses().then((d) => setClasses(d.classes)).catch((e) => setErr(e.message))
  useEffect(() => { reload() }, [])

  const create = async () => {
    if (!name.trim()) return
    setBusy(true); setErr('')
    try { const r = await createClass(name); setName(''); reload(); onOpen(r.id) }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const join = async () => {
    if (!code.trim()) return
    setBusy(true); setErr('')
    try { const r = await joinClass(code); setCode(''); reload(); onOpen(r.id) }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <div>
      <div style={eyebrow}>{s.classes}</div>
      <h1 style={{ fontSize: 24, fontWeight: 600, margin: '6px 0 16px' }}>{s.classesTitle}</h1>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12, marginBottom: 20 }}>
        {isTeacher && (
          <div style={card}>
            <div style={cardH}>{s.createClass}</div>
            <input style={inp} placeholder={s.className} value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') create() }} />
            <button style={primary} disabled={busy} onClick={create}>{s.createClass}</button>
          </div>
        )}
        <div style={card}>
          <div style={cardH}>{s.joinClass}</div>
          <input style={inp} placeholder={s.joinCode} value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} onKeyDown={(e) => { if (e.key === 'Enter') join() }} />
          <button style={ghost} disabled={busy} onClick={join}>{s.joinClass}</button>
        </div>
      </div>

      {err && <div style={errBox}>{err}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
        {classes.map((c) => (
          <div key={c.id} style={{ ...card, cursor: 'pointer' }} onClick={() => onOpen(c.id)}>
            <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>{c.name}</div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={c.role === 'teacher' ? livePill : draftPill}>{c.role === 'teacher' ? s.roleTeacher : s.roleStudent}</span>
              <span style={{ fontSize: 12, color: 'var(--muted)' }}>{c.members} {s.membersLabel}</span>
            </div>
          </div>
        ))}
        {!classes.length && <div style={{ color: 'var(--muted)', fontSize: 13 }}>{s.noClasses}</div>}
      </div>
    </div>
  )
}

const ACC = '#34d399'
const eyebrow = { fontSize: 12.5, letterSpacing: '.1em', textTransform: 'uppercase', color: ACC, fontWeight: 600 }
const card = { background: 'var(--near-black)', border: '1px solid var(--border)', borderRadius: 14, padding: 16 }
const cardH = { fontSize: 13, fontWeight: 600, color: 'var(--muted)', marginBottom: 10 }
const inp = { width: '100%', background: 'var(--black)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--white)', padding: '9px 11px', fontSize: 13.5, marginBottom: 10 }
const primary = { border: 'none', borderRadius: 9, padding: '9px 16px', cursor: 'pointer', fontSize: 13, fontWeight: 600, background: ACC, color: '#04221a', width: '100%' }
const ghost = { border: '1px solid var(--border)', borderRadius: 9, padding: '9px 16px', cursor: 'pointer', fontSize: 13, fontWeight: 600, background: 'transparent', color: 'var(--white)', width: '100%' }
const livePill = { fontSize: 10.5, fontWeight: 600, padding: '2px 8px', borderRadius: 99, background: 'rgba(52,211,153,0.16)', color: '#7fe9c6' }
const draftPill = { fontSize: 10.5, fontWeight: 600, padding: '2px 8px', borderRadius: 99, background: 'rgba(106,166,255,0.16)', color: '#9cc0ff' }
const errBox = { background: 'rgba(242,114,155,0.12)', border: '1px solid rgba(242,114,155,0.3)', color: '#f2729b', borderRadius: 10, padding: '10px 13px', fontSize: 13, marginBottom: 14 }
