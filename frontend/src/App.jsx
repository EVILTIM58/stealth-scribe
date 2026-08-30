import React from 'react'
import { useAuth } from './auth.jsx'
import { useRoute, Link } from './router.jsx'
import SiteFooter from './components/SiteFooter.jsx'
import Landing from './pages/Landing.jsx'
import Library from './pages/Library.jsx'
import AdminPage from './pages/Admin.jsx'
import AccountPage from './pages/Account.jsx'
import PeoplePage from './pages/People.jsx'
import { LoginPage, SignupPage, VerifyPage, ForgotPage, ResetPage } from './pages/Auth.jsx'
import {
  AboutPage, PrivacyPage, TermsPage, GuidelinesPage, DmcaPage, ContactPage, ChangelogPage
} from './pages/Legal.jsx'

// Reachable whether or not you're signed in. Google needs to crawl these, and
// somebody deciding whether to sign up needs to read them first.
const PUBLIC_PAGES = {
  '/about': AboutPage,
  '/privacy': PrivacyPage,
  '/terms': TermsPage,
  '/guidelines': GuidelinesPage,
  '/dmca': DmcaPage,
  '/contact': ContactPage,
  '/changelog': ChangelogPage
}

const AUTH_PAGES = {
  '/login': LoginPage,
  '/signup': SignupPage,
  '/verify': VerifyPage,
  '/forgot': ForgotPage,
  '/reset': ResetPage
}

function Chrome({ children, footer = true }) {
  return (
    <div className="page">
      <div className="page-body">{children}</div>
      {footer && <SiteFooter />}
    </div>
  )
}

function NotFound() {
  return (
    <div className="empty">
      <img src="/ss-mark.webp" alt="" className="empty-mark" />
      <h3>Nothing here</h3>
      <p className="muted">That page doesn&rsquo;t exist.</p>
      <Link to="/" className="btn">Go home</Link>
    </div>
  )
}

export default function App() {
  const { user, loading, isAdmin } = useAuth()
  const { path } = useRoute()

  if (loading) {
    return <div className="boot-screen"><div className="pulse-eye" /></div>
  }

  const Public = PUBLIC_PAGES[path]
  if (Public) return <Chrome><Public /></Chrome>

  const Auth = AUTH_PAGES[path]
  if (Auth) {
    // Already signed in? The only auth page still worth showing is /verify,
    // which finishes a flow the user is mid-way through.
    if (user && path !== '/verify') {
      window.history.replaceState({}, '', '/')
      return <Library />
    }
    return <Chrome><Auth /></Chrome>
  }

  if (!user) {
    // Signed out at any app route -> the public homepage, which is also the
    // page Google indexes.
    return <Chrome><Landing /></Chrome>
  }

  if (path === '/admin') {
    return isAdmin
      ? <Chrome footer={false}><AdminPage /></Chrome>
      : <Chrome><div className="empty">
          <h3>Admins only</h3>
          <p className="muted">You don&rsquo;t have access to that area.</p>
          <Link to="/" className="btn">Back to your library</Link>
        </div></Chrome>
  }

  if (path === '/account') return <Chrome footer={false}><AccountPage /></Chrome>
  if (path === '/people') return <Chrome footer={false}><PeoplePage /></Chrome>
  if (path === '/' || path === '/library') return <Library />

  return <Chrome><NotFound /></Chrome>
}
