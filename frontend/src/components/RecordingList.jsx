import React from 'react'
import { hms, humanDate, humanBytes } from '../api.js'

function StatusBadge({ item }) {
  const { status, progress, stage } = item
  if (status === 'processing') {
    return (
      <span className="badge processing" title={stage}>
        <i className="spinner" /> {Math.round((progress || 0) * 100)}%
      </span>
    )
  }
  if (status === 'queued') return <span className="badge queued">Queued</span>
  if (status === 'failed') return <span className="badge failed" title={item.error}>Failed</span>
  return <span className="badge done">Ready</span>
}

export default function RecordingList({ items, loading, query, onOpen, onSeekTo }) {
  if (loading && !items.length) {
    return <div className="empty"><div className="pulse-eye" /><p>Loading library...</p></div>
  }
  if (!items.length) {
    return (
      <div className="empty">
        <img src="/ss-mark.webp" alt="" className="empty-mark" />
        <h3>{query ? 'Nothing matched that search' : 'No recordings yet'}</h3>
        <p className="muted">
          {query
            ? 'Try a different word or phrase.'
            : 'Drop a voice recorder file above and Stealth-Scribe will take it from there.'}
        </p>
      </div>
    )
  }

  return (
    <ul className="rec-list">
      {items.map((item) => (
        <li key={item.id} className={`rec-card ${item.status}`} onClick={() => onOpen(item.id)}>
          <div className="rec-main">
            <div className="rec-head">
              <h3>{item.title || item.original_name}</h3>
              <StatusBadge item={item} />
            </div>
            <div className="rec-meta">
              {item.kind === 'video' && <span className="kind-video">VIDEO</span>}
              {item.language && item.language !== 'en' && (
                <span className="kind-lang">
                  {item.language_name || item.language}
                  {item.translated_from ? ' → EN' : ''}
                </span>
              )}
              <span>{humanDate(item.recorded_at)}</span>
              {item.duration_sec > 0 && <span>{hms(item.duration_sec)}</span>}
              {item.word_count > 0 && <span>{item.word_count.toLocaleString()} words</span>}
              {Object.keys(item.speaker_labels || {}).length > 1 && (
                <span>{Object.keys(item.speaker_labels).length} speakers</span>
              )}
              <span className="muted">{humanBytes(item.size_bytes)}</span>
            </div>
            {item.status === 'processing' && (
              <div className="rec-progress">
                <span className="track">
                  <i style={{ width: `${Math.round((item.progress || 0) * 100)}%` }} />
                </span>
                <span className="muted small">{item.stage}</span>
              </div>
            )}
            {item.status === 'failed' && item.error && (
              <div className="rec-error small">{item.error}</div>
            )}
            {(item.folder || (item.tags || []).length > 0) && (
              <div className="rec-tags">
                {item.folder && <span className="chip folder">{item.folder}</span>}
                {(item.tags || []).map((t) => <span className="chip" key={t}>{t}</span>)}
              </div>
            )}
            {(item.matches || []).length > 0 && (
              <div className="rec-matches">
                {item.matches.map((m, i) => (
                  <button
                    key={i}
                    className="match"
                    onClick={(e) => { e.stopPropagation(); onSeekTo(item.id, m.start) }}
                  >
                    <span className="ts">{hms(m.start)}</span>
                    {m.speaker && <span className="who">{m.speaker}</span>}
                    <span className="txt">{m.text}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </li>
      ))}
    </ul>
  )
}
