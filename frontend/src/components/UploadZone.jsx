import React, { useCallback, useRef, useState } from 'react'
import { uploadFile, humanBytes } from '../api.js'

const ACCEPT = [
  // audio
  '.mp3', '.wav', '.m4a', '.wma', '.ogg', '.oga', '.flac', '.aac', '.m4b',
  '.opus', '.amr', '.aiff', '.aif', '.3gp', '.mp2', '.ac3', '.caf', '.wv',
  // video -- the audio track is transcribed the same way
  '.mp4', '.mov', '.mkv', '.avi', '.wmv', '.webm', '.m4v', '.flv', '.mpg',
  '.mpeg', '.mts', '.m2ts', '.ts', '.vob', '.ogv', '.asf', '.3g2'
].join(',')

export default function UploadZone({ folders, onUploaded }) {
  const [dragging, setDragging] = useState(false)
  const [queue, setQueue] = useState([])
  const [folder, setFolder] = useState('')
  const [tags, setTags] = useState('')
  const inputRef = useRef(null)

  const start = useCallback(async (files) => {
    const list = Array.from(files)
    if (!list.length) return
    setQueue((q) => [...q, ...list.map((f) => ({ name: f.name, size: f.size, pct: 0, state: 'waiting' }))])

    for (const file of list) {
      const mark = (patch) =>
        setQueue((q) => q.map((row) => (row.name === file.name ? { ...row, ...patch } : row)))
      try {
        mark({ state: 'uploading' })
        await uploadFile(
          file,
          {
            folder: folder.trim(),
            tags: tags.split(',').map((t) => t.trim()).filter(Boolean)
          },
          (pct) => mark({ pct })
        )
        mark({ state: 'done', pct: 1 })
        onUploaded()
      } catch (err) {
        mark({ state: 'error', error: err.message })
      }
    }
    setTimeout(() => setQueue((q) => q.filter((r) => r.state !== 'done')), 4000)
  }, [folder, tags, onUploaded])

  return (
    <section className="upload">
      <div
        className={`dropzone ${dragging ? 'dragging' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); start(e.dataTransfer.files) }}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
      >
        <div className="dropzone-icon">&#8593;</div>
        <div>
          <strong>Drop recordings or video here</strong>
          <span className="muted"> or click to choose files</span>
        </div>
        <div className="muted small">
          Audio (mp3, wav, m4a, wma, ogg, flac) and video (mp4, mov, mkv, avi, wmv) &mdash;
          uploaded in 5 MB parts, so large files are safe
        </div>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPT}
          style={{ display: 'none' }}
          onChange={(e) => { start(e.target.files); e.target.value = '' }}
        />
      </div>

      <div className="upload-meta">
        <label>
          Folder
          <input
            list="folder-options"
            value={folder}
            placeholder="e.g. Meetings"
            onChange={(e) => setFolder(e.target.value)}
          />
          <datalist id="folder-options">
            {folders.map((f) => f.name && <option key={f.name} value={f.name} />)}
          </datalist>
        </label>
        <label>
          Tags
          <input
            value={tags}
            placeholder="comma, separated"
            onChange={(e) => setTags(e.target.value)}
          />
        </label>
      </div>

      {queue.length > 0 && (
        <ul className="upload-queue">
          {queue.map((row) => (
            <li key={row.name} className={row.state}>
              <span className="uq-name">{row.name}</span>
              <span className="muted small">{humanBytes(row.size)}</span>
              {row.state === 'error'
                ? <span className="badge failed">{row.error}</span>
                : <span className="uq-bar"><i style={{ width: `${Math.round(row.pct * 100)}%` }} /></span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
