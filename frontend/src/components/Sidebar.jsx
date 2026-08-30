import React from 'react'
import { hms, humanBytes } from '../api.js'
import { APP_VERSION } from '../config/version.js'

const STATUS_LABEL = {
  queued: 'Queued',
  processing: 'Transcribing',
  done: 'Done',
  failed: 'Failed'
}

export default function Sidebar({ stats, folders, tags, filters, setFilters, onOpenSettings }) {
  const workers = stats?.workers || []
  const byStatus = stats?.by_status || {}

  const setFilter = (patch) => setFilters({ ...filters, ...patch, skip: 0 })

  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark" style={{ backgroundImage: 'url(/ss-mark.webp)' }} />
        <div>
          <div className="brand-name">Stealth-Scribe</div>
          <div className="muted small">Clear. Accurate. Secure.</div>
        </div>
      </div>

      <div className="worker-status">
        <div className="section-title">Transcription worker</div>
        {workers.length === 0 ? (
          <div className="worker offline">
            <span className="dot" />
            <div>
              <div>No worker connected</div>
              <div className="muted small">Uploads will queue until your PC is running the worker.</div>
            </div>
          </div>
        ) : (
          workers.map((w) => (
            <div className="worker online" key={w.name}>
              <span className="dot" />
              <div>
                <div>{w.name} <span className="muted small">{w.device}</span></div>
                <div className="muted small">
                  {w.current ? `working on ${w.current.title}` : 'idle, waiting for jobs'}
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      <nav className="filters">
        <div className="section-title">Status</div>
        <button
          className={!filters.status ? 'active' : ''}
          onClick={() => setFilter({ status: '' })}
        >
          All recordings <span className="count">{stats?.total || 0}</span>
        </button>
        {['queued', 'processing', 'done', 'failed'].map((s) =>
          byStatus[s] ? (
            <button
              key={s}
              className={filters.status === s ? 'active' : ''}
              onClick={() => setFilter({ status: s })}
            >
              {STATUS_LABEL[s]} <span className="count">{byStatus[s]}</span>
            </button>
          ) : null
        )}
      </nav>

      {folders.length > 0 && (
        <nav className="filters">
          <div className="section-title">Folders</div>
          {folders.map((f) => (
            <button
              key={f.name || '__root'}
              className={filters.folder === f.name ? 'active' : ''}
              onClick={() =>
                setFilter({ folder: filters.folder === f.name ? undefined : f.name })
              }
            >
              {f.name || 'Unfiled'} <span className="count">{f.count}</span>
            </button>
          ))}
        </nav>
      )}

      {tags.length > 0 && (
        <div className="filters">
          <div className="section-title">Tags</div>
          <div className="tag-cloud">
            {tags.slice(0, 24).map((t) => (
              <button
                key={t.name}
                className={`tag ${filters.tag === t.name ? 'active' : ''}`}
                onClick={() => setFilter({ tag: filters.tag === t.name ? '' : t.name })}
              >
                {t.name} <span className="count">{t.count}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="sidebar-footer">
        <button className="link" onClick={onOpenSettings}>Transcription settings</button>
        <div className="muted small">
          {stats ? (
            <>
              {hms(stats.duration_sec)} of audio &middot; {humanBytes(stats.bytes)}
              {stats.disk?.free ? <> &middot; {humanBytes(stats.disk.free)} free</> : null}
            </>
          ) : 'loading...'}
        </div>
        <div className="muted small">Stealth-Scribe v{APP_VERSION}</div>
      </div>
    </aside>
  )
}
