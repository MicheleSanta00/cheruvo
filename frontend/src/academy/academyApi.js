/**
 * academyApi.js — client per gli endpoint /academy (riusa apiFetch: base /api + JWT).
 */
import apiFetch from '../apiFetch.js'

export const getMe        = ()        => apiFetch('/academy/me')
export const updateMe     = (body)    => apiFetch('/academy/me', { method: 'PUT', body: JSON.stringify(body) })
export const getPaths     = ()        => apiFetch('/academy/paths')
export const getLesson    = (id)      => apiFetch(`/academy/lessons/${id}`)
export const saveProgress = (body)    => apiFetch('/academy/progress', { method: 'POST', body: JSON.stringify(body) })
export const getLeaderboard = (range = 'all') => apiFetch(`/academy/leaderboard?range=${range}`)

// Admin / workspace
export const adminLessons = ()        => apiFetch('/academy/admin/lessons')
export const createLesson = (body)    => apiFetch('/academy/lessons', { method: 'POST', body: JSON.stringify(body) })
export const updateLesson = (id, body) => apiFetch(`/academy/lessons/${id}`, { method: 'PUT', body: JSON.stringify(body) })
export const deleteLesson = (id)      => apiFetch(`/academy/lessons/${id}`, { method: 'DELETE' })
export const aiDraft      = (topic, type = 'quiz', n = 5) => apiFetch('/academy/ai/draft', { method: 'POST', body: JSON.stringify({ topic, type, n }) })

// Gestione amministratori
export const listAdmins   = ()       => apiFetch('/academy/admin/admins')
export const addAdmin     = (email)  => apiFetch('/academy/admin/admins', { method: 'POST', body: JSON.stringify({ email }) })
export const removeAdmin  = (uid)    => apiFetch(`/academy/admin/admins/${uid}`, { method: 'DELETE' })

// Docente: le proprie lezioni (create dal wizard "Lezioni dal libro")
export const myLessons    = ()       => apiFetch('/academy/my/lessons')

// Lezioni dal Libro (wizard docente)
export const bookUpload = (files) => {
  const fd = new FormData()
  files.forEach((f) => fd.append('files', f))
  return apiFetch('/academy/book/upload', { method: 'POST', body: fd })
}
export const bookJob        = (id)   => apiFetch(`/academy/book/jobs/${id}`)
export const bookGenerate   = (body) => apiFetch('/academy/book/generate', { method: 'POST', body: JSON.stringify(body) })
export const bookRegenerate = (body) => apiFetch('/academy/book/regenerate', { method: 'POST', body: JSON.stringify(body) })
export const bookPublish    = (body) => apiFetch('/academy/book/publish', { method: 'POST', body: JSON.stringify(body) })
