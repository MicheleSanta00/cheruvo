/**
 * UserSettings.jsx — impostazioni di QUALSIASI utente Academy: ruolo (studente/docente),
 * nickname e partecipazione alla classifica.
 */
import { useState, useEffect } from 'react'
import { getMe, updateMe } from './academyApi.js'
import Icon from '../components/Icon.jsx'

export default function UserSettings({ s, onSaved }) {
  const [p, setP] = useState({ display_name: '', leaderboard_opt_in: false, role: 'student' })
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getMe().then((d) => setP({
      display_name: d.profile.display_name || '',
      leaderboard_opt_in: !!d.profile.leaderboard_opt_in,
      role: d.profile.role || 'student',
    })).catch(() => {})
  }, [])

  const save = async () => {
    setBusy(true); setMsg('')
    try { await updateMe(p); setMsg(s.saved); onSaved && onSaved(p) }
    catch (e) { setMsg(e.message) } finally { setBusy(false) }
  }

  return (
    <div style={{ maxWidth: 520 }}>
      <div style={card}>
        <div style={h}>{s.yourProfile}</div>

        <label style={lbl}>{s.roleLabel}</label>
        <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
          <button style={{ ...(p.role === 'student' ? roleOn : roleOff), display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 7 }} onClick={() => setP((x) => ({ ...x, role: 'student' }))}><Icon name="student" size={16} /> {s.roleStudent}</button>
          <button style={{ ...(p.role === 'teacher' ? roleOn : roleOff), display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 7 }} onClick={() => setP((x) => ({ ...x, role: 'teacher' }))}><Icon name="teacher" size={16} /> {s.roleTeacher}</button>
        </div>

        <label style={lbl}>{s.nickname}</label>
        <input style={inp} value={p.display_name} onChange={(e) => setP((x) => ({ ...x, display_name: e.target.value }))} />

        <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 12, fontSize: 13.5, cursor: 'pointer' }}>
          <input type="checkbox" checked={p.leaderboard_opt_in} onChange={(e) => setP((x) => ({ ...x, leaderboard_opt_in: e.target.checked }))} />
          {s.joinLeaderboard}
        </label>

        <div style={{ marginTop: 16, display: 'flex', alignItems: 'center', gap: 12 }}>
          <button style={primary} disabled={busy} onClick={save}>{s.save}</button>
          {msg && <span style={{ fontSize: 13, color: '#34d399' }}>{msg}</span>}
        </div>
      </div>
    </div>
  )
}

const card = { background: 'var(--near-black)', border: '1px solid var(--border)', borderRadius: 14, padding: 16 }
const h = { fontSize: 15, fontWeight: 600, marginBottom: 12 }
const lbl = { display: 'block', fontSize: 12.5, color: 'var(--muted)', marginBottom: 6 }
const inp = { width: '100%', background: 'var(--black)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--white)', padding: '9px 11px', fontSize: 13.5 }
const primary = { border: 'none', borderRadius: 9, padding: '9px 16px', cursor: 'pointer', fontSize: 13, fontWeight: 600, background: '#34d399', color: '#04221a' }
const roleOff = { flex: 1, border: '1px solid var(--border)', background: 'var(--black)', color: 'var(--white)', borderRadius: 10, padding: '12px', cursor: 'pointer', fontSize: 14, fontWeight: 600 }
const roleOn = { ...roleOff, borderColor: '#34d399', color: '#34d399', background: 'rgba(52,211,153,0.10)' }
