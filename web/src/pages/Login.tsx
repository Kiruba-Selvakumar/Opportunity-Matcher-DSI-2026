import { useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { LogIn } from 'lucide-react'
import { ApiError } from '../lib/api'
import { useQuery } from '@tanstack/react-query'
import { get } from '../lib/api'
import { HOME, ROLE_WORD, useAuth, useAuthMode } from '../lib/auth'
import type { Role } from '../lib/types'
import { Banner } from '../components/ui'
import { Mark } from '../components/MapleMark'

export default function Login() {
  const { user, signIn, demoSignIn, loading } = useAuth()
  const { demo, ready } = useAuthMode()
  const people = useQuery({ queryKey: ['demo-users'], queryFn: () => get<{ username: string; display_name: string; role: Role; linked: string }[]>('/api/auth/demo-users'), enabled: demo })
  const [pick, setPick] = useState('')
  const nav = useNavigate()
  const loc = useLocation()
  const from = (loc.state as { from?: string } | null)?.from
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (!loading && user) return <Navigate to={user.must_change_password ? '/account' : HOME[user.role]} replace />

  const enter = async (e: FormEvent) => {
    e.preventDefault()
    if (!pick) { setError('Choose who to sign in as.'); return }
    setBusy(true); setError(null)
    try {
      const u = await demoSignIn(pick)
      nav(from && from.startsWith(HOME[u.role]) ? from : HOME[u.role], { replace: true })
    } catch (err) { setError(err instanceof Error ? err.message : 'Something went wrong. Try again.') } finally { setBusy(false) }
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password) { setError('Enter your username and password.'); return }
    setBusy(true); setError(null)
    try {
      const u = await signIn(username.trim(), password)
      nav(u.must_change_password ? '/account' : (from && from.startsWith('/' + HOME[u.role].slice(1)) ? from : HOME[u.role]), { replace: true })
    } catch (err) {
      setPassword('')
      setError(err instanceof ApiError ? (err.status === 0 ? err.message : err.message) : 'Something went wrong. Try again.')
    } finally { setBusy(false) }
  }

  return (
    <div className="min-h-screen">
      <header className="sky border-b border-line px-8 pb-10 pt-10">
        <div className="mx-auto max-w-md">
          <div className="flex items-center gap-2.5"><Mark className="h-8 w-8" /><span className="font-serif text-xl">Opportunity Matcher</span></div>
          <h1 className="mt-6">Sign in</h1>
          <p className="mt-2 text-base text-ink-soft">{demo ? 'Choose a person to try the app as.' : 'Use the username and password the NGO gave you.'}</p>
        </div>
      </header>
      <main className="mx-auto max-w-md px-8 py-8">
        {!ready ? (
          <div className="card p-6" role="status" aria-label="Loading"><div className="h-4 w-1/3 animate-pulse rounded bg-sunk" /><div className="mt-4 h-10 w-full animate-pulse rounded bg-sunk" /></div>
        ) : demo ? (
          <form onSubmit={enter} className="card settle space-y-4 p-6" noValidate>
            <Banner tone="amber" lead="Demo mode.">There are no passwords. Pick who you want to be.</Banner>
            <div>
              <label htmlFor="demo-user" className="label">Sign in as</label>
              <select id="demo-user" className="input !py-2.5 !text-base" value={pick} onChange={(e) => setPick(e.target.value)} autoFocus aria-invalid={!!error}>
                <option value="">Choose a person</option>
                {(['ngo_admin', 'ngo_staff', 'student', 'employer'] as Role[]).map((r) => {
                  const group = (people.data ?? []).filter((p) => p.role === r)
                  return group.length === 0 ? null : (
                    <optgroup key={r} label={ROLE_WORD[r]}>
                      {group.map((p) => <option key={p.username} value={p.username}>{p.display_name} ({p.username}{p.linked ? ` · ${p.linked}` : ''})</option>)}
                    </optgroup>
                  )
                })}
              </select>
            </div>
            {people.error && <p className="text-sm text-fail" role="alert">Could not load the people. Is the API running?</p>}
            {error && <p className="rounded-md border border-fail-line bg-fail-soft px-3 py-2 text-sm text-fail" role="alert">{error}</p>}
            <button type="submit" className="btn btn-primary w-full !py-2.5" disabled={busy}><LogIn className="h-4 w-4" aria-hidden />{busy ? 'Signing in' : 'Sign in'}</button>
          </form>
        ) : (
        <form onSubmit={submit} className="card settle space-y-4 p-6" noValidate>
          <div>
            <label htmlFor="username" className="label">Username</label>
            <input id="username" className="input !py-2.5 !text-base" value={username} onChange={(e) => setUsername(e.target.value)}
              autoComplete="username" autoCapitalize="none" spellCheck={false} autoFocus aria-invalid={!!error} />
          </div>
          <div>
            <label htmlFor="password" className="label">Password</label>
            <input id="password" type="password" className="input !py-2.5 !text-base" value={password} onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password" aria-invalid={!!error} aria-describedby={error ? 'login-error' : undefined} />
          </div>
          {error && <p id="login-error" className="rounded-md border border-fail-line bg-fail-soft px-3 py-2 text-sm text-fail" role="alert">{error}</p>}
          <button type="submit" className="btn btn-primary w-full !py-2.5" disabled={busy}><LogIn className="h-4 w-4" aria-hidden />{busy ? 'Signing in' : 'Sign in'}</button>
          <p className="text-xs text-ink-faint">Forgot your password? Ask your NGO admin to reset it.</p>
        </form>
        )}
      </main>
    </div>
  )
}
