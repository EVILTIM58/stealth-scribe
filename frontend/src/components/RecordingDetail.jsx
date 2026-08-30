import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, hms, humanDate, humanBytes } from '../api.js'
import SpeakerBar from './SpeakerBar.jsx'
import PrintView from './PrintView.jsx'

export default function RecordingDetail({ id, seekTo, onClose, onChanged }) {
  const [doc, setDoc] = useState(null)
  const [error, setError] = useState('')
  const [tab, setTab] = useState('transcript')
  const [time, setTime] = useState(0)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState({})
  const [speakerDraft, setSpeakerDraft] = useState({})
  const [follow, setFollow] = useState(true)
  const [menuFor, setMenuFor] = useState(null)
  const [files, setFiles] = useState([])
  const [view, setView] = useState('en')   // en | orig | both
  const audioRef = useRef(null)
  const activeRef = useRef(null)

  const load = useCallback(async () => {
    try {
      const data = await api.get(id)
      setDoc(data)
      setDraft({
        title: data.title || '',
        folder: data.folder || '',
        tags: (data.tags || []).join(', '),
        notes: data.notes || ''
      })
      setSpeakerDraft({ ...(data.speaker_labels || {}) })
    } catch (err) {
      setError(err.message)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  // What actually exists on disk for this recording.
  useEffect(() => {
    if (doc?.status !== 'done') return
    let cancelled = false
    api.files(id).then((r) => { if (!cancelled) setFiles(r.files) }).catch(() => {})
    return () => { cancelled = true }
  }, [id, doc?.status, doc?.updated_at])

  // Keep polling while it is still being transcribed.
  useEffect(() => {
    if (!doc || (doc.status !== 'processing' && doc.status !== 'queued')) return
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [doc, load])

  useEffect(() => {
    if (seekTo != null && audioRef.current) {
      audioRef.current.currentTime = seekTo
      audioRef.current.play().catch(() => {})
    }
  }, [seekTo, doc])

  const segments = doc?.segments || []
  const translation = doc?.translation || []
  const hasTranslation = translation.length > 0
  const rtl = !!doc?.is_rtl
  // Show the English by default when it exists -- that is the reason it exists.
  const showing = !hasTranslation ? 'orig' : view
  const displaySegments = showing === 'orig' ? segments : translation

  // For side-by-side, find the original lines that overlap an English turn.
  const originalUnder = (turn) =>
    segments.filter((s) => s.start < turn.end && s.end > turn.start)
            .map((s) => s.text).join(' ')

  const activeIndex = useMemo(() => {
    if (!displaySegments.length) return -1
    let lo = 0, hi = displaySegments.length - 1, found = -1
    while (lo <= hi) {
      const mid = (lo + hi) >> 1
      if (time >= displaySegments[mid].start) { found = mid; lo = mid + 1 } else { hi = mid - 1 }
    }
    if (found >= 0 && time > displaySegments[found].end + 2) return -1
    return found
  }, [displaySegments, time])

  useEffect(() => {
    if (follow && activeRef.current) {
      activeRef.current.scrollIntoView({ block: 'center', behavior: 'smooth' })
    }
  }, [activeIndex, follow])

  const seek = (seconds) => {
    if (!audioRef.current) return
    audioRef.current.currentTime = Math.max(0, seconds)
    audioRef.current.play().catch(() => {})
  }

  const speakerName = (raw) => (doc?.speaker_labels || {})[raw] || raw || ''

  // Diarization gets turns wrong -- crosstalk, a cough, someone leaning away
  // from the mic. Let the human just fix it instead of re-transcribing.
  const reassign = async (turn, toSpeaker) => {
    setMenuFor(null)
    try {
      for (const part of turn.parts) {
        await api.reassign(id, { segment_index: part.index, to_speaker: toSpeaker })
      }
      await load()
      onChanged()
    } catch (err) {
      setError(err.message)
    }
  }

  const turns = useMemo(() => {
    const out = []
    for (let i = 0; i < displaySegments.length; i++) {
      const seg = displaySegments[i]
      const prev = out[out.length - 1]
      // Same speaker, no long gap, and don't let one block grow past ~45s --
      // otherwise a single-speaker recording renders as one wall of text.
      const sameBlock =
        prev &&
        prev.speaker === seg.speaker &&
        seg.start - prev.end < 30 &&
        seg.end - prev.start < 45
      if (sameBlock) {
        prev.end = seg.end
        prev.parts.push({ ...seg, index: i })
      } else {
        out.push({ speaker: seg.speaker, start: seg.start, end: seg.end, parts: [{ ...seg, index: i }] })
      }
    }
    return out
  }, [displaySegments])

  const save = async () => {
    try {
      await api.patch(id, {
        title: draft.title,
        folder: draft.folder,
        tags: draft.tags.split(',').map((t) => t.trim()).filter(Boolean),
        notes: draft.notes
      })
      const changed = Object.entries(speakerDraft).filter(
        ([k, v]) => v && v !== (doc.speaker_labels || {})[k]
      )
      if (changed.length) await api.renameSpeakers(id, Object.fromEntries(changed))
      setEditing(false)
      await load()
      onChanged()
    } catch (err) {
      setError(err.message)
    }
  }

  const requeue = async () => {
    await api.requeue(id, {})
    await load()
    onChanged()
  }

  const remove = async () => {
    if (!window.confirm('Delete this recording, its audio file and its transcript?')) return
    await api.remove(id)
    onChanged()
    onClose()
  }

  if (error) return <div className="detail"><div className="rec-error">{error}</div></div>
  if (!doc) return <div className="detail"><div className="empty"><div className="pulse-eye" /></div></div>

  const summary = doc.summary || {}
  const speakers = Object.keys(doc.speaker_labels || {})
  const busy = doc.status === 'queued' || doc.status === 'processing'
  const isVideo = doc.kind === 'video' || String(doc.mime || '').startsWith('video/')

  return (
    <div className="detail">
      <header className="detail-head">
        <button className="link back" onClick={onClose}>&larr; Library</button>
        <div className="detail-actions">
          {doc.status === 'done' && (
            <button className="btn ghost" onClick={() => window.print()}>Print</button>
          )}
          {!busy && <button className="btn ghost" onClick={requeue}>Re-transcribe</button>}
          <button className="btn ghost danger" onClick={remove}>Delete</button>
        </div>
      </header>

      {editing ? (
        <div className="edit-panel">
          <label>Title<input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} /></label>
          <div className="two-col">
            <label>Folder<input value={draft.folder} onChange={(e) => setDraft({ ...draft, folder: e.target.value })} /></label>
            <label>Tags<input value={draft.tags} placeholder="comma, separated" onChange={(e) => setDraft({ ...draft, tags: e.target.value })} /></label>
          </div>
          {speakers.length > 0 && (
            <div className="speaker-edit">
              <div className="section-title">Who is who</div>
              {speakers.map((raw) => (
                <label key={raw} className="speaker-row">
                  <span className={`swatch s${speakers.indexOf(raw) % 6}`} />
                  <input
                    value={speakerDraft[raw] || ''}
                    placeholder={raw}
                    onChange={(e) => setSpeakerDraft({ ...speakerDraft, [raw]: e.target.value })}
                  />
                </label>
              ))}
            </div>
          )}
          <label>Notes<textarea rows={4} value={draft.notes} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} /></label>
          <div className="edit-actions">
            <button className="btn" onClick={save}>Save changes</button>
            <button className="btn ghost" onClick={() => { setEditing(false); load() }}>Cancel</button>
          </div>
        </div>
      ) : (
        <div className="detail-title">
          <h2>{doc.title || doc.original_name}</h2>
          <button className="link" onClick={() => setEditing(true)}>Edit details</button>
          <div className="rec-meta">
            <span>Recorded {humanDate(doc.recorded_at)}</span>
            {doc.duration_sec > 0 && <span>{hms(doc.duration_sec)}</span>}
            {doc.word_count > 0 && <span>{doc.word_count.toLocaleString()} words</span>}
            {doc.language && <span>{doc.language}</span>}
            {doc.finished_at && <span>Transcribed {humanDate(doc.finished_at)}</span>}
          </div>
          {(doc.folder || (doc.tags || []).length > 0) && (
            <div className="rec-tags">
              {doc.folder && <span className="chip folder">{doc.folder}</span>}
              {(doc.tags || []).map((t) => <span className="chip" key={t}>{t}</span>)}
            </div>
          )}
        </div>
      )}

      <div className={`player ${isVideo ? 'video' : ''}`}>
        {isVideo ? (
          <video
            ref={audioRef}
            src={api.mediaUrl(id)}
            controls
            playsInline
            preload="metadata"
            onTimeUpdate={(e) => setTime(e.target.currentTime)}
          />
        ) : (
          <audio
            ref={audioRef}
            src={api.mediaUrl(id)}
            controls
            preload="metadata"
            onTimeUpdate={(e) => setTime(e.target.currentTime)}
          />
        )}
        <label className="follow">
          <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} />
          Follow along
        </label>
      </div>

      {busy && (
        <div className="processing-panel">
          <div className="pulse-eye small" />
          <div>
            <strong>{doc.status === 'queued' ? 'Waiting for a worker' : 'Transcribing'}</strong>
            <div className="muted small">{doc.stage}</div>
            {doc.status === 'processing' && (
              <div className="rec-progress">
                <span className="track">
                  <i style={{ width: `${Math.round((doc.progress || 0) * 100)}%` }} />
                </span>
              </div>
            )}
            {doc.status === 'queued' && (
              <div className="muted small">
                Start the Stealth-Scribe worker on your PC and this will begin automatically.
              </div>
            )}
          </div>
        </div>
      )}

      {doc.status === 'failed' && <div className="rec-error">{doc.error}</div>}

      {doc.status === 'done' && (
        <>
          <section className="downloads">
            <div className="section-title">Files</div>
            <div className="download-row">
              {files.map((f) => (
                <a
                  key={f.kind}
                  className={`download-card ${f.available ? '' : 'pending'}`}
                  href={api.downloadUrl(id, f.kind)}
                  download
                >
                  <span className={`dl-kind ${f.kind}`}>{f.kind.toUpperCase()}</span>
                  <span className="dl-label">{f.label}</span>
                  <span className="muted small">
                    {f.available ? humanBytes(f.bytes) : 'generated on download'}
                  </span>
                </a>
              ))}
            </div>
            <div className="muted small">
              All three live together on the server. Large downloads resume if the
              connection drops.
            </div>
          </section>

          <SpeakerBar doc={doc} onChanged={async () => { await load(); onChanged() }} />

          <div className="tabs">
            <button className={tab === 'transcript' ? 'active' : ''} onClick={() => setTab('transcript')}>Transcript</button>
            <button className={tab === 'summary' ? 'active' : ''} onClick={() => setTab('summary')}>Summary</button>
            {doc.notes && <button className={tab === 'notes' ? 'active' : ''} onClick={() => setTab('notes')}>Notes</button>}
          </div>

          {tab === 'summary' && (
            <div className="summary-panel">
              <p className="overview">{summary.overview}</p>
              {(summary.key_points || []).length > 0 && (
                <>
                  <div className="section-title">Key points</div>
                  <ul className="bullets">{summary.key_points.map((k, i) => <li key={i}>{k}</li>)}</ul>
                </>
              )}
              {(summary.action_items || []).length > 0 && (
                <>
                  <div className="section-title">Action items</div>
                  <ul className="bullets actions">{summary.action_items.map((k, i) => <li key={i}>{k}</li>)}</ul>
                </>
              )}
              {(summary.questions || []).length > 0 && (
                <>
                  <div className="section-title">Questions raised</div>
                  <ul className="bullets questions">{summary.questions.map((k, i) => <li key={i}>{k}</li>)}</ul>
                </>
              )}
              {(summary.topics || []).length > 0 && (
                <>
                  <div className="section-title">Frequent topics</div>
                  <div className="rec-tags">{summary.topics.map((t) => <span className="chip" key={t}>{t}</span>)}</div>
                </>
              )}
              <div className="muted small source-note">
                Summary generated {summary.source === 'ai' ? 'by AI' : 'on your own hardware, offline'}.
              </div>
            </div>
          )}

          {tab === 'notes' && <div className="summary-panel"><p className="overview">{doc.notes}</p></div>}

          {tab === 'transcript' && hasTranslation && (
            <div className="lang-toggle">
              <span className="muted small">
                {doc.language_name || doc.language} detected &mdash; translated to English
              </span>
              <div className="lang-buttons">
                <button className={showing === 'en' ? 'active' : ''}
                        onClick={() => setView('en')}>English</button>
                <button className={showing === 'orig' ? 'active' : ''}
                        onClick={() => setView('orig')}>{doc.language_name || 'Original'}</button>
                <button className={showing === 'both' ? 'active' : ''}
                        onClick={() => setView('both')}>Both</button>
              </div>
            </div>
          )}

          {tab === 'transcript' && (
            <div className="transcript">
              {turns.map((turn, ti) => {
                const isActive = turn.parts.some((p) => p.index === activeIndex)
                const idx = speakers.indexOf(turn.speaker)
                return (
                  <div className={`turn ${isActive ? 'active' : ''}`} key={ti} ref={isActive ? activeRef : null}>
                    <div className="turn-head">
                      <button className="ts" onClick={() => seek(turn.start)}>{hms(turn.start)}</button>
                      {turn.speaker && (
                        <span className="who-wrap">
                          <button
                            className={`who swatch-text s${(idx < 0 ? 0 : idx) % 6}`}
                            title="Wrong speaker? Click to reassign this turn."
                            onClick={() => setMenuFor(menuFor === ti ? null : ti)}
                          >
                            {speakerName(turn.speaker)}
                          </button>
                          {menuFor === ti && (
                            <>
                              <span className="menu-scrim" onClick={() => setMenuFor(null)} />
                              <span className="menu turn-menu">
                                <span className="menu-head small muted">
                                  This turn is actually&hellip;
                                </span>
                                {speakers.filter((s) => s !== turn.speaker).map((s) => (
                                  <button key={s} onClick={() => reassign(turn, s)}>
                                    {speakerName(s)}
                                  </button>
                                ))}
                                {speakers.length < 2 && (
                                  <span className="menu-head small muted">
                                    Only one voice was detected.
                                  </span>
                                )}
                              </span>
                            </>
                          )}
                        </span>
                      )}
                    </div>
                    <p dir={showing === 'orig' && rtl ? 'rtl' : 'ltr'}>
                      {turn.parts.map((p) => (
                        <span
                          key={p.index}
                          className={p.index === activeIndex ? 'seg current' : 'seg'}
                          onClick={() => seek(p.start)}
                          title={hms(p.start)}
                        >
                          {p.text}{' '}
                        </span>
                      ))}
                    </p>
                    {showing === 'both' && (
                      <p className="orig-line" dir={rtl ? 'rtl' : 'ltr'}>
                        {originalUnder(turn)}
                      </p>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </>
      )}
      {doc.status === 'done' && <PrintView doc={doc} />}

    </div>
  )
}
