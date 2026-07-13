/**
 * ClassView.jsx — interno di una classe: bacheca (post), membri e chat.
 * Il docente pubblica annunci, materiali (link), lezioni assegnate e file (upload).
 */
import { useState, useEffect, useRef } from 'react'
import { getClass, createPost, deletePost, getMessages, sendMessage, leaveClass, uploadClassFile } from './classroomApi.js'
import { getPaths, myLessons } from './academyApi.js'
import { pick } from './academyStrings.js'

const ACC = '#34d399'
const postKind = (k, s) => k === 'announcement' ? s.announcement : k === 'material' ? s.material : k === 'lesson' ? s.assignLesson : k === 'file' ? s.uploadFile : k

export default function ClassView({ classId, s, lang, onBack, onOpenLesson }) {
  const [data, setData] = useState(null)
  const [tab, setTab] = useState('stream')
  const [err, setErr] = useState('')
  const [msgs, setMsgs] = useState([])
  const [chatInput, setChatInput] = useState('')
  const [pkind, setPkind] = useState('announcement')
  const [ptext, setPtext] = useState('')
  const [purl, setPurl] = useState('')
  const [plesson, setPlesson] = useState('')
  const [lessons, setLessons] = useState([])
  const [busy, setBusy] = useState(false)
  const fileRef = useRef(null)

  const load = () => getClass(classId).then(setData).catch((e) => setErr(e.message))
  const loadMsgs = () => getMessages(classId).then((d) => setMsgs(d.messages)).catch(() => {})

  useEffect(() => {
    load()
    // Nel selettore "Assegna lezione": prima le lezioni del docente (create dal
    // wizard "Lezioni dal libro"), poi i contenuti Academy pubblicati.
    Promise.all([
      myLessons().then((d) => (d.lessons || []).filter((l) => l.status === 'published')).catch(() => []),
      getPaths().then((d) => { const ls = []; d.paths.forEach((p) => p.lessons.forEach((l) => ls.push(l))); return ls }).catch(() => []),
    ]).then(([mine, global]) => {
      const seen = new Set()
      setLessons([...mine, ...global].filter((l) => (seen.has(l.id) ? false : seen.add(l.id))))
    })
  }, [classId])

  useEffect(() => {
    if (tab !== 'chat') return
    loadMsgs()
    const t = setInterval(loadMsgs, 5000)
    return () => clearInterval(t)
  }, [tab, classId])

  if (!data) return <div style={{ color: 'var(--muted)', fontSize: 13 }}>{err || s.loading}</div>

  const submitPost = async () => {
    setBusy(true); setErr('')
    try {
      if (pkind === 'lesson') {
        const l = lessons.find((x) => x.id === plesson)
        await createPost(classId, { kind: 'lesson', lesson_id: plesson || null, text: l ? pick(l.title, lang) : ptext || null })
      } else {
        await createPost(classId, { kind: pkind, text: ptext || null, url: purl || null })
      }
      setPtext(''); setPurl(''); setPlesson(''); load()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const onFile = async (e) => {
    const f = e.target.files[0]; if (!f) return
    setBusy(true); setErr('')
    try { const up = await uploadClassFile(classId, f); await createPost(classId, { kind: 'file', url: up.url, file_name: up.name, text: ptext || null }); setPtext(''); load() }
    catch (er) { setErr(er.message) } finally { setBusy(false); if (fileRef.current) fileRef.current.value = '' }
  }
  const send = async () => {
    const b = chatInput.trim(); if (!b) return
    setChatInput('')
    try { await sendMessage(classId, b); loadMsgs() } catch (e) { setErr(e.message) }
  }
  const doLeave = async () => {
    if (!window.confirm(s.confirmLeave)) return
    try { await leaveClass(classId); onBack() } catch (e) { setErr(e.message) }
  }

  return (
    <div>
      <button style={ghost} onClick={onBack}>← {s.classes}</button>

      <div style={{ ...card, marginTop: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <h2 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>{data.name}</h2>
          {data.is_teacher
            ? <span style={{ fontSize: 12.5, color: 'var(--muted)' }}>{s.shareCode}: <b title={s.copy} style={{ color: ACC, cursor: 'pointer' }} onClick={() => navigator.clipboard && navigator.clipboard.writeText(data.join_code)}>{data.join_code}</b></span>
            : <button style={linkDanger} onClick={doLeave}>{s.leave}</button>}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, margin: '14px 0' }}>
        {['stream', 'members', 'chat'].map((tb) => (
          <button key={tb} style={tab === tb ? tabOn : tabOff} onClick={() => setTab(tb)}>
            {tb === 'stream' ? s.stream : tb === 'members' ? s.membersTab : s.chat}
          </button>
        ))}
      </div>

      {err && <div style={errBox}>{err}</div>}

      {tab === 'stream' && (
        <div>
          {data.is_teacher && (
            <div style={card}>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
                {[['announcement', s.announcement], ['material', s.material], ['lesson', s.assignLesson], ['file', s.uploadFile]].map(([k, lab]) => (
                  <button key={k} style={pkind === k ? tabOn : tabOff} onClick={() => setPkind(k)}>{lab}</button>
                ))}
              </div>
              <textarea style={{ ...inp, minHeight: 54 }} placeholder={s.writeHere} value={ptext} onChange={(e) => setPtext(e.target.value)} />
              {pkind === 'material' && <input style={inp} placeholder={s.linkUrl} value={purl} onChange={(e) => setPurl(e.target.value)} />}
              {pkind === 'lesson' && (
                <select style={inp} value={plesson} onChange={(e) => setPlesson(e.target.value)}>
                  <option value="">—</option>
                  {lessons.map((l) => <option key={l.id} value={l.id}>{pick(l.title, lang)}</option>)}
                </select>
              )}
              {pkind === 'file'
                ? <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}><input ref={fileRef} type="file" onChange={onFile} style={{ fontSize: 13 }} />{busy && <span style={{ color: 'var(--muted)', fontSize: 12 }}>…</span>}</div>
                : <button style={primary} disabled={busy} onClick={submitPost}>{s.post}</button>}
            </div>
          )}
          <div style={{ display: 'grid', gap: 10, marginTop: data.is_teacher ? 14 : 0 }}>
            {data.posts.map((p) => (
              <div key={p.id} style={card}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11.5, color: 'var(--muted)', marginBottom: 6 }}>
                  <span>{postKind(p.kind, s)} · {p.author}</span>
                  {data.is_teacher && <button style={linkDanger} onClick={async () => { await deletePost(p.id); load() }}>×</button>}
                </div>
                {p.text && <div style={{ fontSize: 14, marginBottom: 6, whiteSpace: 'pre-wrap' }}>{p.text}</div>}
                {p.kind === 'material' && p.url && <a href={p.url} target="_blank" rel="noreferrer" style={linkA}>{p.url}</a>}
                {p.kind === 'file' && p.url && <a href={p.url} target="_blank" rel="noreferrer" style={linkA}>📎 {p.file_name || 'file'}</a>}
                {p.kind === 'lesson' && p.lesson_id && <button style={primary} onClick={() => onOpenLesson(p.lesson_id)}>📘 {s.openLesson}</button>}
              </div>
            ))}
            {!data.posts.length && <div style={{ color: 'var(--muted)', fontSize: 13 }}>—</div>}
          </div>
        </div>
      )}

      {tab === 'members' && (
        <div style={{ display: 'grid', gap: 8 }}>
          {data.members.map((m) => (
            <div key={m.user_id} style={rowItem}>
              <span style={{ fontSize: 14 }}>{m.name}</span>
              <span style={m.role === 'teacher' ? livePill : draftPill}>{m.role === 'teacher' ? s.roleTeacher : s.roleStudent}</span>
            </div>
          ))}
        </div>
      )}

      {tab === 'chat' && (
        <div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 10, maxHeight: 340, overflowY: 'auto' }}>
            {msgs.map((m) => (
              <div key={m.id} style={{ alignSelf: m.is_me ? 'flex-end' : 'flex-start', background: m.is_me ? 'rgba(52,211,153,0.14)' : 'var(--near-black)', border: '1px solid var(--border)', borderRadius: 10, padding: '8px 11px', maxWidth: '85%' }}>
                {!m.is_me && <div style={{ fontSize: 11, color: ACC, marginBottom: 2 }}>{m.name}</div>}
                <div style={{ fontSize: 13.5, whiteSpace: 'pre-wrap' }}>{m.body}</div>
              </div>
            ))}
            {!msgs.length && <div style={{ color: 'var(--muted)', fontSize: 13 }}>—</div>}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <input style={inp} placeholder={s.writeMsg} value={chatInput} onChange={(e) => setChatInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') send() }} />
            <button style={{ ...primary, width: 'auto' }} onClick={send}>{s.send}</button>
          </div>
        </div>
      )}
    </div>
  )
}

const card = { background: 'var(--near-black)', border: '1px solid var(--border)', borderRadius: 14, padding: 16 }
const ghost = { border: '1px solid var(--border)', borderRadius: 9, padding: '9px 14px', cursor: 'pointer', fontSize: 13, fontWeight: 600, background: 'transparent', color: 'var(--white)' }
const primary = { border: 'none', borderRadius: 9, padding: '9px 16px', cursor: 'pointer', fontSize: 13, fontWeight: 600, background: ACC, color: '#04221a', width: '100%' }
const inp = { width: '100%', background: 'var(--black)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--white)', padding: '9px 11px', fontSize: 13.5, marginBottom: 10 }
const tabOff = { border: '1px solid var(--border)', background: 'transparent', color: 'var(--muted)', borderRadius: 9, padding: '7px 12px', cursor: 'pointer', fontSize: 12.5, fontWeight: 600 }
const tabOn = { ...tabOff, color: 'var(--white)', borderColor: ACC }
const rowItem = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'var(--near-black)', border: '1px solid var(--border)', borderRadius: 10, padding: '10px 12px' }
const livePill = { fontSize: 10.5, fontWeight: 600, padding: '2px 8px', borderRadius: 99, background: 'rgba(52,211,153,0.16)', color: '#7fe9c6' }
const draftPill = { fontSize: 10.5, fontWeight: 600, padding: '2px 8px', borderRadius: 99, background: 'rgba(106,166,255,0.16)', color: '#9cc0ff' }
const linkA = { color: '#6aa6ff', fontSize: 13.5, wordBreak: 'break-all' }
const linkDanger = { border: 'none', background: 'transparent', color: '#f2729b', cursor: 'pointer', fontSize: 13 }
const errBox = { background: 'rgba(242,114,155,0.12)', border: '1px solid rgba(242,114,155,0.3)', color: '#f2729b', borderRadius: 10, padding: '10px 13px', fontSize: 13, marginBottom: 14 }
