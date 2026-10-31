import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, setUnauthorizedHandler, tokenStore } from './api'
import type { User } from './types'

interface AuthState {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<User>
  register: (data: { full_name: string; email: string; password: string; company?: string; phone?: string }) => Promise<User>
  logout: () => Promise<void>
  setSession: (token: string, user: User) => void
  isInternal: boolean
  isAdmin: boolean
}

const Ctx = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const clear = useCallback(() => { tokenStore.clear(); setUser(null) }, [])

  useEffect(() => {
    setUnauthorizedHandler(clear)
    if (!tokenStore.get()) { setLoading(false); return }
    api<User>('/auth/me').then(setUser).catch(clear).finally(() => setLoading(false))
  }, [clear])

  const setSession = useCallback((token: string, u: User) => { tokenStore.set(token); setUser(u) }, [])

  const value = useMemo<AuthState>(() => ({
    user, loading, setSession,
    login: async (email, password) => {
      const r = await api<{ access_token: string; user: User }>('/auth/login', { body: { email, password } })
      setSession(r.access_token, r.user)
      return r.user
    },
    register: async (data) => {
      const r = await api<{ access_token: string; user: User }>('/auth/register', { body: data })
      setSession(r.access_token, r.user)
      return r.user
    },
    logout: async () => { try { await api('/auth/logout', { method: 'POST' }) } catch { /* already invalid */ } clear() },
    isInternal: user?.role === 'admin' || user?.role === 'staff',
    isAdmin: user?.role === 'admin',
  }), [user, loading, setSession, clear])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth() {
  const c = useContext(Ctx)
  if (!c) throw new Error('useAuth outside AuthProvider')
  return c
}

export const PASSWORD_RULES = [
  { label: 'More than 8 characters', test: (p: string) => p.length > 8 },
  { label: 'An uppercase letter', test: (p: string) => /[A-Z]/.test(p) },
  { label: 'A lowercase letter', test: (p: string) => /[a-z]/.test(p) },
  { label: 'A special character', test: (p: string) => /[^A-Za-z0-9]/.test(p) },
]
