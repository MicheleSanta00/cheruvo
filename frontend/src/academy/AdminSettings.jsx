/**
 * AdminSettings.jsx — pannello "Impostazioni" del Workspace.
 * Sezione 1: profilo dell'utente (nickname + opt-in classifica).
 * Sezione 2: gestione amministratori (promuovi/rimuovi per email) — niente più SQL.
 */
import { useState, useEffect } from 'react'
import { getMe, updateMe, listAdmins, addAdmin, removeAdmin } from './academyApi.js'

export default function AdminSettings({ lang, strings, user }) {
  const s = strings
  const [profile, setProfile] = useState({ display_name: '', leaderboard_opt_in: false })
  const [admins, setAdmins] = useState([])
  const [email, setEmail] = useState('')
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const loadAdmins = () => listAdmins().then(d => setAdmins(d.admins)).catch(e => setErr(e.message))
  useEffect(() => {
    getMe().then(d => setProfile({
      display_name: d.profile.display_name || '',
      leaderboard_opt_in: !!d.profile.leaderboard_opt_in,
    })).catch(() => {})
    loadAdmins()
  }, [])

  const saveProfile = async () => {
    setBusy(true); setErr(''); setMsg('')
    try { await updateMe(profile); setMsg(s.saved) } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const promote = async () => {
    if (!email) return
    setBusy(true); setErr(''); setMsg('')
    try { const r = await addAdmin(email); setEmail(''); setMsg('✓ ' + r.email); loadAdmins() }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const demote = async (uid) => {
    setErr(''); setMsg('')
    try { await removeAdmin(uid); loadAdmins() } catch (e) { setErr(e.message) }
  }

  return (
    <div style={{ display: 'grid', gap: 16, maxWidth: 560 }}>
      <div style={card}>
        <div style={h}>{s.yourProfile}</div>
        <label style={lbl}>{s.nickname}</label>
        <input style={inp} value={profile.display_name}
          onChange={e => setProfile(p => ({ ...p, display_name: e.target.value }))} />
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10, fontSize: 13.5, cursor: 'pointer' }}>
          <input type="checkbox" checked={profile.leaderboard_opt_in}
            onChange={e => setProfile(p => ({ ...p, leaderboard_opt_in: e.target.checked }))} />
          {s.joinLeaderboard}
        </label>
        <button style={primary} disabled={busy} onClick={saveProfile}>{s.save}</button>
      </div>

      <div style={card}>
        <div style={h}>{s.adminsTitle}</div>
        <div style={{ color: 'var(--muted)', fontSize: 12.5, marginBottom: 12 }}>{s.adminsHelp}</div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <input style={{ ...inp, flex: '1 1 180px', width: 'auto' }} type="email" placeholder={s.addByEmail} value={email}
            onChange={e => setEmail(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') promote() }} />
          <button style={primary} disabled={busy} onClick={promote}>{s.makeAdmin}</button>
        </div>
        {msg && <div style={okBox}>{msg}</div>}
        {err && <div style={errBox}>{err}</div>}
        <div style={{ display: 'grid', gap: 7, marginTop: 12 }}>
          {admins.map(a => (
            <div key={a.user_id} style={rowItem}>
              <span style={{ fontSize: 13.5 }}>{a.email}{a.user_id === user?.id ? ' ' + s.you : ''}</span>
              {a.user_id !== user?.id && <button style={linkDanger} onClick={() => demote(a.user_id)}>{s.remove}</button>}
            </div>
          ))}
          {!admins.length && <span style={{ color: 'var(--muted)', fontSize: 13 }}>—</span>}
        </div>
      </div>
    </div>
  )
}

const card = { background: 'var(--near-black)', border: '1px solid var(--border)', borderRadius: 14, padding: 16 }
const h = { fontSize: 15, fontWeight: 600, marginBottom: 12 }
const lbl = { display: 'block', fontSize: 12.5, color: 'var(--muted)', marginBottom: 6 }
const inp = { flex: 1, width: '100%', background: 'var(--black)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--white)', padding: '9px 11px', fontSize: 13.5 }
const primary = { border: 'none', borderRadius: 9, padding: '9px 16px', cursor: 'pointer', fontSize: 13, fontWeight: 600, background: '#34d399', color: '#04221a', whiteSpace: 'nowrap', marginTop: 0 }
const rowItem = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'var(--black)', border: '1px solid var(--border)', borderRadius: 10, padding: '9px 12px' }
const linkDanger = { border: 'none', background: 'transparent', color: '#f2729b', cursor: 'pointer', fontSize: 12.5 }
const okBox = { background: 'rgba(52,211,153,0.12)', border: '1px solid rgba(52,211,153,0.3)', color: '#34d399', borderRadius: 9, padding: '9px 12px', fontSize: 13, marginTop: 10 }
const errBox = { background: 'rgba(242,114,155,0.12)', border: '1px solid rgba(242,114,155,0.3)', color: '#f2729b', borderRadius: 9, padding: '9px 12px', fontSize: 13, marginTop: 10 }
