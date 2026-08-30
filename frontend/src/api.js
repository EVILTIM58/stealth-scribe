const BASE = ''

async function req(path, options = {}) {
  const res = await fetch(BASE + path, {
    // Session lives in an httpOnly cookie, so every call must send credentials.
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options
  })
  if (res.status === 204) return null
  const body = await res.text()
  let data = null
  try { data = body ? JSON.parse(body) : null } catch { data = body }
  if (!res.ok) {
    const message = (data && data.detail) || res.statusText || 'Request failed'
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message))
  }
  return data
}

const post = (path, body) => req(path, { method: 'POST', body: JSON.stringify(body || {}) })

export const api = {
  // ---------------------------------------------------------------- auth
  me: () => req('/api/auth/me'),
  authConfig: () => req('/api/auth/config'),
  signup: (body) => post('/api/auth/signup', body),
  login: (body) => post('/api/auth/login', body),
  logout: () => post('/api/auth/logout'),
  logoutEverywhere: () => post('/api/auth/logout-everywhere'),
  verify: (token) => post('/api/auth/verify', { token }),
  resendVerification: (email) => post('/api/auth/resend-verification', { email }),
  forgot: (email) => post('/api/auth/forgot', { email }),
  resetPassword: (token, password) => post('/api/auth/reset', { token, password }),
  updateProfile: (body) => req('/api/auth/profile', { method: 'PATCH', body: JSON.stringify(body) }),
  oauthUrl: (provider) => `${BASE}/api/auth/${provider}/start`,

  // --------------------------------------------------------------- admin
  adminUsers: (q = '') => req(`/api/admin/users${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  adminOverview: () => req('/api/admin/overview'),
  adminSetRole: (id, role) =>
    req(`/api/admin/users/${id}/role`, { method: 'PATCH', body: JSON.stringify({ role }) }),
  banDurations: () => req('/api/admin/ban-durations'),
  adminBan: (id, duration, reason) => post(`/api/admin/users/${id}/ban`, { duration, reason }),
  adminUnban: (id) => post(`/api/admin/users/${id}/unban`),
  adminUpdateUser: (id, body) =>
    req(`/api/admin/users/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  adminDeleteUser: (id) => req(`/api/admin/users/${id}`, { method: 'DELETE' }),

  // ---------------------------------------------------------------- site
  nuke: (opts) => post('/api/account/nuke', {
    confirm: 'NUKE',
    forget_voices: opts.forgetVoices,
    delete_account: opts.deleteAccount
  }),

  siteMeta: () => req('/api/site/meta'),
  contact: (body) => post('/api/contact', body),

  version: () => req('/api/system/version'),
  stats: () => req('/api/stats'),
  settings: () => req('/api/settings'),
  saveSettings: (patch) => req('/api/settings', { method: 'PATCH', body: JSON.stringify(patch) }),
  folders: () => req('/api/folders'),

  list: (params = {}) => {
    const qs = new URLSearchParams()
    // Empty string is meaningful for `folder` (= unfiled), so only skip nullish.
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) qs.set(k, v)
    })
    const s = qs.toString()
    return req('/api/recordings' + (s ? `?${s}` : ''))
  },
  get: (id) => req(`/api/recordings/${id}`),
  patch: (id, patch) => req(`/api/recordings/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  renameSpeakers: (id, labels) =>
    req(`/api/recordings/${id}/speakers`, { method: 'POST', body: JSON.stringify({ labels }) }),
  confirmSpeaker: (id, speaker, accept) =>
    post(`/api/recordings/${id}/speakers/confirm`, { speaker, accept }),
  reassign: (id, body) => post(`/api/recordings/${id}/reassign`, body),

  // ------------------------------------------------------- voice library
  people: () => req('/api/people'),
  updatePerson: (id, body) =>
    req(`/api/people/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deletePerson: (id) => req(`/api/people/${id}`, { method: 'DELETE' }),
  mergePeople: (keepId, dropId) => post(`/api/people/${keepId}/merge/${dropId}`),
  personRecordings: (id) => req(`/api/people/${id}/recordings`),
  requeue: (id, options = {}) =>
    req(`/api/recordings/${id}/requeue`, { method: 'POST', body: JSON.stringify(options) }),
  remove: (id) => req(`/api/recordings/${id}`, { method: 'DELETE' }),

  audioUrl: (id) => `${BASE}/api/recordings/${id}/audio`,
  files: (id) => req(`/api/recordings/${id}/files`),
  downloadUrl: (id, what) => `${BASE}/api/recordings/${id}/download/${what}`,
  transcriptUrl: (id) => `${BASE}/api/recordings/${id}/transcript.txt`,
  // Same endpoint serves audio and video, with byte-range support for seeking.
  mediaUrl: (id) => `${BASE}/api/recordings/${id}/audio`
}

// 5 MB: small enough that Cloudflare never kills a request (100 MB cap) and
// that a dropped home-uplink packet only costs one part, large enough that a
// 2 GB video isn't 2000 round trips.
const CHUNK = 5 * 1024 * 1024
const MAX_RETRIES = 4

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function putChunkWithRetry(uploadId, index, blob, totalChunks) {
  let attempt = 0
  for (;;) {
    try {
      const res = await fetch(`${BASE}/api/uploads/${uploadId}/chunk?index=${index}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/octet-stream' },
        body: blob
      })
      // 4xx means the request itself is wrong - retrying will never fix it.
      if (res.status >= 400 && res.status < 500) {
        const detail = await res.text().catch(() => '')
        throw Object.assign(new Error(detail || res.statusText), { fatal: true })
      }
      if (!res.ok) throw new Error(res.statusText || `HTTP ${res.status}`)
      return
    } catch (err) {
      attempt++
      if (err.fatal || attempt >= MAX_RETRIES) {
        throw new Error(
          `Upload failed on part ${index + 1} of ${totalChunks}: ${err.message}`
        )
      }
      // Exponential backoff: 0.8s, 1.6s, 3.2s - rides out a flaky uplink.
      await sleep(800 * 2 ** (attempt - 1))
    }
  }
}

export async function uploadFile(file, meta = {}, onProgress = () => {}) {
  const totalChunks = Math.max(1, Math.ceil(file.size / CHUNK))
  const init = await req('/api/uploads/init', {
    method: 'POST',
    body: JSON.stringify({
      filename: file.name,
      size: file.size,
      total_chunks: totalChunks,
      // Live recordings are audio in a .webm container, which by extension alone
      // looks like video. The declared mime settles it.
      mime: meta.mime || file.type || ''
    })
  })

  for (let i = 0; i < totalChunks; i++) {
    const slice = file.slice(i * CHUNK, Math.min(file.size, (i + 1) * CHUNK))
    await putChunkWithRetry(init.upload_id, i, slice, totalChunks)
    onProgress((i + 1) / totalChunks)
  }

  return req(`/api/uploads/${init.upload_id}/complete`, {
    method: 'POST',
    body: JSON.stringify({
      folder: meta.folder || '',
      tags: meta.tags || [],
      title: meta.title || '',
      notes: meta.notes || '',
      recorded_at: meta.recordedAt || null
    })
  })
}

// ---------------------------------------------------------------- formatting
export function hms(seconds) {
  const s = Math.max(0, Math.round(seconds || 0))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  const pad = (n) => String(n).padStart(2, '0')
  return h ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`
}

export function humanDate(value) {
  if (!value) return ''
  const d = new Date(value)
  if (isNaN(d)) return ''
  return d.toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit'
  })
}

export function humanBytes(n) {
  if (!n) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  let v = n
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`
}
