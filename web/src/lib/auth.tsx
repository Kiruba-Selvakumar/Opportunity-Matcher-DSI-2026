import { createContext, useCallback, useContext, useEffect, useMemo, type ReactNode } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { ApiError, get, post, setCsrf, setUnauthorizedHandler } from './api'
import type { AuthUser, Role } from './types'
import { Spinner } from '../components/ui'

interface Me { user: AuthUser; csrf: string }

interface AuthCtx {
  user: AuthUser | null
  loading: boolean
  signIn: (username: string, password: string) => Promise<AuthUser>
  demoSignIn: (username: string) => Promise<AuthUser>
  signOut: () => Promise<void>
  refresh: () => Promise<void>
}

const Ctx = createContext<AuthCtx | null>(null)

export function useAuthMode(): { demo: boolean; ready: boolean } {
  const q = useQuery({ queryKey: ['mode'], queryFn: () => get<{ demo: boolean }>('/api/auth/mode'), staleTime: 300_000 })
  return { demo: q.data?.demo === true, ready: !q.isLoading }
}

export function useDemoMode(): boolean {
  return useAuthMode().demo
}

export const HOME: Record<Role, string> = { ngo_admin: '/ngo', ngo_staff: '/ngo', student: '/student', employer: '/employer' }
export const ROLE_WORD: Record<Role, string> = { ngo_admin: 'NGO admin', ngo_staff: 'NGO staff', student: 'Student', employer: 'Employer' }

/** Forget everything that was loaded for the last person, but keep the query that holds who is signed in. */
function forgetEverythingExceptMe(qc: QueryClient) {
  qc.removeQueries({ predicate: (q) => q.queryKey[0] !== 'me' })
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const me = useQuery({
    queryKey: ['me'],
    queryFn: async () => {
      try { const m = await get<Me>('/api/auth/me'); setCsrf(m.csrf); return m }
      catch (e) { if (e instanceof ApiError && e.status === 401) return null; throw e }
    },
    staleTime: 60_000,
  })

  // when the server says the session is gone, forget everything that was loaded for that person
  useEffect(() => {
    setUnauthorizedHandler(() => { setCsrf(''); forgetEverythingExceptMe(qc); qc.setQueryData(['me'], null) })
    return () => setUnauthorizedHandler(null)
  }, [qc])

  const signIn = useCallback(async (username: string, password: string) => {
    const m = await post<Me>('/api/auth/login', { username, password })
    setCsrf(m.csrf)
    forgetEverythingExceptMe(qc)
    qc.setQueryData(['me'], m)
    return m.user
  }, [qc])

  const demoSignIn = useCallback(async (username: string) => {
    const m = await post<Me>('/api/auth/demo-login', { username })
    setCsrf(m.csrf)
    forgetEverythingExceptMe(qc)
    qc.setQueryData(['me'], m)
    return m.user
  }, [qc])

  const signOut = useCallback(async () => {
    try { await post('/api/auth/logout', {}) } catch { /* the session may already be gone */ }
    setCsrf('')
    forgetEverythingExceptMe(qc)
    qc.setQueryData(['me'], null)
  }, [qc])

  const refresh = useCallback(async () => { await qc.invalidateQueries({ queryKey: ['me'] }) }, [qc])

  const value = useMemo<AuthCtx>(() => ({ user: me.data?.user ?? null, loading: me.isLoading, signIn, demoSignIn, signOut, refresh }),
    [me.data, me.isLoading, signIn, demoSignIn, signOut, refresh])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth(): AuthCtx {
  const c = useContext(Ctx)
  if (!c) throw new Error('useAuth must be used inside AuthProvider')
  return c
}

/** Sends people who are not signed in to /login, people who must change their password to /account, and shows a plain message to the wrong role. */
export function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user, loading } = useAuth()
  const loc = useLocation()
  if (loading) return <div className="p-8"><Spinner text="Checking your sign-in" /></div>
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname + loc.search }} />
  if (user.must_change_password) return <Navigate to="/account" replace />
  if (!roles.includes(user.role)) {
    return (
      <div className="mx-auto max-w-md px-8 py-24 text-center">
        <h1>No access</h1>
        <p className="mt-3 text-base text-ink-soft">You do not have access to this area with your account.</p>
        <Link to={HOME[user.role]} className="btn btn-primary mt-6">Go to your area</Link>
      </div>
    )
  }
  return <>{children}</>
}
