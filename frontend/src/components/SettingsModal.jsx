import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

// Common languages, mirroring backend/languages.py. Whisper handles many more;
// "Detect automatically" covers anything not listed here.
const LANGUAGES = [
  { code: 'en', name: 'English' }, { code: 'es', name: 'Spanish' },
  { code: 'fr', name: 'French' }, { code: 'de', name: 'German' },
  { code: 'it', name: 'Italian' }, { code: 'pt', name: 'Portuguese' },
  { code: 'nl', name: 'Dutch' }, { code: 'pl', name: 'Polish' },
  { code: 'ru', name: 'Russian' }, { code: 'uk', name: 'Ukrainian' },
  { code: 'ar', name: 'Arabic' }, { code: 'he', name: 'Hebrew' },
  { code: 'fa', name: 'Persian (Farsi)' }, { code: 'ur', name: 'Urdu' },
  { code: 'tr', name: 'Turkish' }, { code: 'zh', name: 'Chinese' },
  { code: 'ja', name: 'Japanese' }, { code: 'ko', name: 'Korean' },
  { code: 'hi', name: 'Hindi' }, { code: 'vi', name: 'Vietnamese' },
  { code: 'th', name: 'Thai' }, { code: 'id', name: 'Indonesian' },
  { code: 'tl', name: 'Tagalog' }, { code: 'sw', name: 'Swahili' },
  { code: 'el', name: 'Greek' }, { code: 'ro', name: 'Romanian' },
  { code: 'so', name: 'Somali' }, { code: 'ps', name: 'Pashto' }
]

const MODELS = [
  ['tiny', 'Fastest, roughest'],
  ['base', 'Fast, clear speech only'],
  ['small', 'Good balance'],
  ['medium', 'Recommended'],
  ['large-v3', 'Best accuracy, slowest']
]

export default function SettingsModal({ onClose }) {
  const [s, setS] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => { api.settings().then(setS).catch(() => setS({})) }, [])

  const save = async () => {
    setSaving(true)
    try {
      await api.saveSettings({
        model_size: s.model_size,
        language: s.language,
        speaker_mode: s.speaker_mode,
        num_speakers: Number(s.num_speakers) || 0,
        summary_mode: s.summary_mode,
        translate: s.translate || 'auto',
        show_timestamps: !!s.show_timestamps
      })
      onClose()
    } finally {
      setSaving(false)
    }
  }

  if (!s) return null
  const set = (patch) => setS({ ...s, ...patch })

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>Transcription settings</h2>
        <p className="muted small">
          These apply to new uploads. Existing recordings keep the settings they were made with &mdash;
          use &ldquo;Re-transcribe&rdquo; to redo one with the current settings.
        </p>

        <label>
          Accuracy
          <select value={s.model_size} onChange={(e) => set({ model_size: e.target.value })}>
            {MODELS.map(([v, note]) => <option key={v} value={v}>{v} &mdash; {note}</option>)}
          </select>
        </label>

        <label>
          Spoken language
          <select value={s.language} onChange={(e) => set({ language: e.target.value })}>
            <option value="auto">Detect automatically (recommended)</option>
            {LANGUAGES.map((l) => (
              <option key={l.code} value={l.code}>{l.name}</option>
            ))}
          </select>
        </label>

        <label>
          Translate to English
          <select value={s.translate || 'auto'} onChange={(e) => set({ translate: e.target.value })}>
            <option value="auto">When the audio isn&rsquo;t English (recommended)</option>
            <option value="always">Always, even for English audio</option>
            <option value="off">Never &mdash; keep the original only</option>
          </select>
        </label>
        <div className="muted small">
          Whisper translates any of ~99 languages into English. It adds a second
          pass, so a translated recording takes roughly twice as long. The
          original is always kept alongside the translation.
          {s.model_size !== 'large-v3' && (s.language !== 'en') && (
            <> <strong>For non-English audio, large-v3 is noticeably more
            accurate than medium</strong> &mdash; especially for Arabic, Hindi
            and Chinese.</>
          )}
        </div>

        <div className="two-col">
          <label>
            Speaker labels
            <select value={s.speaker_mode} onChange={(e) => set({ speaker_mode: e.target.value })}>
              <option value="auto">Best available</option>
              <option value="builtin">Built-in (no token)</option>
              <option value="off">Off</option>
            </select>
          </label>
          <label>
            How many speakers
            <select value={String(s.num_speakers || 0)} onChange={(e) => set({ num_speakers: e.target.value })}>
              <option value="0">Detect automatically</option>
              {[1, 2, 3, 4, 5, 6].map((n) => <option key={n} value={String(n)}>{n}</option>)}
            </select>
          </label>
        </div>

        <label>
          Summary
          <select value={s.summary_mode} onChange={(e) => set({ summary_mode: e.target.value })}>
            <option value="offline">Offline &mdash; free, private, no internet</option>
            <option value="ai">AI &mdash; needs an API key on the worker</option>
          </select>
        </label>

        <label className="checkbox">
          <input
            type="checkbox"
            checked={!!s.show_timestamps}
            onChange={(e) => set({ show_timestamps: e.target.checked })}
          />
          Put timestamps on every turn in the .txt file
        </label>

        <div className="edit-actions">
          <button className="btn" onClick={save} disabled={saving}>
            {saving ? 'Saving...' : 'Save'}
          </button>
          <button className="btn ghost" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  )
}
