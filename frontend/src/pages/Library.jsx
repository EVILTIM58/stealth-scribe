import React, { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { useAuth } from '../auth.jsx'
import { Link } from '../router.jsx'
import Sidebar from '../components/Sidebar.jsx'
import UploadZone from '../components/UploadZone.jsx'
import RecordingList from '../components/RecordingList.jsx'
import RecordingDetail from '../components/RecordingDetail.jsx'
import SettingsModal from '../components/SettingsModal.jsx'
import LiveRecorder from '../components/LiveRecorder.jsx'

function UserMenu() {
  const { user, isAdmin, logout } = useAuth()
  const [open, setOpen] = useState(false)
  return (
    <div className="user-menu">
      <button className="user-chip" onClick={() => setOpen((v) => !v)}>
        {user.picture
          ? <img src={user.picture} alt="" className="avatar" />
          : <span className="avatar placeholder">{(user.name || user.email)[0].toUpperCase()}</span>}
        <span className="user-chip-name">{user.name}</span>
      </button>
      {open && (
        <>
          <div className="menu-scrim" onClick={() => setOpen(false)} />
          <div className="menu">
            <div className="menu-head">
              <div>{user.name}</div>
              <div className="muted small">{user.email}</div>
              <div className={`role-badge ${user.role.toLowerCase()}`}>{user.role}</div>
            </div>
            <Link to="/people" onClick={() => setOpen(false)}>Voices Stealth-Scribe knows</Link>
            <Link to="/account" onClick={() => setOpen(false)}>Your account</Link>
            {isAdmin && <Link to="/admin" onClick={() => setOpen(false)}>Administration</Link>}
            <Link to="/about" onClick={() => setOpen(false)}>About Stealth-Scribe</Link>
            <button onClick={logout}>Sign out</button>
          </div>
        </>
      )}
    </div>
  )
}

export default function Library() {
  const { user, isAdmin } = useAuth()
  const [filters, setFilters] = useState({ status: '', tag: '', skip: 0 })
  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [stats, setStats] = useState(null)
  const [folders, setFolders] = useState([])
  const [tags, setTags] = useState([])
  const [openId, setOpenId] = useState(null)
  const [seekTo, setSeekTo] = useState(null)
  const [showSettings, setShowSettings] = useState(false)
  const [error, setError] = useState('')
  const [showUpload, setShowUpload] = useState(true)
  const [recording, setRecording] = useState(false)
  const timer = useRef(null)

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query), 300)
    return () => clearTimeout(t)
  }, [query])

  const refresh = useCallback(async () => {
    try {
      const [list, st, fld] = await Promise.all([
        api.list({
          q: debounced,
          status: filters.status || undefined,
          folder: filters.folder,
          tag: filters.tag || undefined,
          skip: filters.skip || 0
        }),
        api.stats(),
        api.folders()
      ])
      setItems(list.items)
      setTotal(list.total)
      setStats(st)
      setFolders(fld.folders)
      setTags(fld.tags)
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [debounced, filters])

  useEffect(() => { setLoading(true); refresh() }, [refresh])

  // Poll while anything is in flight so progress updates itself.
  useEffect(() => {
    const active = items.some((i) => i.status === 'queued' || i.status === 'processing')
    clearInterval(timer.current)
    timer.current = setInterval(refresh, active ? 3000 : 15000)
    return () => clearInterval(timer.current)
  }, [items, refresh])

  const openAt = (id, seconds) => { setSeekTo(seconds); setOpenId(id) }

  return (
    <div className="app">
      <Sidebar
        stats={stats}
        folders={folders}
        tags={tags}
        filters={filters}
        setFilters={setFilters}
        onOpenSettings={() => setShowSettings(true)}
      />

      <main className="main">
        <header className="topbar">
          <div className="search">
            <span className="search-icon" />
            <input
              value={query}
              placeholder="Search everything that was said..."
              onChange={(e) => setQuery(e.target.value)}
            />
            {query && <button className="clear" onClick={() => setQuery('')}>&times;</button>}
          </div>
          <div className="topbar-right">
            {/* Admin is a first-class destination for tier 2 and 3, not a
                menu item they have to go hunting for. */}
            {isAdmin && (
              <Link to="/admin" className="btn admin-btn" title="Administration">
                <span className="btn-dot" /> Admin
              </Link>
            )}
            {!openId && (
              <>
                <button
                  className={`btn ${recording ? 'ghost' : 'record'}`}
                  onClick={() => setRecording((v) => !v)}
                >
                  <span className="btn-dot" /> {recording ? 'Close recorder' : 'Record'}
                </button>
                <button className="btn ghost" onClick={() => setShowUpload((v) => !v)}>
                  {showUpload ? 'Hide upload' : 'Upload'}
                </button>
              </>
            )}
            <UserMenu />
          </div>
        </header>

        {error && <div className="rec-error banner">{error}</div>}

        {stats?.quota?.limited && stats.quota.remaining_minutes <= 15 && (
          <div className="notice">
            You&rsquo;ve used {stats.quota.used_minutes} of your {stats.quota.limit_minutes}{' '}
            daily minutes. The limit resets on a rolling 24-hour basis.
          </div>
        )}

        {openId ? (
          <RecordingDetail
            id={openId}
            seekTo={seekTo}
            onClose={() => { setOpenId(null); setSeekTo(null); refresh() }}
            onChanged={refresh}
          />
        ) : (
          <>
            {recording && (
              <LiveRecorder
                folders={folders}
                onUploaded={refresh}
                onClose={() => setRecording(false)}
              />
            )}
            {showUpload && !recording && <UploadZone folders={folders} onUploaded={refresh} />}
            <div className="list-head">
              <span className="muted small">
                {debounced
                  ? `${total} recording${total === 1 ? '' : 's'} mention "${debounced}"`
                  : `${total} recording${total === 1 ? '' : 's'}`}
              </span>
            </div>
            <RecordingList
              items={items}
              loading={loading}
              query={debounced}
              onOpen={(id) => openAt(id, null)}
              onSeekTo={openAt}
            />
          </>
        )}
      </main>

      {showSettings && <SettingsModal onClose={() => setShowSettings(false)} />}
    </div>
  )
}
