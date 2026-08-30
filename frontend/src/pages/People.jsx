import React, { useCallback, useEffect, useState } from 'react'
import { api, hms, humanDate } from '../api.js'
import { Link } from '../router.jsx'

export default function PeoplePage() {
  const [people, setPeople] = useState([])
  const [trained, setTrained] = useState(0)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(null)
  const [draft, setDraft] = useState('')
  const [mergeFrom, setMergeFrom] = useState(null)
  const [expanded, setExpanded] = useState(null)
  const [recordings, setRecordings] = useState({})

  const load = useCallback(async () => {
    try {
      const data = await api.people()
      setPeople(data.items)
      setTrained(data.trained)
      setError('')
    } catch (err) { setError(err.message) }
  }, [])

  useEffect(() => { load() }, [load])

  const act = async (fn) => {
    try { await fn(); await load() } catch (err) { setError(err.message) }
  }

  const open = async (person) => {
    if (expanded === person.id) { setExpanded(null); return }
    setExpanded(person.id)
    if (!recordings[person.id]) {
      try {
        const data = await api.personRecordings(person.id)
        setRecordings((r) => ({ ...r, [person.id]: data.items }))
      } catch (err) { setError(err.message) }
    }
  }

  return (
    <div className="people">
      <Link to="/" className="link back">&larr; Library</Link>
      <h1>Voices Stealth-Scribe knows</h1>
      <p className="muted">
        Every time you put a name to a voice, Stealth-Scribe remembers what that person
        sounds like. In later recordings it labels them for you automatically.
      </p>

      {error && <div className="rec-error banner">{error}</div>}

      <div className="stat-row">
        <div className="stat"><span className="stat-n">{people.length}</span>
          <span className="stat-l">People named</span></div>
        <div className="stat"><span className="stat-n">{trained}</span>
          <span className="stat-l">With a real voiceprint</span></div>
        <div className="stat">
          <span className="stat-n">{people.reduce((n, p) => n + p.samples, 0)}</span>
          <span className="stat-l">Confirmations learned</span></div>
      </div>

      {!people.length && (
        <div className="empty">
          <img src="/ss-mark.webp" alt="" className="empty-mark" />
          <h3>No voices yet</h3>
          <p className="muted">
            Open a transcript and put a name to one of the voices. Stealth-Scribe starts
            learning from that moment.
          </p>
        </div>
      )}

      <div className="user-table">
        {people.map((p) => (
          <div className="person-row" key={p.id}>
            <div className="person-main">
              <div className="user-id">
                <span className="avatar placeholder">{(p.name || '?')[0].toUpperCase()}</span>
                <div>
                  {editing === p.id ? (
                    <input
                      autoFocus value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Escape') setEditing(null)
                        if (e.key === 'Enter') {
                          act(() => api.updatePerson(p.id, { name: draft }))
                          setEditing(null)
                        }
                      }}
                      onBlur={() => setEditing(null)}
                    />
                  ) : (
                    <button className="person-name" onClick={() => { setEditing(p.id); setDraft(p.name) }}>
                      {p.name}
                    </button>
                  )}
                  <div className="user-meta muted small">
                    <span className={`vp-badge ${p.engine}`}>
                      {p.engine === 'pyannote' ? 'voiceprint trained'
                        : p.engine === 'builtin' ? 'weak voiceprint'
                          : 'name only'}
                    </span>
                    <span>{p.samples} confirmation{p.samples === 1 ? '' : 's'}</span>
                    <span>{p.recordings} recording{p.recordings === 1 ? '' : 's'}</span>
                    {p.updated_at && <span>updated {humanDate(p.updated_at)}</span>}
                  </div>
                </div>
              </div>
            </div>

            <div className="user-actions">
              <button className="btn ghost" onClick={() => open(p)}>
                {expanded === p.id ? 'Hide' : 'Where they appear'}
              </button>
              {mergeFrom && mergeFrom !== p.id ? (
                <button className="btn" onClick={() => {
                  act(() => api.mergePeople(p.id, mergeFrom)); setMergeFrom(null)
                }}>
                  Merge into {p.name}
                </button>
              ) : (
                <button className="btn ghost"
                        onClick={() => setMergeFrom(mergeFrom === p.id ? null : p.id)}>
                  {mergeFrom === p.id ? 'Cancel merge' : 'Same as…'}
                </button>
              )}
              <button className="btn ghost danger" onClick={() => {
                if (window.confirm(
                  `Forget ${p.name}'s voice? Transcripts keep the name, but Stealth-Scribe ` +
                  `will stop recognising them automatically.`)) {
                  act(() => api.deletePerson(p.id))
                }
              }}>Forget</button>
            </div>

            {expanded === p.id && (
              <div className="person-recordings">
                {(recordings[p.id] || []).length === 0
                  ? <span className="muted small">No transcripts carry this name yet.</span>
                  : (recordings[p.id] || []).map((r) => (
                      <div className="person-rec" key={r.id}>
                        <span>{r.title}</span>
                        <span className="muted small">
                          {humanDate(r.recorded_at)} &middot; {hms(r.duration_sec)}
                        </span>
                      </div>
                    ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {mergeFrom && (
        <div className="notice">
          Pick the person to merge <strong>{people.find((p) => p.id === mergeFrom)?.name}</strong> into.
          Their voiceprints combine and every transcript is relabelled.
        </div>
      )}
    </div>
  )
}
