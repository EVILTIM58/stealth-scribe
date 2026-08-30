import React, { useState } from 'react'
import { api, humanBytes } from '../api.js'
import { useAuth } from '../auth.jsx'
import { Link } from '../router.jsx'

/** Irreversible bulk deletion. A one-click window.confirm() is not enough
 *  friction for something with no undo, so the user has to type the word. */
function NukeDialog({ onCancel, onDone }) {
  const [typed, setTyped] = useState('')
  const [forgetVoices, setForgetVoices] = useState(true)
  const [deleteAccount, setDeleteAccount] = useState(false)
  const [busy, setBusy] = useState(false)
  const [nuking, setNuking] = useState(false)
  const [error, setError] = useState('')
  const armed = typed.trim().toUpperCase() === 'NUKE'

  const go = async () => {
    setBusy(true); setError('')
    try {
      onDone(await api.nuke({ forgetVoices, deleteAccount }))
    } catch (err) {
      setError(err.message); setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal nuke-modal" onClick={(e) => e.stopPropagation()}>
        <h2>Are you really sure?</h2>

        <div className="nuke-warning">
          <strong>NUKED FILES CANNOT BE RETRIEVED.</strong>
          <p>
            This permanently deletes every recording on your account and
            everything made from it — the audio or video file, the transcript,
            any translation, the PDF and the plain text. There is no archive,
            no recycle bin and no backup to restore from.
          </p>
          <p>
            It happens <strong>the moment you press the button</strong>. No
            support ticket, no waiting period, nobody reviews it and nobody can
            undo it. Poof, gone.
          </p>
        </div>

        <label className="checkbox">
          <input type="checkbox" checked={forgetVoices}
                 onChange={(e) => setForgetVoices(e.target.checked)} />
          Also forget every voice I have named
        </label>
        <div className="muted small">
          Leave this ticked to remove the voiceprints too. Untick it to keep your
          people library so future recordings are still recognised.
        </div>

        <label className="checkbox">
          <input type="checkbox" checked={deleteAccount}
                 onChange={(e) => setDeleteAccount(e.target.checked)} />
          Delete my whole account as well
        </label>
        {deleteAccount && (
          <div className="nuke-warning">
            <strong>YOUR ACCOUNT WILL BE ERASED TOO.</strong>
            <p>
              You will be signed out immediately and your account will no longer
              exist. Signing in again would create a brand new, empty account.
            </p>
          </div>
        )}

        <label>
          <span>Type <b className="nuke-word">NUKE</b> to confirm</span>
          <input value={typed} autoFocus autoComplete="off" spellCheck="false"
                 placeholder="NUKE"
                 onChange={(e) => setTyped(e.target.value)} />
        </label>

        {error && <div className="rec-error">{error}</div>}

        <div className="edit-actions">
          <button className="btn nuke-btn" disabled={!armed || busy} onClick={go}>
            {busy ? 'Deleting…'
              : deleteAccount ? 'Yes, erase me completely' : 'Yes, nuke everything'}
          </button>
          <button className="btn ghost" onClick={onCancel}>Keep my recordings</button>
        </div>
      </div>
    </div>
  )
}

export default function AccountPage() {
  const { user, refresh, logout } = useAuth()
  const [name, setName] = useState(user.name || '')
  const [pw, setPw] = useState({ current: '', next: '' })
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [nuking, setNuking] = useState(false)

  const save = async (body, okMessage) => {
    setBusy(true); setError(''); setMsg('')
    try {
      await api.updateProfile(body)
      await refresh()
      setMsg(okMessage)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="account-page">
      <Link to="/" className="link back">&larr; Library</Link>
      <h1>Your account</h1>

      {msg && <div className="notice">{msg}</div>}
      {error && <div className="rec-error">{error}</div>}

      <section className="edit-panel">
        <div className="section-title">Profile</div>
        <div className="account-id">
          {user.picture
            ? <img src={user.picture} alt="" className="avatar big" />
            : <span className="avatar placeholder big">{(user.name || user.email)[0].toUpperCase()}</span>}
          <div>
            <div>{user.email}</div>
            <div className="muted small">
              {user.role} · signed up with {user.providers.join(', ') || 'password'}
            </div>
          </div>
        </div>
        <label>Display name
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <div className="edit-actions">
          <button className="btn" disabled={busy || !name.trim()}
                  onClick={() => save({ name }, 'Name updated.')}>Save name</button>
        </div>
      </section>

      <section className="edit-panel">
        <div className="section-title">
          {user.has_password ? 'Change password' : 'Add a password'}
        </div>
        {!user.has_password && (
          <p className="muted small">
            You sign in with {user.providers.join(' and ')}. Adding a password lets you
            sign in with your email as well.
          </p>
        )}
        {user.has_password && (
          <label>Current password
            <input type="password" autoComplete="current-password" value={pw.current}
                   onChange={(e) => setPw({ ...pw, current: e.target.value })} />
          </label>
        )}
        <label>New password
          <input type="password" autoComplete="new-password" minLength={10} value={pw.next}
                 onChange={(e) => setPw({ ...pw, next: e.target.value })} />
        </label>
        <div className="edit-actions">
          <button className="btn" disabled={busy || pw.next.length < 10}
                  onClick={() => save(
                    { current_password: pw.current, new_password: pw.next },
                    'Password updated.'
                  ).then(() => setPw({ current: '', next: '' }))}>
            {user.has_password ? 'Change password' : 'Set password'}
          </button>
        </div>
      </section>

      <section className="edit-panel">
        <div className="section-title">Sessions</div>
        <p className="muted small">
          Signed-in sessions last 30 days. If you've used a shared or lost device,
          sign out everywhere and log back in.
        </p>
        <div className="edit-actions">
          <button className="btn ghost" onClick={() => logout()}>Sign out</button>
          <button className="btn ghost danger"
                  onClick={async () => { await api.logoutEverywhere().catch(() => {}); await refresh() }}>
            Sign out everywhere
          </button>
        </div>
      </section>

      <section className="edit-panel">
        <div className="section-title">Your data</div>
        <p className="muted small">
          Every transcript can be downloaded as audio, PDF or plain text from its
          own page. Deleting one recording removes the media file, its transcript
          and its PDF from disk. To erase everything at once &mdash; or your whole
          account &mdash; use the Nuke button below. You never need to ask us.
        </p>
      </section>

      <section className="edit-panel danger-zone">
        <div className="section-title danger">Danger zone</div>
        <div className="nuke-row">
          <div>
            <strong>Nuke everything</strong>
            <p className="muted small">
              Permanently delete every recording you have uploaded, along with its
              transcript, translation, PDF and audio file — and, if you want, your
              account itself. It happens instantly. No support ticket, no waiting
              period, no review. Nothing is archived and nothing is recoverable.
            </p>
          </div>
          <button className="btn nuke-btn" onClick={() => setNuking(true)}>
            Nuke my recordings
          </button>
        </div>
      </section>

      {nuking && (
        <NukeDialog
          onCancel={() => setNuking(false)}
          onDone={(r) => {
            setNuking(false)
            if (r.account_deleted) {
              // Nothing left to show them. Send them to the front door.
              window.location.href = '/'
              return
            }
            setMsg(
              `Nuked ${r.recordings_deleted} recording(s)` +
              (r.voices_forgotten ? `, forgot ${r.voices_forgotten} voice(s)` : '') +
              `. ${humanBytes(r.bytes_freed)} freed.`)
          }}
        />
      )}
    </div>
  )
}
