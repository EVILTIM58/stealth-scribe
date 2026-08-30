import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import { useAuth } from '../auth.jsx'
import { Link, useRoute } from '../router.jsx'

function Shell({ title, subtitle, children, footer }) {
  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-brand">
          <img src="/ss-mark.webp" alt="" />
          <div>
            <div className="brand-name">Stealth-Scribe</div>
            <div className="muted small">Audio in. Transcribe to English. Save as PDF.</div>
          </div>
        </div>
        <h1>{title}</h1>
        {subtitle && <p className="muted auth-sub">{subtitle}</p>}
        {children}
        {footer && <div className="auth-footer">{footer}</div>}
      </div>
    </div>
  )
}

function Social({ providers, label, consent }) {
  if (!providers?.google && !providers?.facebook) return null
  return (
    <>
      {consent && (
        <div className="muted small consent-note">
          By continuing you accept the <Link to="/terms">Terms</Link> and{' '}
          <Link to="/privacy">Privacy Policy</Link>, and confirm you have the right
          to upload the recordings you process.
        </div>
      )}
      <div className="social">
        {providers.google && (
          <a className="btn ghost social-btn" href={api.oauthUrl('google')}>
            <span className="social-g">G</span> {label} with Google
          </a>
        )}
        {providers.facebook && (
          <a className="btn ghost social-btn" href={api.oauthUrl('facebook')}>
            <span className="social-f">f</span> {label} with Facebook
          </a>
        )}
      </div>
      <div className="or"><span>or</span></div>
    </>
  )
}

/* ------------------------------------------------------------------ login */
export function LoginPage() {
  const { config, refresh } = useAuth()
  const { navigate, query } = useRoute()
  const [form, setForm] = useState({ email: '', password: '' })
  const [error, setError] = useState(query.error || '')
  const [busy, setBusy] = useState(false)
  const [needsVerify, setNeedsVerify] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError(''); setNeedsVerify(false)
    try {
      await api.login(form)
      await refresh()
      navigate('/')
    } catch (err) {
      setError(err.message)
      if (/confirm your email/i.test(err.message)) setNeedsVerify(true)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Shell
      title="Sign in"
      subtitle="Your recordings are private to your account."
      footer={
        config.allow_signup && (
          <>No account? <Link to="/signup">Create one</Link></>
        )
      }
    >
      <Social providers={config.providers} label="Continue" consent />
      <form onSubmit={submit} className="auth-form">
        <label>Email
          <input type="email" required autoComplete="email" value={form.email}
                 onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </label>
        <label>Password
          <input type="password" required autoComplete="current-password" value={form.password}
                 onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </label>
        {error && <div className="rec-error">{error}</div>}
        {needsVerify && (
          <button type="button" className="link"
                  onClick={() => api.resendVerification(form.email).then(
                    () => setError('A new confirmation link is on its way.'))}>
            Resend the confirmation email
          </button>
        )}
        <button className="btn" disabled={busy}>{busy ? 'Signing in...' : 'Sign in'}</button>
        <Link to="/forgot" className="link small">Forgot your password?</Link>
      </form>
    </Shell>
  )
}

/* ----------------------------------------------------------------- signup */
export function SignupPage() {
  const { config, refresh } = useAuth()
  const { navigate } = useRoute()
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [accepted, setAccepted] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      const res = await api.signup({ ...form, accept_terms: accepted })
      setDone(res)
      await refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (done) {
    return (
      <Shell title="Check your email"
             subtitle={done.message}
             footer={<Link to="/login">Back to sign in</Link>}>
        <p className="muted">
          We sent a confirmation link to <strong>{form.email}</strong>. It's good for
          24 hours. If it doesn't arrive, check spam.
        </p>
      </Shell>
    )
  }

  if (!config.allow_signup) {
    return (
      <Shell title="Registration is closed"
             footer={<Link to="/login">Back to sign in</Link>}>
        <p className="muted">This server isn't accepting new accounts right now.</p>
      </Shell>
    )
  }

  return (
    <Shell title="Create your account"
           subtitle="Free. Your recordings stay private to you."
           footer={<>Already registered? <Link to="/login">Sign in</Link></>}>
      <Social providers={config.providers} label="Sign up" consent />
      <form onSubmit={submit} className="auth-form">
        <label>Name
          <input value={form.name} autoComplete="name" placeholder="What should we call you?"
                 onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </label>
        <label>Email
          <input type="email" required autoComplete="email" value={form.email}
                 onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </label>
        <label>Password
          <input type="password" required autoComplete="new-password" minLength={10}
                 value={form.password}
                 onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </label>
        <div className="muted small">At least 10 characters. A short phrase beats a clever word.</div>
        <label className="checkbox consent">
          <input type="checkbox" checked={accepted}
                 onChange={(e) => setAccepted(e.target.checked)} />
          <span>
            I will only upload recordings I have the legal right to make and to
            have transcribed, and I accept the <Link to="/terms">Terms</Link> and{' '}
            <Link to="/privacy">Privacy Policy</Link>.
          </span>
        </label>
        {error && <div className="rec-error">{error}</div>}
        <button className="btn" disabled={busy || !accepted}>
          {busy ? 'Creating...' : 'Create account'}
        </button>
      </form>
    </Shell>
  )
}

/* ----------------------------------------------------------------- verify */
export function VerifyPage() {
  const { query, navigate } = useRoute()
  const { refresh } = useAuth()
  const [state, setState] = useState('working')
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    if (!query.token) { setState('error'); setError('This link is missing its token.'); return }
    api.verify(query.token)
      .then(async () => {
        if (cancelled) return
        await refresh()
        setState('done')
        setTimeout(() => navigate('/'), 1200)
      })
      .catch((err) => { if (!cancelled) { setState('error'); setError(err.message) } })
    return () => { cancelled = true }
  }, [query.token, refresh, navigate])

  return (
    <Shell title={state === 'done' ? 'You’re in' : 'Confirming your email'}
           footer={state === 'error' && <Link to="/login">Back to sign in</Link>}>
      {state === 'working' && <div className="pulse-eye" />}
      {state === 'done' && <p className="muted">Address confirmed. Taking you to your library...</p>}
      {state === 'error' && <div className="rec-error">{error}</div>}
    </Shell>
  )
}

/* ----------------------------------------------------------- forgot/reset */
export function ForgotPage() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    await api.forgot(email).catch(() => {})
    setSent(true); setBusy(false)
  }

  return (
    <Shell title="Reset your password"
           subtitle={sent ? '' : 'We’ll email you a link to choose a new one.'}
           footer={<Link to="/login">Back to sign in</Link>}>
      {sent ? (
        <p className="muted">
          If <strong>{email}</strong> has an account, a reset link is on its way.
          It expires in an hour.
        </p>
      ) : (
        <form onSubmit={submit} className="auth-form">
          <label>Email
            <input type="email" required autoComplete="email" value={email}
                   onChange={(e) => setEmail(e.target.value)} />
          </label>
          <button className="btn" disabled={busy}>{busy ? 'Sending...' : 'Send reset link'}</button>
        </form>
      )}
    </Shell>
  )
}

export function ResetPage() {
  const { query, navigate } = useRoute()
  const { refresh } = useAuth()
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      await api.resetPassword(query.token, password)
      await refresh()
      navigate('/')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Shell title="Choose a new password"
           subtitle="This also signs you out everywhere else."
           footer={<Link to="/login">Back to sign in</Link>}>
      <form onSubmit={submit} className="auth-form">
        <label>New password
          <input type="password" required minLength={10} autoComplete="new-password"
                 value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && <div className="rec-error">{error}</div>}
        <button className="btn" disabled={busy}>{busy ? 'Saving...' : 'Set password'}</button>
      </form>
    </Shell>
  )
}
