/**
 * classroomApi.js — client per gli endpoint /classroom + upload file su Supabase Storage.
 */
import apiFetch from '../apiFetch.js'
import { supabase } from '../supabase.js'

export const myClasses   = ()          => apiFetch('/classroom/classes')
export const createClass = (name)      => apiFetch('/classroom/classes', { method: 'POST', body: JSON.stringify({ name }) })
export const joinClass   = (code)      => apiFetch('/classroom/join', { method: 'POST', body: JSON.stringify({ code }) })
export const getClass    = (id)        => apiFetch(`/classroom/classes/${id}`)
export const createPost  = (id, post)  => apiFetch(`/classroom/classes/${id}/posts`, { method: 'POST', body: JSON.stringify(post) })
export const deletePost  = (pid)       => apiFetch(`/classroom/posts/${pid}`, { method: 'DELETE' })
export const getMessages = (id)        => apiFetch(`/classroom/classes/${id}/messages`)
export const sendMessage = (id, body)  => apiFetch(`/classroom/classes/${id}/messages`, { method: 'POST', body: JSON.stringify({ body }) })
export const leaveClass  = (id)        => apiFetch(`/classroom/classes/${id}/leave`, { method: 'POST' })

// Upload diretto su Supabase Storage (bucket pubblico "class-files")
export async function uploadClassFile(classId, file) {
  const safe = file.name.replace(/[^a-zA-Z0-9._-]/g, '_')
  const path = `${classId}/${Date.now()}_${safe}`
  const { error } = await supabase.storage.from('class-files').upload(path, file)
  if (error) throw new Error(error.message)
  const { data } = supabase.storage.from('class-files').getPublicUrl(path)
  return { url: data.publicUrl, name: file.name }
}
