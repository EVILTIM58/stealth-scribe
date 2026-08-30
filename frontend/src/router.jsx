import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'

// A ~40 line router instead of react-router-dom. Stealth-Scribe has a dozen flat
// routes and no nesting, and every dependency is something that can break a
// build we cannot rehearse locally.

const RouteContext = createContext({ path: '/', query: {}, navigate: () => {} })

function read() {
  return {
    path: window.location.pathname || '/',
    query: Object.fromEntries(new URLSearchParams(window.location.search))
  }
}

export function RouterProvider({ children }) {
  const [route, setRoute] = useState(read)

  useEffect(() => {
    const onPop = () => setRoute(read())
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const navigate = useCallback((to, { replace = false } = {}) => {
    if (to === window.location.pathname + window.location.search) return
    window.history[replace ? 'replaceState' : 'pushState']({}, '', to)
    setRoute(read())
    window.scrollTo(0, 0)
  }, [])

  return (
    <RouteContext.Provider value={{ ...route, navigate }}>
      {children}
    </RouteContext.Provider>
  )
}

export function useRoute() {
  return useContext(RouteContext)
}

/** Anchor that navigates without a full page reload, but is still a real
 *  <a href> — so crawlers, middle-click and "open in new tab" all work. */
export function Link({ to, children, className, onClick, ...rest }) {
  const { navigate } = useRoute()
  return (
    <a
      href={to}
      className={className}
      onClick={(e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return
        e.preventDefault()
        onClick?.(e)
        navigate(to)
      }}
      {...rest}
    >
      {children}
    </a>
  )
}
