import React from 'react'
import { Link } from '../router.jsx'
import { SITE } from '../config/siteMeta.js'

const FEATURES = [
  {
    key: 'transcribe',
    title: 'Every word, written down',
    body: 'Upload audio or video and get a full transcript. Timestamps on every turn, ' +
          'so you can always find the moment something was said.'
  },
  {
    key: 'speakers',
    title: 'Who said what',
    body: 'Stealth-Scribe separates the voices in a conversation and labels each turn. ' +
          'Rename Voice 1 to a real name and it updates the whole transcript.'
  },
  {
    key: 'summary',
    title: 'The point, up front',
    body: 'A written summary at the top of every transcript, plus key points, ' +
          'action items, and the questions that were raised.'
  },
  {
    key: 'search',
    title: 'Search everything you ever recorded',
    body: 'Find the phrase you half-remember across every recording you own, ' +
          'then click the result to hear exactly that moment.'
  },
  {
    key: 'record',
    title: 'Record on the spot',
    body: 'Capture straight from your phone or desktop microphone. It uploads and ' +
          'transcribes itself, no separate recorder app required.'
  },
  {
    key: 'private',
    title: 'Private by default',
    body: 'Your recordings are visible only to you. Nothing is sold, mined or used ' +
          'to train models. And you can erase everything — recordings, transcripts, ' +
          'account and all — instantly, without asking anyone.'
  }
]

const STEPS = [
  ['Capture it', 'Upload a file from your voice recorder, drop in a video, or hit Record.'],
  ['Convert it', 'Speech recognition writes it all down and works out who was speaking.'],
  ['Get to the point', 'Read the summary, skim the key points, check the action items.'],
  ['Keep it', 'Search it later, or download the plain .txt and take it with you.']
]

export default function Landing() {
  return (
    <div className="landing">
      <section className="hero">
        {/* The mark, not the full logo: the full artwork already contains the
            wordmark and taglines, which would then read twice on the page. */}
        <img src="/ss-mark.webp" alt="" className="hero-logo" />
        <h1 className="hero-title">Stealth-Scribe</h1>
        <p className="hero-tagline">{SITE.tagline}</p>
        <p className="hero-strap">{SITE.strapline}</p>
        <p className="hero-lede">
          Turn any recording into a transcript you can actually read, search and act
          on &mdash; with every speaker labelled and the point summarised up front.
        </p>
        <div className="hero-cta">
          <Link to="/signup" className="btn">Create a free account</Link>
          <Link to="/login" className="btn ghost">Sign in</Link>
        </div>
        <div className="muted small hero-note">
          From sound to clarity. In seconds.
        </div>
      </section>

      <section className="features">
        <h2 className="section-heading">What it does</h2>
        <div className="feature-grid">
          {FEATURES.map((f) => (
            <div className="feature" key={f.key}>
              <h3>{f.title}</h3>
              <p className="muted">{f.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="steps">
        <h2 className="section-heading">How it works</h2>
        <ol className="step-list">
          {STEPS.map(([title, body], i) => (
            <li key={title}>
              <span className="step-n">{String(i + 1).padStart(2, '0')}</span>
              <div>
                <h3>{title}</h3>
                <p className="muted">{body}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="landing-formats">
        <h2 className="section-heading">Works with what you already have</h2>
        <p className="muted">
          Audio: mp3, wav, m4a, wma, ogg, flac, aac, opus, amr.
          Video: mp4, mov, mkv, avi, wmv, webm &mdash; the audio track is pulled out
          automatically and the video stays playable alongside the transcript.
        </p>
      </section>

      <section className="landing-cta">
        <h2>Stop re-listening to your own recordings.</h2>
        <Link to="/signup" className="btn">Get started &mdash; it&rsquo;s free</Link>
        <p className="muted small">
          By signing up you agree to our <Link to="/terms">Terms</Link> and{' '}
          <Link to="/privacy">Privacy Policy</Link>. You must be {SITE.minimumAge} or older.
          Only upload recordings you have the right to record.
        </p>
      </section>
    </div>
  )
}
