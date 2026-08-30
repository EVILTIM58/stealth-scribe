import React, { useCallback, useEffect, useRef, useState } from 'react'
import { uploadFile, hms, humanBytes } from '../api.js'

// Browsers disagree on what they can record. Ask, don't assume.
// Android/desktop Chrome -> webm/opus. iOS Safari (14.3+) -> mp4/aac.
const MIME_CANDIDATES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/mp4;codecs=mp4a.40.2',
  'audio/mp4',
  'audio/ogg;codecs=opus',
  'audio/mpeg'
]

const EXT_BY_MIME = {
  'audio/webm': '.webm',
  'audio/mp4': '.m4a',
  'audio/ogg': '.ogg',
  'audio/mpeg': '.mp3',
  'audio/wav': '.wav'
}

function pickMimeType() {
  if (typeof MediaRecorder === 'undefined') return null
  for (const type of MIME_CANDIDATES) {
    try {
      if (MediaRecorder.isTypeSupported(type)) return type
    } catch { /* older browsers throw instead of returning false */ }
  }
  return ''
}

function baseMime(type) {
  return (type || '').split(';')[0].trim().toLowerCase()
}

function stamp(d) {
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ` +
         `${p(d.getHours())}-${p(d.getMinutes())}-${p(d.getSeconds())}`
}

export default function LiveRecorder({ folders, onUploaded, onClose }) {
  const [phase, setPhase] = useState('idle')  // idle | recording | paused | review | uploading
  const [seconds, setSeconds] = useState(0)
  const [level, setLevel] = useState(0)
  const [error, setError] = useState('')
  const [blob, setBlob] = useState(null)
  const [blobUrl, setBlobUrl] = useState('')
  const [progress, setProgress] = useState(0)
  const [meta, setMeta] = useState({ title: '', folder: '', tags: '' })

  const streamRef = useRef(null)
  const recorderRef = useRef(null)
  const partsRef = useRef([])
  const startedAtRef = useRef(null)
  const timerRef = useRef(null)
  const rafRef = useRef(null)
  const audioCtxRef = useRef(null)
  const wakeLockRef = useRef(null)

  const secure = typeof window !== 'undefined' &&
    (window.isSecureContext || window.location.hostname === 'localhost')
  const supported = typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined'

  // ---------------------------------------------------------------- cleanup
  const teardown = useCallback(() => {
    clearInterval(timerRef.current)
    cancelAnimationFrame(rafRef.current)
    try { streamRef.current?.getTracks().forEach((t) => t.stop()) } catch { /* ignore */ }
    streamRef.current = null
    try { audioCtxRef.current?.close() } catch { /* ignore */ }
    audioCtxRef.current = null
    try { wakeLockRef.current?.release() } catch { /* ignore */ }
    wakeLockRef.current = null
    setLevel(0)
  }, [])

  useEffect(() => () => {
    teardown()
    if (blobUrl) URL.revokeObjectURL(blobUrl)
  }, [teardown, blobUrl])

  // -------------------------------------------------------------- metering
  const startMeter = (stream) => {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext
      if (!Ctx) return
      const ctx = new Ctx()
      audioCtxRef.current = ctx
      const source = ctx.createMediaStreamSource(stream)
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 1024
      source.connect(analyser)
      const buf = new Uint8Array(analyser.fftSize)
      const tick = () => {
        analyser.getByteTimeDomainData(buf)
        let sum = 0
        for (let i = 0; i < buf.length; i++) {
          const v = (buf[i] - 128) / 128
          sum += v * v
        }
        // RMS -> 0..1, with a curve that makes speech visible
        setLevel(Math.min(1, Math.sqrt(sum / buf.length) * 3.2))
        rafRef.current = requestAnimationFrame(tick)
      }
      tick()
    } catch { /* metering is a nicety, never fatal */ }
  }

  // ----------------------------------------------------------------- start
  const start = async () => {
    setError('')
    if (!secure) {
      setError('insecure')
      return
    }
    if (!supported) {
      setError('This browser cannot record audio. Try Chrome or Safari.')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1
        }
      })
      streamRef.current = stream

      const mimeType = pickMimeType()
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      partsRef.current = []
      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) partsRef.current.push(e.data)
      }
      recorder.onstop = () => {
        const type = baseMime(recorder.mimeType || mimeType) || 'audio/webm'
        const finished = new Blob(partsRef.current, { type })
        setBlob(finished)
        setBlobUrl((old) => {
          if (old) URL.revokeObjectURL(old)
          return URL.createObjectURL(finished)
        })
        setPhase('review')
        teardown()
      }
      recorder.onerror = (e) => {
        setError(`Recording stopped: ${e.error?.message || 'unknown error'}`)
        setPhase('idle')
        teardown()
      }

      // 1s slices: data arrives steadily instead of one huge blob at the end,
      // so a crash costs a second rather than the whole session.
      recorder.start(1000)
      recorderRef.current = recorder
      startedAtRef.current = new Date()
      setSeconds(0)
      setPhase('recording')

      timerRef.current = setInterval(
        () => setSeconds((s) => s + 1), 1000
      )
      startMeter(stream)

      // Keep the screen awake -- a locked phone suspends the recorder.
      try {
        wakeLockRef.current = await navigator.wakeLock?.request('screen')
      } catch { /* not supported / denied, not fatal */ }
    } catch (err) {
      if (err.name === 'NotAllowedError' || err.name === 'SecurityError') {
        setError('Microphone permission was denied. Allow it in your browser settings and try again.')
      } else if (err.name === 'NotFoundError') {
        setError('No microphone found on this device.')
      } else {
        setError(err.message || String(err))
      }
      teardown()
    }
  }

  const pause = () => {
    try {
      recorderRef.current?.pause()
      clearInterval(timerRef.current)
      setPhase('paused')
    } catch { /* not supported everywhere */ }
  }

  const resume = () => {
    try {
      recorderRef.current?.resume()
      timerRef.current = setInterval(() => setSeconds((s) => s + 1), 1000)
      setPhase('recording')
    } catch { /* ignore */ }
  }

  const stop = () => {
    try {
      recorderRef.current?.stop()
    } catch {
      teardown()
      setPhase('idle')
    }
  }

  const discard = () => {
    if (blobUrl) URL.revokeObjectURL(blobUrl)
    setBlob(null)
    setBlobUrl('')
    setSeconds(0)
    setPhase('idle')
    setMeta({ title: '', folder: '', tags: '' })
  }

  // ---------------------------------------------------------------- upload
  const save = async () => {
    if (!blob) return
    setPhase('uploading')
    setProgress(0)
    try {
      const started = startedAtRef.current || new Date()
      const ext = EXT_BY_MIME[baseMime(blob.type)] || '.webm'
      const filename = `Stealth-Scribe ${stamp(started)}${ext}`
      const file = new File([blob], filename, { type: blob.type })
      await uploadFile(
        file,
        {
          title: meta.title.trim() || `Live recording ${stamp(started)}`,
          folder: meta.folder.trim(),
          tags: meta.tags.split(',').map((t) => t.trim()).filter(Boolean),
          recordedAt: started.toISOString(),
          mime: blob.type
        },
        setProgress
      )
      discard()
      onUploaded()
      onClose?.()
    } catch (err) {
      setError(err.message)
      setPhase('review')
    }
  }

  // ------------------------------------------------------------------- UI
  if (error === 'insecure') {
    return <InsecureNotice onDismiss={() => setError('')} />
  }

  return (
    <section className="recorder">
      <div className="recorder-head">
        <h3>Record now</h3>
        <button className="link" onClick={onClose}>Close</button>
      </div>

      {error && <div className="rec-error">{error}</div>}

      {!secure && phase === 'idle' && (
        <div className="notice">
          <strong>Microphone blocked on this address.</strong>{' '}
          Browsers only allow recording over HTTPS.{' '}
          <button className="link" onClick={() => setError('insecure')}>How to fix it</button>
        </div>
      )}

      {(phase === 'idle') && (
        <div className="rec-idle">
          <button className="record-btn" onClick={start} aria-label="Start recording">
            <span className="record-dot" />
          </button>
          <div className="muted small">
            Tap to start. Stealth-Scribe records on this device, then uploads to the NAS
            and queues it for transcription like any other file.
          </div>
        </div>
      )}

      {(phase === 'recording' || phase === 'paused') && (
        <div className="rec-live">
          <div className="rec-live-top">
            <span className={`live-dot ${phase === 'recording' ? 'on' : ''}`} />
            <span className="rec-timer">{hms(seconds)}</span>
            <span className="muted small">
              {phase === 'paused' ? 'paused' : 'recording'}
            </span>
          </div>

          <div className="meter" aria-hidden="true">
            <i style={{ width: `${Math.round(level * 100)}%` }} />
          </div>

          <div className="rec-actions">
            {phase === 'recording'
              ? <button className="btn ghost" onClick={pause}>Pause</button>
              : <button className="btn ghost" onClick={resume}>Resume</button>}
            <button className="btn" onClick={stop}>Stop</button>
          </div>

          <div className="muted small">
            Keep this screen on. If the phone locks, recording may stop.
          </div>
        </div>
      )}

      {phase === 'review' && (
        <div className="rec-review">
          <div className="rec-live-top">
            <span className="rec-timer">{hms(seconds)}</span>
            <span className="muted small">{blob ? humanBytes(blob.size) : ''}</span>
          </div>
          <audio src={blobUrl} controls preload="metadata" />
          <label>
            Title
            <input
              value={meta.title}
              placeholder="What was this?"
              onChange={(e) => setMeta({ ...meta, title: e.target.value })}
            />
          </label>
          <div className="two-col">
            <label>
              Folder
              <input
                list="rec-folder-options"
                value={meta.folder}
                onChange={(e) => setMeta({ ...meta, folder: e.target.value })}
              />
              <datalist id="rec-folder-options">
                {folders.map((f) => f.name && <option key={f.name} value={f.name} />)}
              </datalist>
            </label>
            <label>
              Tags
              <input
                value={meta.tags}
                placeholder="comma, separated"
                onChange={(e) => setMeta({ ...meta, tags: e.target.value })}
              />
            </label>
          </div>
          <div className="rec-actions">
            <button className="btn" onClick={save}>Save &amp; transcribe</button>
            <button className="btn ghost danger" onClick={discard}>Discard</button>
          </div>
        </div>
      )}

      {phase === 'uploading' && (
        <div className="rec-live">
          <div className="muted">Uploading...</div>
          <div className="rec-progress">
            <span className="track">
              <i style={{ width: `${Math.round(progress * 100)}%` }} />
            </span>
            <span className="muted small">{Math.round(progress * 100)}%</span>
          </div>
        </div>
      )}
    </section>
  )
}

function InsecureNotice({ onDismiss }) {
  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  return (
    <section className="recorder">
      <div className="recorder-head">
        <h3>Microphone needs a secure connection</h3>
        <button className="link" onClick={onDismiss}>Back</button>
      </div>
      <p className="muted">
        Every browser refuses microphone access on a plain <code>http://</code> address
        that isn&apos;t <code>localhost</code>. This is a browser rule, not a Stealth-Scribe
        setting &mdash; nothing in the app can override it. You are on{' '}
        <code>{origin}</code>. Any one of these fixes it:
      </p>
      <ol className="fix-list">
        <li>
          <strong>Put Stealth-Scribe behind your Cloudflare tunnel</strong> so it&apos;s reached
          over <code>https://</code>. Best long-term answer &mdash; it also makes recording
          work away from home. Add Cloudflare Access first, since Stealth-Scribe has no login.
        </li>
        <li>
          <strong>Tell Chrome to trust this origin.</strong> On the phone or desktop open{' '}
          <code>chrome://flags/#unsafely-treat-insecure-origin-as-secure</code>, add{' '}
          <code>{origin}</code>, set the flag to Enabled and relaunch. Fastest fix, and it
          only affects your own browser.
        </li>
        <li>
          <strong>Give nginx a self-signed certificate.</strong> You&apos;ll accept a
          one-time browser warning, after which the origin counts as secure.
        </li>
      </ol>
      <p className="muted small">
        Uploading files you recorded with your phone&apos;s own voice recorder app works
        fine over plain http &mdash; only live capture is restricted.
      </p>
    </section>
  )
}
