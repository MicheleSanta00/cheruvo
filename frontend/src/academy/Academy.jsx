/**
 * Academy.jsx — sezione educativa, SEPARATA dalla home/dashboard.
 * Area a sé con header proprio. Accesso solo previo login (montata da App dopo l'auth).
 * Viste: hub (percorsi + classifica) · lesson (player) · workspace (admin).
 */
import { useState, useEffect } from 'react'
import { useLang } from '../LangContext.jsx'
import { STRINGS, pick } from './academyStrings.js'
import { getMe, getPaths, getLesson, saveProgress, getLeaderboard, updateMe } from './academyApi.js'
import LessonRenderer from './LessonRenderer.jsx'
import Workspace from './Workspace.jsx'
import Classroom from './Classroom.jsx'
import ClassView from './ClassView.jsx'
import UserSettings from './UserSettings.jsx'
import BookWizard from './BookWizard.jsx'

export default function Academy({ user, onExit }) {
  const { lang, toggleLang } = useLang()
  const s = STRINGS[lang] || STRINGS.it

  const [view, setView] = useState('hub')   // hub | lesson | workspace
  const [me, setMe] = useState(null)
  const [paths, setPaths] = useState([])
  const [board, setBoard] = useState([])
  const [lesson, setLesson] = useState(null)
  const [classId, setClassId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')

  const loadHub = () => {
    setLoading(true)
    Promise.all([getPaths(), getLeaderboard('all')])
      .then(([p, b]) => { setPaths(p.paths); setBoard(b.leaderboard) })
      .catch(e => setErr(e.message))
      .finally(() => setLoading(false))
  }
  useEffect(() => { getMe().then(setMe).catch(() => {}); loadHub() }, [])

  const openLesson = async (id) => {
    setErr('')
    try { const l = await getLesson(id); setLesson(l); setView('lesson') }
    catch (e) { setErr(e.message) }
  }
  const completeLesson = async ({ correct }) => {
    try { await saveProgress({ lesson_id: lesson.id, correct, completed: true }) } catch (_) {}
    setLesson(null); setView('hub'); loadHub()
  }

  const pickRole = (role) => {
    updateMe({ role, display_name: me?.profile?.display_name || null, leaderboard_opt_in: !!me?.profile?.leaderboard_opt_in })
      .then(() => getMe().then(setMe)).catch(() => {})
  }

  return (
    <div style={{ height: '100dvh', overflow: 'auto', background: 'var(--black)', color: 'var(--white)' }}>
      <header style={hdr}>
        <span onClick={() => setView('hub')} style={{ fontSize: 16, fontWeight: 600, cursor: 'pointer' }}>Cheruvo <span style={{ color: ACC }}>{s.brand}</span></span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <button style={view === 'hub' || view === 'lesson' ? chipOn : chip} onClick={() => { setLesson(null); setView('hub') }}>{s.paths}</button>
          <button style={view === 'classes' || view === 'class' ? chipOn : chip} onClick={() => { setClassId(null); setView('classes') }}>{s.classes}</button>
          {(me?.profile?.role === 'teacher' || me?.is_admin) && (
            <button style={view === 'book' ? chipOn : chip} onClick={() => setView('book')}>📖 {s.bookChip}</button>
          )}
          {me?.is_admin && (
            <button style={view === 'workspace' ? chipOn : chip} onClick={() => setView(view === 'workspace' ? 'hub' : 'workspace')}>{s.workspace}</button>
          )}
          <button style={view === 'settings' ? chipOn : chip} onClick={() => setView('settings')} title={s.settings}>⚙</button>
          <button style={chip} onClick={toggleLang}>{lang === 'it' ? '🇮🇹' : '🇬🇧'}</button>
          <button style={chip} onClick={onExit}>{s.backToApp}</button>
        </div>
      </header>

      <div style={{ maxWidth: 900, margin: '0 auto', padding: '22px 18px 60px' }}>
        {me && !me.profile?.role && (
          <div style={{ position: 'fixed', inset: 0, zIndex: 100, background: 'rgba(0,0,0,0.72)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
            <div style={{ ...card, maxWidth: 420, textAlign: 'center' }}>
              <div style={{ fontSize: 30 }}>🎓</div>
              <div style={{ fontSize: 18, fontWeight: 600, margin: '8px 0 4px' }}>{s.chooseRole}</div>
              <div style={{ color: 'var(--muted)', fontSize: 13.5, marginBottom: 16 }}>{s.chooseRoleSub}</div>
              <div style={{ display: 'flex', gap: 10 }}>
                <button style={roleBtn} onClick={() => pickRole('student')}>🧑‍🎓 {s.roleStudent}</button>
                <button style={roleBtn} onClick={() => pickRole('teacher')}>🧑‍🏫 {s.roleTeacher}</button>
              </div>
            </div>
          </div>
        )}
        {err && <div style={errBox}>{err}</div>}

        {view === 'workspace' && me?.is_admin && <Workspace lang={lang} strings={s} user={user} />}

        {view === 'book' && (me?.profile?.role === 'teacher' || me?.is_admin) && (
          <BookWizard lang={lang} s={s} onDone={(cid) => { if (cid) { setClassId(cid); setView('class') } else { setView('hub') } }} />
        )}

        {view === 'classes' && <Classroom s={s} isTeacher={me?.profile?.role === 'teacher'} onOpen={(id) => { setClassId(id); setView('class') }} />}

        {view === 'class' && classId && <ClassView classId={classId} s={s} lang={lang} onBack={() => setView('classes')} onOpenLesson={(id) => openLesson(id)} />}

        {view === 'settings' && <UserSettings s={s} onSaved={() => getMe().then(setMe)} />}

        {view === 'lesson' && lesson && (
          <div>
            <button style={ghost} onClick={() => { setView('hub'); setLesson(null) }}>{s.backToHub}</button>
            <div style={{ ...card, marginTop: 14, maxWidth: 640 }}>
              <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 14 }}>{pick(lesson.title, lang)}</div>
              <LessonRenderer type={lesson.type} content={lesson.content} lang={lang} mode="play" strings={s} onComplete={completeLesson} />
            </div>
          </div>
        )}

        {view === 'hub' && (
          <div>
            <div style={eyebrow}>{s.hubTitle}</div>
            <h1 style={{ fontSize: 24, fontWeight: 600, margin: '6px 0 4px' }}>{s.paths}</h1>
            <div style={{ color: 'var(--muted)', fontSize: 14, marginBottom: 20 }}>{s.hubSub}</div>

            {loading ? <div style={{ color: 'var(--muted)' }}>{s.loading}</div> : (
              <>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(240px,1fr))', gap: 14 }}>
                  {paths.map(p => (
                    <div key={p.id} style={card}>
                      <div style={{ fontSize: 12, color: ACC, fontWeight: 600, textTransform: 'uppercase' }}>{pick(p.title, lang)}</div>
                      <div style={{ color: 'var(--muted)', fontSize: 13, margin: '6px 0 12px' }}>{pick(p.description, lang)}</div>
                      <div style={{ display: 'grid', gap: 6 }}>
                        {p.lessons.map(l => (
                          <button key={l.id} onClick={() => openLesson(l.id)} style={lessonRow}>
                            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <span style={lvlBadge(l.level)}>{l.level === 'avanzato' ? s.levelAdv : l.level === 'intermedio' ? s.levelInter : s.levelBase}</span>
                              {pick(l.title, lang)}
                            </span>
                            <span style={{ color: l.completed ? ACC : 'var(--muted)', fontSize: 12, whiteSpace: 'nowrap' }}>
                              {l.completed ? '✓ ' + s.done : s.start + ' →'}
                            </span>
                          </button>
                        ))}
                        {!p.lessons.length && <span style={{ color: 'var(--muted)', fontSize: 12 }}>—</span>}
                      </div>
                    </div>
                  ))}
                  {!paths.length && <div style={{ color: 'var(--muted)' }}>{s.empty}</div>}
                </div>

                <div style={{ ...eyebrow, marginTop: 28, marginBottom: 12 }}>{s.leaderboard}</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
                  <div style={card}>
                    {board.length ? board.map(e => (
                      <div key={e.rank} style={{ ...lbRow, ...(e.is_you ? { borderColor: ACC } : {}) }}>
                        <span><b style={{ color: e.rank === 1 ? '#f5c451' : 'var(--muted)' }}>{e.rank}</b>&nbsp;&nbsp;{e.name}</span>
                        <span style={{ color: ACC, fontWeight: 600 }}>{e.xp} XP</span>
                      </div>
                    )) : <div style={{ color: 'var(--muted)', fontSize: 13 }}>—</div>}
                  </div>
                  <div style={card}>
                    <div style={{ fontWeight: 600, marginBottom: 8 }}>{s.howXp}</div>
                    <div style={{ color: 'var(--muted)', fontSize: 13, lineHeight: 1.9 }}>
                      <div>{s.xpComplete}</div><div>{s.xpCorrect}</div>
                    </div>
                    <div style={{ color: 'var(--muted)', fontSize: 11.5, marginTop: 10 }}>{s.optIn}</div>
                  </div>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

const ACC = '#34d399'
const hdr = { minHeight: 52, borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, padding: '8px 14px', background: 'var(--near-black)', position: 'sticky', top: 0, zIndex: 10 }
const chip = { fontSize: 12, background: 'transparent', border: '1px solid var(--border)', borderRadius: 8, padding: '5px 10px', cursor: 'pointer', color: 'var(--white)' }
const chipOn = { ...chip, borderColor: ACC, color: ACC }
const ghost = { fontSize: 13, background: 'transparent', border: '1px solid var(--border)', borderRadius: 8, padding: '7px 12px', cursor: 'pointer', color: 'var(--white)' }
const card = { background: 'var(--near-black)', border: '1px solid var(--border)', borderRadius: 14, padding: 16 }
const roleBtn = { flex: 1, border: '1px solid var(--border)', background: 'var(--black)', color: 'var(--white)', borderRadius: 10, padding: '12px', cursor: 'pointer', fontSize: 14, fontWeight: 600 }
const eyebrow = { fontSize: 12.5, letterSpacing: '.1em', textTransform: 'uppercase', color: ACC, fontWeight: 600 }
const lessonRow = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--black)', border: '1px solid var(--border)', borderRadius: 10, padding: '10px 12px', cursor: 'pointer', color: 'var(--white)', fontSize: 13.5, textAlign: 'left' }
const lvlBadge = (lvl) => ({ fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 99, background: lvl === 'avanzato' ? 'rgba(242,114,155,0.16)' : lvl === 'intermedio' ? 'rgba(245,196,81,0.16)' : 'rgba(52,211,153,0.16)', color: lvl === 'avanzato' ? '#ffa6c2' : lvl === 'intermedio' ? '#f5c451' : '#7fe9c6' })
const lbRow = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--black)', border: '1px solid var(--border)', borderRadius: 10, padding: '9px 12px', marginBottom: 7, fontSize: 13.5 }
const errBox = { background: 'rgba(242,114,155,0.12)', border: '1px solid rgba(242,114,155,0.3)', color: '#f2729b', borderRadius: 10, padding: '10px 13px', fontSize: 13, marginBottom: 14 }
