import React, { useCallback, useEffect, useState } from 'react'
import { api, hms, humanBytes, humanDate } from '../api.js'
import { useAuth } from '../auth.jsx'
import { Link } from '../router.jsx'

/** How each account signs in. A glance should tell you Google vs Facebook vs
 *  a password — it's the first thing worth knowing about a stranger who just
 *  uploaded something. */
function ProviderBadge({ provider }) {
  const map = {
    google: { label: 'Google', glyph: 'G', cls: 'google' },
    facebook: { label: 'Facebook', glyph: 'f', cls: 'facebook' },
    password: { label: 'Email', glyph: '@', cls: 'password' }
  }
  const p = map[provider] || map.password
  return (
    <span className={`provider-badge ${p.cls}`} title={`Signs in with ${p.label}`}>
      <span className="pb-glyph">{p.glyph}</span>{p.label}
    </span>
  )
}

function BanDialog({ user, durations, onCancel, onConfirm }) {
  const [duration, setDuration] = useState('3d')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>Suspend {user.name}</h2>
        <p className="muted small">
          {user.email} is signed out of every device immediately and cannot sign
          back in until the suspension ends.
        </p>

        <label>
          How long
          <select value={duration} onChange={(e) => setDuration(e.target.value)}>
            {durations.map((d) => (
              <option key={d.key} value={d.key}>{d.label}</option>
            ))}
          </select>
        </label>

        <label>
          Reason
          <input
            value={reason}
            placeholder="e.g. uploading recordings they had no right to"
            onChange={(e) => setReason(e.target.value)}
          />
        </label>
        <div className="muted small">
          The reason is kept for other admins. It is not shown to the user.
        </div>

        <div className="edit-actions">
          <button
            className="btn ghost danger"
            disabled={busy}
            onClick={async () => { setBusy(true); await onConfirm(duration, reason) }}
          >
            {busy ? 'Suspending…' : `Suspend for ${
              durations.find((d) => d.key === duration)?.label || duration}`}
          </button>
          <button className="btn ghost" onClick={onCancel}>Cancel</button>
        </div>
      </div>
    </div>
  )
}

export default function AdminPage() {
  const { user, isGod } = useAuth()
  const [overview, setOverview] = useState(null)
  const [users, setUsers] = useState([])
  const [durations, setDurations] = useState([])
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState(null)
  const [banning, setBanning] = useState(null)

  const load = useCallback(async () => {
    try {
      const [ov, list] = await Promise.all([api.adminOverview(), api.adminUsers(query)])
      setOverview(ov)
      setUsers(list.items)
      setError('')
    } catch (err) { setError(err.message) }
  }, [query])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    api.banDurations().then((d) => setDurations(d.durations)).catch(() => {})
  }, [])

  const act = async (id, fn) => {
    setBusyId(id)
    try { await fn(); await load(); setError('') }
    catch (err) { setError(err.message) }
    finally { setBusyId(null); setBanning(null) }
  }

  return (
    <div className="admin-page">
      <header className="admin-head">
        <Link to="/" className="link back">&larr; Dashboard</Link>
        <h1>Administration</h1>
        <p className="muted small">
          Signed in as {user.email} &middot;{' '}
          <span className={`role-badge ${user.role.toLowerCase()}`}>{user.role}</span>{' '}
          (tier {user.level})
          {!isGod && ' — only the owner can change roles, delete accounts, or act on another admin.'}
        </p>
      </header>

      {error && <div className="rec-error banner">{error}</div>}

      {overview && (
        <div className="stat-row">
          <div className="stat"><span className="stat-n">{overview.users.total}</span>
            <span className="stat-l">Users</span></div>
          <div className="stat"><span className="stat-n">{overview.users.admins}</span>
            <span className="stat-l">Admins</span></div>
          <div className="stat"><span className="stat-n">{overview.users.banned}</span>
            <span className="stat-l">Suspended</span></div>
          <div className="stat"><span className="stat-n">{overview.recordings.total}</span>
            <span className="stat-l">Recordings</span></div>
          <div className="stat"><span className="stat-n">{hms(overview.recordings.duration_sec)}</span>
            <span className="stat-l">Audio held</span></div>
          <div className="stat"><span className="stat-n">{humanBytes(overview.recordings.bytes)}</span>
            <span className="stat-l">On disk</span></div>
        </div>
      )}

      <div className="admin-toolbar">
        <div className="search">
          <span className="search-icon" />
          <input value={query} placeholder="Search users by name or email…"
                 onChange={(e) => setQuery(e.target.value)} />
        </div>
        <span className="muted small">
          {overview?.signup_open ? 'Signup OPEN' : 'Signup CLOSED'}
          {overview?.quota_minutes ? ` · ${overview.quota_minutes} min/day per user` : ''}
        </span>
      </div>

      <div className="user-table">
        {users.map((u) => {
          const isTargetGod = u.role === 'GOD'
          const isSelf = u.id === user.id
          // An admin may not act on another admin. Only GOD may.
          const locked = isTargetGod || (u.role === 'ADMIN' && !isGod) || isSelf
          return (
            <div className={`user-row ${u.banned ? 'banned' : ''}`} key={u.id}>
              <div className="user-main">
                <div className="user-id">
                  {u.picture
                    ? <img src={u.picture} alt="" className="avatar big"
                           referrerPolicy="no-referrer" />
                    : <span className="avatar placeholder big">
                        {(u.name || u.email)[0].toUpperCase()}
                      </span>}
                  <div className="user-facts">
                    <div className="user-name">
                      {u.name}
                      <span className={`role-badge ${u.role.toLowerCase()}`}>
                        {u.role} &middot; T{u.level}
                      </span>
                      {u.banned && (
                        <span className="badge failed">
                          {u.ban?.permanent
                            ? 'SUSPENDED — PERMANENT'
                            : `SUSPENDED until ${humanDate(u.ban?.until)}`}
                        </span>
                      )}
                      {!u.email_verified && <span className="badge queued">UNVERIFIED</span>}
                    </div>
                    <div className="user-email">{u.email}</div>
                    <div className="provider-row">
                      {(u.providers.length ? u.providers : ['password']).map((p) => (
                        <ProviderBadge key={p} provider={p} />
                      ))}
                    </div>
                    {u.banned && u.ban?.reason && (
                      <div className="ban-note muted small">
                        &ldquo;{u.ban.reason}&rdquo; &mdash; by {u.ban.by}
                      </div>
                    )}
                    <div className="user-meta muted small">
                      <span>{u.usage.recordings} recordings</span>
                      <span>{hms(u.usage.duration_sec)}</span>
                      <span>{humanBytes(u.usage.bytes)}</span>
                      <span>joined {humanDate(u.created_at)}</span>
                      {u.last_login && <span>last seen {humanDate(u.last_login)}</span>}
                    </div>
                  </div>
                </div>
              </div>

              <div className="user-actions">
                {isTargetGod ? (
                  <span className="muted small">Owner account — protected</span>
                ) : isSelf ? (
                  <span className="muted small">This is you</span>
                ) : (
                  <>
                    {isGod && (
                      u.role === 'ADMIN'
                        ? <button className="btn ghost" disabled={busyId === u.id}
                                  onClick={() => act(u.id, () => api.adminSetRole(u.id, 'USER'))}>
                            Demote to user
                          </button>
                        : <button className="btn ghost" disabled={busyId === u.id}
                                  onClick={() => act(u.id, () => api.adminSetRole(u.id, 'ADMIN'))}>
                            Make admin
                          </button>
                    )}
                    {u.banned ? (
                      <button className="btn ghost" disabled={busyId === u.id || locked}
                              onClick={() => act(u.id, () => api.adminUnban(u.id))}>
                        Lift suspension
                      </button>
                    ) : (
                      <button className="btn ghost danger" disabled={busyId === u.id || locked}
                              onClick={() => setBanning(u)}>
                        Suspend&hellip;
                      </button>
                    )}
                    {isGod && (
                      <button className="btn ghost danger" disabled={busyId === u.id}
                              onClick={() => {
                                if (window.confirm(
                                  `Delete ${u.email} and every recording they uploaded? ` +
                                  `This cannot be undone.`)) {
                                  act(u.id, () => api.adminDeleteUser(u.id))
                                }
                              }}>Delete</button>
                    )}
                  </>
                )}
              </div>
            </div>
          )
        })}
        {!users.length && (
          <div className="empty"><p className="muted">No users match that search.</p></div>
        )}
      </div>

      {banning && (
        <BanDialog
          user={banning}
          durations={durations}
          onCancel={() => setBanning(null)}
          onConfirm={(duration, reason) =>
            act(banning.id, () => api.adminBan(banning.id, duration, reason))}
        />
      )}
    </div>
  )
}
