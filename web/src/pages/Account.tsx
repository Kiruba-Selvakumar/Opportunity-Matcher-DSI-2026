import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Mail, MonitorSmartphone } from 'lucide-react'
import { ApiError, get, post, put } from '../lib/api'
import { useConfirm } from '../components/Confirm'
import { useToast } from '../components/Toast'
import type { AuthUser, SessionRow } from '../lib/types'
import { HOME, ROLE_WORD, useAuth } from '../lib/auth'
import { Banner, Spinner } from '../components/ui'
import { Mark } from '../components/MapleMark'

export default function Account() {
  const { user, loading, refresh, signOut } = useAuth()
  const nav = useNavigate()
  const qc = useQueryClient()
  const confirm = useConfirm()
  const toast = useToast()
  const sessions = useQuery({ queryKey: ['sessions'], queryFn: () => get<SessionRow[]>('/api/auth/sessions'), enabled: !!user && !user.must_change_password })
  const revoke = useMutation({
    mutationFn: () => post<{ revoked: number }>('/api/auth/sessions/revoke-others', {}),
    onSuccess: (r) => { toast(r.revoked ? `Signed out of ${r.revoked} other place${r.revoked === 1 ? '' : 's'}.` : 'You are not signed in anywhere else.'); qc.invalidateQueries({ queryKey: ['sessions'] }) },
  })
  const signOutOthers = async () => { if (await confirm({ title: 'Sign out everywhere else?', body: 'Every other phone or computer signed in as you will be signed out. This one stays signed in.', confirmLabel: 'Sign out the others' })) revoke.mutate() }
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [again, setAgain] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)

  if (loading) return <div className="p-8"><Spinner /></div>
  if (!user) return <Navigate to="/login" replace />

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null); setDone(false)
    if (next !== again) { setError('The two new passwords are not the same.'); return }
    setBusy(true)
    try {
      await post('/api/auth/change-password', { current, new: next })
      setCurrent(''); setNext(''); setAgain(''); setDone(true)
      await refresh()
      if (user.must_change_password) nav(HOME[user.role], { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.')
    } finally { setBusy(false) }
  }

  return (
    <div className="min-h-screen">
      <header className="sky border-b border-line px-8 pb-10 pt-10">
        <div className="mx-auto max-w-md">
          <div className="flex items-center gap-2.5"><Mark className="h-8 w-8" /><span className="font-serif text-xl">Opportunity Matcher</span></div>
          <h1 className="mt-6">Your account</h1>
          <p className="mt-2 text-base text-ink-soft">{user.display_name} · {ROLE_WORD[user.role]} · <span className="font-mono text-sm">{user.username}</span></p>
        </div>
      </header>
      <main className="mx-auto max-w-md space-y-4 px-8 py-8">
        {user.must_change_password && <Banner tone="amber" lead="Choose a new password to continue.">The password you were given is only for your first sign-in.</Banner>}
        <form onSubmit={submit} className="card space-y-4 p-6" noValidate>
          <h2>Change your password</h2>
          <div><label className="label" htmlFor="cur">Current password</label>
            <input id="cur" type="password" className="input" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} /></div>
          <div><label className="label" htmlFor="new">New password</label>
            <input id="new" type="password" className="input" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} aria-describedby="rules" />
            <p id="rules" className="mt-1 text-xs text-ink-faint">At least 10 characters. A few words in a row make a good password. Common passwords are not allowed.</p></div>
          <div><label className="label" htmlFor="again">New password again</label>
            <input id="again" type="password" className="input" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} /></div>
          {error && <p className="rounded-md border border-fail-line bg-fail-soft px-3 py-2 text-sm text-fail" role="alert">{error}</p>}
          {done && <p className="rounded-md border border-pass-line bg-pass-soft px-3 py-2 text-sm text-pass" role="status">Your password was changed. Your other sign-ins were signed out.</p>}
          <button type="submit" className="btn btn-primary" disabled={busy || !current || !next || !again}>{busy ? 'Saving' : 'Change password'}</button>
        </form>
        {!user.must_change_password && user.role !== 'student' && <EmailForm user={user} onSaved={refresh} />}
        {!user.must_change_password && sessions.data && (
          <section className="card space-y-3 p-6" aria-labelledby="sess-h">
            <h2 id="sess-h" className="flex items-center gap-2"><MonitorSmartphone className="h-4 w-4 text-ink-soft" aria-hidden />Where you are signed in</h2>
            <ul className="divide-y divide-line text-sm">
              {sessions.data.map((s, i) => (
                <li key={i} className="flex items-center justify-between gap-3 py-2">
                  <span>{s.current ? <strong>This device</strong> : 'Another device'}<span className="block text-xs text-ink-faint">Signed in {s.created_at.replace('T', ' ').slice(0, 16)}. Last used {s.last_seen_at.replace('T', ' ').slice(0, 16)}{s.ip ? ` from ${s.ip}` : ''}.</span></span>
                </li>
              ))}
            </ul>
            {sessions.data.length > 1 && <button type="button" className="btn" onClick={signOutOthers} disabled={revoke.isPending}>Sign out of all other devices</button>}
          </section>
        )}
        <div className="flex items-center justify-between">
          {!user.must_change_password
            ? <Link to={HOME[user.role]} className="inline-flex items-center gap-1.5 text-sm text-ink-soft hover:text-ink"><ArrowLeft className="h-4 w-4" aria-hidden />Back to my area</Link>
            : <span />}
          <button type="button" className="btn btn-quiet" onClick={async () => { await signOut(); nav('/login', { replace: true }) }}>Sign out</button>
        </div>
      </main>
    </div>
  )
}

/** NGO and employer accounts set where emails about listings, candidates and interviews go. */
function EmailForm({ user, onSaved }: { user: AuthUser; onSaved: () => Promise<void> }) {
  const toast = useToast()
  const [v, setV] = useState(user.email ?? '')
  const save = useMutation({
    mutationFn: () => put('/api/auth/email', { email: v.trim() || null }),
    onSuccess: async () => { toast(v.trim() ? 'Email saved.' : 'Email removed.'); await onSaved() },
    onError: (e) => toast((e as Error).message, 'fail'),
  })
  return (
    <form className="card space-y-3 p-6" onSubmit={(e) => { e.preventDefault(); save.mutate() }}>
      <h2 className="flex items-center gap-2"><Mail className="h-4 w-4 text-ink-soft" aria-hidden />Your email</h2>
      <p className="text-sm text-ink-soft">{user.role === 'employer' ? 'We email you when a listing is approved, when the NGO shares a candidate, and when an interview is set.' : 'Interview invites go here when you take an interview.'}</p>
      <div><label className="label" htmlFor="acc-email">Email</label>
        <input id="acc-email" type="email" className="input" autoComplete="email" value={v} onChange={(e) => setV(e.target.value)} /></div>
      <button type="submit" className="btn" disabled={save.isPending || v.trim() === (user.email ?? '')}>Save email</button>
    </form>
  )
}
