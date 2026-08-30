import React, { useState } from 'react'
import { api } from '../api.js'

/** Who's in this recording — rename them, and resolve anything Stealth-Scribe
 *  thinks it recognised. This is the training loop: every name a human
 *  confirms here teaches the voice library. */
export default function SpeakerBar({ doc, onChanged }) {
  const [editing, setEditing] = useState(null)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const speakers = Object.keys(doc.speaker_labels || {})
  const matches = doc.speaker_matches || {}
  if (!speakers.length) return null

  const run = async (fn) => {
    setBusy(true); setError('')
    try { await fn(); await onChanged() } catch (err) { setError(err.message) }
    finally { setBusy(false); setEditing(null) }
  }

  const save = (raw) => {
    const name = draft.trim()
    if (!name || name === doc.speaker_labels[raw]) { setEditing(null); return }
    run(() => api.renameSpeakers(doc.id, { [raw]: name }))
  }

  const pending = speakers.filter((s) => matches[s] && !matches[s].applied)

  return (
    <section className="speaker-bar">
      <div className="section-title">Voices in this recording</div>

      <div className="speaker-chips">
        {speakers.map((raw, i) => {
          const name = doc.speaker_labels[raw]
          const hit = matches[raw]
          return (
            <div className={`speaker-chip s${i % 6}`} key={raw}>
              <span className="swatch" />
              {editing === raw ? (
                <input
                  autoFocus
                  value={draft}
                  disabled={busy}
                  onChange={(e) => setDraft(e.target.value)}
                  onBlur={() => save(raw)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') save(raw)
                    if (e.key === 'Escape') setEditing(null)
                  }}
                />
              ) : (
                <button
                  className="speaker-name"
                  title="Click to rename this voice everywhere in the transcript"
                  onClick={() => { setEditing(raw); setDraft(name) }}
                >
                  {name}
                </button>
              )}
              {hit?.applied && (
                <span className="recognised" title={`Matched your saved voiceprint (${hit.score})`}>
                  recognised
                </span>
              )}
            </div>
          )
        })}
      </div>

      {pending.length > 0 && (
        <div className="recognitions">
          {pending.map((raw) => {
            const hit = matches[raw]
            return (
              <div className="recognition" key={raw}>
                <div>
                  <strong>Is {doc.speaker_labels[raw]} actually {hit.name}?</strong>
                  <div className="muted small">
                    {hit.contested_by
                      ? `Another voice in this recording is a closer match for ${hit.name}.`
                      : hit.ambiguous
                        ? 'Two saved voices scored almost the same, so this is a guess.'
                        : `Similarity ${(hit.score * 100).toFixed(0)}% against your saved voiceprint.`}
                  </div>
                </div>
                <div className="recognition-actions">
                  <button className="btn" disabled={busy}
                          onClick={() => run(() => api.confirmSpeaker(doc.id, raw, true))}>
                    Yes, that&rsquo;s {hit.name}
                  </button>
                  <button className="btn ghost" disabled={busy}
                          onClick={() => run(() => api.confirmSpeaker(doc.id, raw, false))}>
                    No
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {error && <div className="rec-error">{error}</div>}

      <div className="muted small">
        {doc.embedding_engine === 'pyannote'
          ? 'Naming a voice here teaches Stealth-Scribe to recognise that person in future recordings.'
          : doc.embedding_engine === 'builtin'
            ? 'Voices were separated with the built-in detector, which is too weak to recognise people across recordings. Add a Hugging Face token to the worker for that.'
            : 'No voiceprints were captured for this recording.'}
      </div>
    </section>
  )
}
