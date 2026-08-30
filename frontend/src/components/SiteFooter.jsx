import React from 'react'
import { Link } from '../router.jsx'
import { SITE } from '../config/siteMeta.js'
import { APP_VERSION } from '../config/version.js'

export default function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="footer-inner">
        <div className="footer-brand">
          <img src="/ss-mark.webp" alt="" />
          <div>
            <div className="brand-name">Stealth-Scribe</div>
            <div className="muted small">{SITE.tagline}</div>
          </div>
        </div>

        <nav className="footer-links">
          <Link to="/about">About</Link>
          <Link to="/contact">Contact</Link>
          <Link to="/privacy">Privacy</Link>
          <Link to="/terms">Terms</Link>
          <Link to="/guidelines">Community Guidelines</Link>
          <Link to="/dmca">DMCA</Link>
          <Link to="/changelog">Changelog</Link>
        </nav>

        <div className="footer-legal muted small">
          <div>&copy; {new Date().getFullYear()} {SITE.operator}. All rights reserved.</div>
          <div>
            You must be at least {SITE.minimumAge} to use this service. Only upload
            recordings you have the right to record and transcribe.
          </div>
          <div>Version {APP_VERSION}</div>
        </div>
      </div>
    </footer>
  )
}
