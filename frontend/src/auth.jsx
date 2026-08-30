import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api } from './api.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [config, setConfig] = useState({ providers: {}, allow_signup: true })
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const [me, cfg] = await Promise.all([api.me(), api.authConfig()])
      setUser(me.user)
      setConfig(cfg)
    } catch {
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const value = {
    user,
    config,
    loading,
    refresh,
    setUser,
    isAdmin: !!user && (user.role === 'ADMIN' || user.role === 'GOD'),
    isGod: !!user && user.role === 'GOD',
    logout: async () => {
      await api.logout().catch(() => {})
      setUser(null)
    }
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
