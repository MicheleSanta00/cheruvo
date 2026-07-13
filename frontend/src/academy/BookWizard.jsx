/**
 * BookWizard.jsx — "Lezioni dal Libro": wizard docente in 3 momenti
 * (Carica → Scegli → Rivedi). Il docente carica PDF o foto del SUO materiale,
 * l'AI propone l'indice, genera bozze nei 4 motori e le si assegna alla classe.
 * Le bozze restano private (visibility 'class') finché il docente non pubblica.
 */
import { useState, useEffect, useRef } from 'react'
import { bookUpload, bookJob, bookGenerate, bookRegenerate, bookPublish, getLesson, updateLesson, deleteLesson } from './academyApi.js'
import { myClasses } from './classroomApi.js'
import LessonRenderer from './LessonRenderer.jsx'
import LessonForm from './LessonForm.jsx'
import { pick } from './academyStrings.js'

const ACC = '#34d399'
const TYPES = [
  { t: 'quiz', icon: '❓', label: { it: 'Quiz', en: 'Quiz' } },
  { t: 'flashcard', icon: '🃏', label: { it: 'Flashcard', en: 'Flashcards' } },
  { t: 'scenario', icon: '🌿', label: { it: 'Scenario', en: 'Scenario' } },
  { t: 'simulator', icon: '🎚️', label: { it: 'Simulatore', en: 'Simulator' } },
]
const typeIcon = (t) => (TYPES.find((x) => x.t === t) || {}).icon || '📘'

export default function BookWizard({ lang, s, onDone }) {
  const [step, setStep] = useState('upload')      // upload | toc | config | progress | review | assign | done
  const [phase, setPhase] = useState('extract')   // extract | generate
  const [files, setFiles] = useState([])
  const [jobId, setJobId] = useState(null)
  const [job, setJob] = useState(null)
  const [toc, setToc] = useState([])              // [{idx,title,start,end,checked}]
  const [perCh, setPerCh] = useState(4)
  const [difficulty, setDifficulty] = useState('intermedio')
  const [types, setTypes] = useState(['quiz', 'flashcard', 'scenario', 'simulator'])
  const [lessons, setLessons] = useState([])      // [{id,type,level,map_id,chapter,title,content,status}]
  const [editingId, setEditingId] = useState(null)
  const [classes, setClasses] = useState([])
  const [classId, setClassId] = useState(null)
  const [due, setDue] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const pdfRef = useRef(null)
  const photoRef = useRef(null)

  // ── Polling del job durante estrazione/generazione ──
  useEffect(() => {
    if (step !== 'progress' || !jobId) return
    const t = setInterval(async () => {
      try {
        const j = await bookJob(jobId)
        setJob(j)
        if (j.status === 'ready' && phase === 'extract') {
          setToc((j.toc || []).map((c) => ({ ...c, checked: (j.toc || []).length === 1 })))
          setStep('toc')
        } else if (j.status === 'done' && phase === 'generate') {
          const metas = (j.result && j.result.lessons) || []
          const full = await Promise.all(metas.map(async (m) => {
            try { const l = await getLesson(m.id); return { ...m, title: l.title, content: l.content, status: l.status } }
            catch (_) { return null }
          }))
          setLessons(full.filter(Boolean))
          setStep('review')
        } else if (j.status === 'error') {
          setErr(j.error || s.bkErr)
          setStep(phase === 'extract' ? 'upload' : 'config')
        }
      } catch (e) { /* riprova al giro dopo */ }
    }, 1600)
    return () => clearInterval(t)
  }, [step, jobId, phase])

  useEffect(() => {
    if (step !== 'assign') return
    myClasses().then((d) => {
      const mine = (d.classes || []).filter((c) => c.role === 'teacher')
      setClasses(mine)
      if (mine.length && !classId) setClassId(mine[0].id)
    }).catch((e) => setErr(e.message))
  }, [step])

  // ── Azioni ──
  const onPick = (e) => { setErr(''); setFiles(Array.from(e.target.files || [])) }

  const startUpload = async () => {
    setBusy(true); setErr('')
    try {
      const r = await bookUpload(files)
      setJobId(r.job_id); setPhase('extract'); setJob(null); setStep('progress')
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const startGenerate = async () => {
    const chapters = toc.filter((c) => c.checked).map((c) => c.idx)
    if (!chapters.length || !types.length) return
    setBusy(true); setErr('')
    try {
      const titles = {}
      toc.forEach((c) => { titles[String(c.idx)] = c.title })
      await bookGenerate({ job_id: jobId, chapters, lessons_per_chapter: perCh, difficulty, types, titles })
      setPhase('generate'); setJob(null); setStep('progress')
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const saveEdit = async (l) => {
    setBusy(true); setErr('')
    try {
      await updateLesson(l.id, { type: l.type, title: l.title, content: l.content, status: 'draft', level: l.level })
      setEditingId(null)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const regen = async (l) => {
    const n = window.prompt(s.bkRegenNote, '')
    if (n === null) return
    setBusy(true); setErr('')
    try {
      const r = await bookRegenerate({ lesson_id: l.id, map_id: l.map_id, note: n || '' })
      setLessons((prev) => prev.map((x) => (x.id === l.id ? { ...x, title: r.title, content: r.content } : x)))
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const removeLesson = async (l) => {
    if (!window.confirm(s.confirmDel)) return
    try { await deleteLesson(l.id); setLessons((prev) => prev.filter((x) => x.id !== l.id)) }
    catch (e) { setErr(e.message) }
  }

  const assign = async () => {
    setBusy(true); setErr('')
    try {
      await bookPublish({ lesson_ids: lessons.map((l) => l.id), class_id: classId, due: due || null, note: note || null })
      setStep('done')
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const reset = () => {
    setStep('upload'); setPhase('extract'); setFiles([]); setJobId(null); setJob(null)
    setToc([]); setLessons([]); setEditingId(null); setErr(''); setDue(''); setNote('')
  }

  const nSel = toc.filter((c) => c.checked).length

  // ── UI ──
  return (
    <div style={{ maxWidth: 720 }}>
      <div style={eyebrow}>📖 {s.bkTitle}</div>
      {err && <div style={errBox}>{err}</div>}

      {step === 'upload' && (
        <div>
          <div style={{ color: 'var(--muted)', fontSize: 14, margin: '6px 0 16px' }}>{s.bkIntro}</div>
          <input ref={pdfRef} type="file" accept="application/pdf,.pdf" style={{ display: 'none' }} onChange={onPick} />
          <input ref={photoRef} type="file" accept="image/*" multiple capture="environment" style={{ display: 'none' }} onChange={onPick} />
          <button style={drop} onClick={() => pdfRef.current && pdfRef.current.click()}>
            <div style={{ fontSize: 26 }}>📄</div>
            <b>{s.bkUploadPdf}</b>
            <div style={dropSub}>{s.bkUploadPdfSub}</div>
          </button>
          <button style={{ ...drop, marginTop: 10 }} onClick={() => photoRef.current && photoRef.current.click()}>
            <div style={{ fontSize: 26 }}>📷</div>
            <b>{s.bkUploadPhotos}</b>
            <div style={dropSub}>{s.bkUploadPhotosSub}</div>
          </button>
          {files.length > 0 && (
            <div style={fileSel}>📎 {files.length === 1 ? files[0].name : `${files.length} foto`} <span style={{ color: ACC, marginLeft: 'auto' }}>✓</span></div>
          )}
          <div style={privacy}>{s.bkPrivacy}</div>
          <div style={foot}>
            <button style={ghost} onClick={() => onDone && onDone(null)}>{s.bkCancel}</button>
            <button style={primary} disabled={!files.length || busy} onClick={startUpload}>{s.bkContinue}</button>
          </div>
        </div>
      )}

      {step === 'toc' && (
        <div>
          <h2 style={h2}>{s.bkTocTitle}</h2>
          <div style={{ color: 'var(--muted)', fontSize: 13.5, marginBottom: 12 }}>
            {toc.length} {s.bkChaptersFound} · {s.bkTocSub}
          </div>
          <div style={card}>
            {toc.map((c, i) => (
              <div key={c.idx} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 4px', borderBottom: i < toc.length - 1 ? '1px solid var(--border)' : 'none' }}>
                <input type="checkbox" checked={c.checked} style={{ accentColor: ACC, width: 17, height: 17, cursor: 'pointer' }}
                  onChange={() => setToc((prev) => prev.map((x) => (x.idx === c.idx ? { ...x, checked: !x.checked } : x)))} />
                <input style={{ ...inp, marginBottom: 0 }} value={c.title}
                  onChange={(e) => setToc((prev) => prev.map((x) => (x.idx === c.idx ? { ...x, title: e.target.value } : x)))} />
                <span style={{ color: 'var(--muted)', fontSize: 12, whiteSpace: 'nowrap' }}>{s.bkPages} {c.start}–{c.end}</span>
              </div>
            ))}
          </div>
          <div style={foot}>
            <button style={ghost} onClick={reset}>{s.bkBack}</button>
            <button style={primary} disabled={!nSel} onClick={() => setStep('config')}>{s.bkContinue}</button>
          </div>
        </div>
      )}

      {step === 'config' && (
        <div>
          <h2 style={h2}>{s.bkConfigTitle}</h2>
          <div style={{ ...card, marginTop: 12 }}>
            <div style={row}>
              <div><b style={{ fontSize: 14.5 }}>{s.bkPerChapter}</b></div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <button style={stepBtn} onClick={() => setPerCh((n) => Math.max(1, n - 1))}>−</button>
                <b style={{ fontSize: 17, minWidth: 20, textAlign: 'center' }}>{perCh}</b>
                <button style={stepBtn} onClick={() => setPerCh((n) => Math.min(10, n + 1))}>+</button>
              </div>
            </div>
            <div style={row}>
              <div>
                <b style={{ fontSize: 14.5 }}>{s.bkDifficulty}</b>
                <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 3 }}>{s.bkMixedHint}</div>
              </div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {[['base', s.levelBase], ['intermedio', s.levelInter], ['avanzato', s.levelAdv], ['mista', s.bkMixed]].map(([v, lab]) => (
                  <button key={v} style={difficulty === v ? segOn : seg} onClick={() => setDifficulty(v)}>{lab}</button>
                ))}
              </div>
            </div>
            <div style={{ ...row, borderBottom: 'none' }}>
              <div><b style={{ fontSize: 14.5 }}>{s.bkTypes}</b></div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {TYPES.map((ty) => (
                  <button key={ty.t} style={types.includes(ty.t) ? segOn : seg}
                    onClick={() => setTypes((prev) => prev.includes(ty.t) ? prev.filter((x) => x !== ty.t) : [...prev, ty.t])}>
                    {ty.icon} {pick(ty.label, lang)}
                  </button>
                ))}
              </div>
            </div>
            <div style={{ color: ACC, fontSize: 13.5, fontWeight: 600, marginTop: 12 }}>
              → {nSel * perCh} {s.bkSummary1} · {s.bkSummary2}
            </div>
          </div>
          <div style={foot}>
            <button style={ghost} onClick={() => setStep('toc')}>{s.bkBack}</button>
            <button style={primary} disabled={busy || !types.length} onClick={startGenerate}>{s.bkGenerate}</button>
          </div>
        </div>
      )}

      {step === 'progress' && (
        <div style={{ textAlign: 'center', padding: '46px 10px' }}>
          <div style={{ fontSize: 30 }}>🧠</div>
          <h2 style={{ ...h2, marginTop: 8 }}>{phase === 'extract' ? s.bkWorkingExtract : s.bkWorkingGen}</h2>
          <div style={{ height: 7, background: 'var(--near-black)', border: '1px solid var(--border)', borderRadius: 99, margin: '18px auto 12px', maxWidth: 420, overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${(job && job.progress) || 3}%`, background: ACC, borderRadius: 99, transition: 'width .6s' }} />
          </div>
          <div style={{ fontSize: 14, minHeight: 20 }}>{(job && job.step) || '…'}</div>
          <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 6 }}>{s.bkWait}</div>
        </div>
      )}

      {step === 'review' && (
        <div>
          <h2 style={h2}>{s.bkReviewTitle}</h2>
          <div style={{ color: 'var(--muted)', fontSize: 13.5, marginBottom: 14 }}>{s.bkReviewSub}</div>
          <div style={{ display: 'grid', gap: 12 }}>
            {lessons.map((l) => (
              <div key={l.id} style={card}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
                  <span style={{ fontSize: 19 }}>{typeIcon(l.type)}</span>
                  <div style={{ flex: 1, minWidth: 160 }}>
                    <b style={{ fontSize: 14.5 }}>{pick(l.title, lang) || '—'}</b>
                    <div style={{ fontSize: 11.5, color: 'var(--muted)' }}>{l.chapter} · {l.level}</div>
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button style={linkBtn} onClick={() => setEditingId(editingId === l.id ? null : l.id)}>{s.edit}</button>
                    <button style={linkBtn} disabled={busy} onClick={() => regen(l)}>{s.bkRegen}</button>
                    <button style={linkDanger} onClick={() => removeLesson(l)}>{s.del}</button>
                  </div>
                </div>
                {editingId === l.id ? (
                  <div>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
                      <input style={{ ...inp, flex: '1 1 140px' }} placeholder={s.title + ' (IT)'} value={l.title.it || ''}
                        onChange={(e) => setLessons((prev) => prev.map((x) => x.id === l.id ? { ...x, title: { ...x.title, it: e.target.value } } : x))} />
                      <input style={{ ...inp, flex: '1 1 140px' }} placeholder={s.title + ' (EN)'} value={l.title.en || ''}
                        onChange={(e) => setLessons((prev) => prev.map((x) => x.id === l.id ? { ...x, title: { ...x.title, en: e.target.value } } : x))} />
                    </div>
                    <LessonForm type={l.type} content={l.content} lang={lang} s={s}
                      onContent={(c) => setLessons((prev) => prev.map((x) => (x.id === l.id ? { ...x, content: c } : x)))} />
                    <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                      <button style={primary} disabled={busy} onClick={() => saveEdit(l)}>{s.save}</button>
                      <button style={ghost} onClick={() => setEditingId(null)}>{s.bkCancel}</button>
                    </div>
                  </div>
                ) : (
                  <div style={{ border: '1px dashed var(--border)', borderRadius: 10, padding: 12 }}>
                    <LessonRenderer type={l.type} content={l.content} lang={lang} mode="preview" strings={s} />
                  </div>
                )}
              </div>
            ))}
          </div>
          <div style={foot}>
            <button style={ghost} onClick={() => setStep('config')}>{s.bkBack}</button>
            <button style={primary} disabled={!lessons.length} onClick={() => setStep('assign')}>{s.bkContinue}</button>
          </div>
        </div>
      )}

      {step === 'assign' && (
        <div>
          <h2 style={h2}>{s.bkAssignTitle}</h2>
          <div style={{ color: 'var(--muted)', fontSize: 13.5, marginBottom: 12 }}>{s.bkAssignSub}</div>
          {classes.length ? (
            <div style={{ display: 'grid', gap: 8 }}>
              {classes.map((c) => (
                <button key={c.id} style={{ ...classRow, borderColor: classId === c.id ? ACC : 'var(--border)' }} onClick={() => setClassId(c.id)}>
                  <span>🏫 <b>{c.name}</b></span>
                  <span style={{ color: 'var(--muted)', fontSize: 12 }}>{c.members} {s.membersLabel} · {c.join_code}</span>
                </button>
              ))}
            </div>
          ) : <div style={{ color: 'var(--muted)', fontSize: 13.5 }}>{s.bkNoClasses}</div>}
          <div style={{ ...card, marginTop: 12 }}>
            <input style={inp} placeholder={s.bkDue} value={due} onChange={(e) => setDue(e.target.value)} />
            <input style={{ ...inp, marginBottom: 0 }} placeholder={s.bkNoteOpt} value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
          <div style={foot}>
            <button style={ghost} onClick={() => setStep('review')}>{s.bkBack}</button>
            <div style={{ display: 'flex', gap: 8 }}>
              <button style={ghost} onClick={() => onDone && onDone(null)}>{s.bkSkipAssign}</button>
              <button style={primary} disabled={busy || !classId || !lessons.length} onClick={assign}>{s.bkAssign} ({lessons.length})</button>
            </div>
          </div>
        </div>
      )}

      {step === 'done' && (
        <div style={{ textAlign: 'center', padding: '46px 10px' }}>
          <div style={{ width: 62, height: 62, borderRadius: '50%', background: ACC, color: '#04221a', fontSize: 30, lineHeight: '62px', margin: '0 auto 14px' }}>✓</div>
          <h2 style={h2}>{s.bkDoneTitle}</h2>
          <div style={{ color: 'var(--muted)', fontSize: 14, margin: '6px 0 20px' }}>{lessons.length} {s.bkSummary1} — {s.bkDoneSub}</div>
          <div style={{ display: 'flex', gap: 10, justifyContent: 'center', flexWrap: 'wrap' }}>
            <button style={primary} onClick={() => onDone && onDone(classId)}>{s.bkOpenClass}</button>
            <button style={ghost} onClick={reset}>{s.bkNewRun}</button>
          </div>
        </div>
      )}
    </div>
  )
}

const card = { background: 'var(--near-black)', border: '1px solid var(--border)', borderRadius: 14, padding: 14 }
const h2 = { fontSize: 19, fontWeight: 600, margin: 0 }
const eyebrow = { fontSize: 12.5, letterSpacing: '.1em', textTransform: 'uppercase', color: ACC, fontWeight: 600, marginBottom: 8 }
const drop = { display: 'block', width: '100%', textAlign: 'center', background: 'var(--near-black)', border: '2px dashed var(--border)', borderRadius: 14, padding: '22px 14px', cursor: 'pointer', color: 'var(--white)', fontSize: 14.5 }
const dropSub = { color: 'var(--muted)', fontSize: 12.5, marginTop: 4 }
const fileSel = { display: 'flex', alignItems: 'center', gap: 8, background: 'var(--near-black)', border: '1px solid var(--border)', borderRadius: 10, padding: '10px 13px', fontSize: 13.5, marginTop: 12 }
const privacy = { marginTop: 12, fontSize: 12.5, color: 'var(--muted)', background: 'var(--near-black)', border: '1px solid var(--border)', borderRadius: 10, padding: '10px 12px', lineHeight: 1.5 }
const foot = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, marginTop: 18, flexWrap: 'wrap' }
const primary = { border: 'none', borderRadius: 9, padding: '10px 18px', cursor: 'pointer', fontSize: 13.5, fontWeight: 600, background: ACC, color: '#04221a' }
const ghost = { border: '1px solid var(--border)', borderRadius: 9, padding: '10px 14px', cursor: 'pointer', fontSize: 13, fontWeight: 600, background: 'transparent', color: 'var(--white)' }
const inp = { flex: 1, width: '100%', background: 'var(--black)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--white)', padding: '8px 10px', fontSize: 13, marginBottom: 8 }
const row = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 14, padding: '12px 0', borderBottom: '1px solid var(--border)', flexWrap: 'wrap' }
const stepBtn = { width: 32, height: 32, borderRadius: 8, border: '1px solid var(--border)', background: 'var(--black)', color: 'var(--white)', fontSize: 17, cursor: 'pointer' }
const seg = { border: '1px solid var(--border)', background: 'var(--black)', color: 'var(--muted)', borderRadius: 9, padding: '7px 12px', cursor: 'pointer', fontSize: 12.5, fontWeight: 600 }
const segOn = { ...seg, borderColor: ACC, color: ACC, background: 'rgba(52,211,153,0.10)' }
const classRow = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, background: 'var(--near-black)', border: '1px solid var(--border)', borderRadius: 12, padding: '12px 14px', cursor: 'pointer', color: 'var(--white)', fontSize: 14, textAlign: 'left' }
const linkBtn = { border: 'none', background: 'transparent', color: '#6aa6ff', cursor: 'pointer', fontSize: 12.5 }
const linkDanger = { border: 'none', background: 'transparent', color: '#f2729b', cursor: 'pointer', fontSize: 12.5 }
const errBox = { background: 'rgba(242,114,155,0.12)', border: '1px solid rgba(242,114,155,0.3)', color: '#f2729b', borderRadius: 10, padding: '10px 13px', fontSize: 13, marginBottom: 14 }
