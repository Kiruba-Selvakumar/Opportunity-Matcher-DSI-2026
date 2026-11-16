import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Copy, KeyRound, UserPlus } from 'lucide-react'
import { get, patch, post } from '../../lib/api'
import { ROLE_WORD, useAuth } from '../../lib/auth'
import type { AuthUser, Role } from '../../lib/types'
import { Badge, Banner, Empty, ErrorState, Fold, PageHeader, Spinner } from '../../components/ui'

interface Created { user: AuthUser; temporary_password: string | null }

const ROLES: Role[] = ['student', 'employer', 'ngo_staff', 'ngo_admin']

export default function AdminUsers() {
  const { user: me } = useAuth()
  const qc = useQueryClient()
  const users = useQuery({ queryKey: ['admin-users'], queryFn: () => get<AuthUser[]>('/api/admin/users') })
  const [shown, setShown] = useState<{ who: string; password: string } | null>(null)
  const [form, setForm] = useState({ username: '', display_name: '', role: 'student' as Role, student_id: '', listings: '', email: '' })
  const [formError, setFormError] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<number | null>(null)
  const [copied, setCopied] = useState(false)
  const refresh = () => qc.invalidateQueries({ queryKey: ['admin-users'] })

  const create = useMutation({
    mutationFn: () => post<Created>('/api/admin/users', {
      username: form.username.trim(), display_name: form.display_name.trim(), role: form.role,
      student_id: form.role === 'student' ? form.student_id.trim().toUpperCase() : null,
      listings: form.role === 'employer' ? form.listings.split(/[\s,]+/).filter(Boolean).map((x) => x.toUpperCase()) : [],
      email: form.role === 'student' ? null : form.email.trim() || null,
    }),
    onSuccess: (r) => {
      setShown({ who: r.user.username, password: r.temporary_password ?? '' }); setFormError(null); setCopied(false)
      setForm({ username: '', display_name: '', role: form.role, student_id: '', listings: '', email: '' }); refresh()
    },
    onError: (e) => setFormError((e as Error).message),
  })
  const toggle = useMutation({ mutationFn: (u: AuthUser) => patch(`/api/admin/users/${u.id}`, { is_active: !u.is_active }), onSuccess: refresh })
  const reset = useMutation({
    mutationFn: (u: AuthUser) => post<{ temporary_password: string }>(`/api/admin/users/${u.id}/reset-password`, {}).then((r) => ({ u, r })),
    onSuccess: ({ u, r }) => { setShown({ who: u.username, password: r.temporary_password }); setConfirm(null); setCopied(false); refresh() },
  })

  const submit = (e: FormEvent) => { e.preventDefault(); create.mutate() }
  const copy = async () => { if (shown) { await navigator.clipboard.writeText(shown.password); setCopied(true) } }
  const linked = (u: AuthUser) => u.role === 'student' ? u.student_id : u.role === 'employer' ? u.listings.join(', ') : ''

  return (
    <>
      <PageHeader title="Accounts" sub="Make accounts for staff, students and employers, turn them off when someone leaves, and reset a password when someone is locked out. Only admins see this page." />
      <div className="space-y-6 px-8 py-6">
        {shown && (
          <Banner tone="pass" lead={`Temporary password for ${shown.who}:`}>
            <code className="mx-1 rounded bg-surface px-1.5 py-0.5 font-mono text-sm">{shown.password}</code>
            <button type="button" className="btn btn-quiet ml-1 !py-0.5" onClick={copy}><Copy className="h-3.5 w-3.5" aria-hidden />{copied ? 'Copied' : 'Copy'}</button>
            <span className="block text-xs">This is shown once. Give it to them safely. They must choose their own password on first sign-in.</span>
          </Banner>
        )}

        <Fold title="Add an account" defaultOpen right={<UserPlus className="h-4 w-4 text-ink-soft" aria-hidden />}>
          <form onSubmit={submit} className="grid gap-4 md:grid-cols-2" noValidate>
            <div><label className="label" htmlFor="u-name">Username</label>
              <input id="u-name" className="input" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} autoComplete="off" placeholder="for example ravi.k" />
              <p className="mt-1 text-xs text-ink-faint">3 to 32 letters, numbers, dots, dashes or underscores.</p></div>
            <div><label className="label" htmlFor="u-disp">Display name</label>
              <input id="u-disp" className="input" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} autoComplete="off" /></div>
            <div><label className="label" htmlFor="u-role">Role</label>
              <select id="u-role" className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
                {ROLES.map((r) => <option key={r} value={r}>{ROLE_WORD[r]}</option>)}</select></div>
            {form.role === 'student' && <div><label className="label" htmlFor="u-sid">Student ID</label>
              <input id="u-sid" className="input font-mono" value={form.student_id} onChange={(e) => setForm({ ...form, student_id: e.target.value })} placeholder="S001" autoComplete="off" /></div>}
            {form.role === 'employer' && <div><label className="label" htmlFor="u-list">Listing IDs (optional)</label>
              <input id="u-list" className="input font-mono" value={form.listings} onChange={(e) => setForm({ ...form, listings: e.target.value })} placeholder="J028, J027" autoComplete="off" /></div>}
            {form.role !== 'student' && <div><label className="label" htmlFor="u-email">Email (optional)</label>
              <input id="u-email" type="email" className="input" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} autoComplete="off" placeholder="hr@company.com" />
              <p className="mt-1 text-xs text-ink-faint">{form.role === 'employer' ? 'Approvals, shared candidates and interview invites go here.' : 'Interview invites go here when this person interviews.'}</p></div>}
            <div className="md:col-span-2">
              {formError && <p className="mb-3 rounded-md border border-fail-line bg-fail-soft px-3 py-2 text-sm text-fail" role="alert">{formError}</p>}
              <button type="submit" className="btn btn-primary" disabled={create.isPending || !form.username || !form.display_name}>{create.isPending ? 'Creating' : 'Create account'}</button>
            </div>
          </form>
        </Fold>

        {users.isLoading && <Spinner />}
        {users.error && <ErrorState error={users.error} onRetry={() => users.refetch()} />}
        {users.data?.length === 0 && <Empty title="No accounts">Add the first one above.</Empty>}
        {users.data && users.data.length > 0 && (
          <div className="card pop overflow-x-auto">
            <table className="w-full border-collapse">
              <thead><tr>{['Username', 'Name', 'Role', 'Linked to', 'Email', 'Status', 'Last sign-in', ''].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
              <tbody>
                {users.data.map((u) => (
                  <tr key={u.id} className="hover:bg-[#f6f0e3]">
                    <td className="td font-mono text-xs">{u.username}{u.id === me?.id && <Badge tone="sky" className="ml-1.5">you</Badge>}</td>
                    <td className="td">{u.display_name}</td>
                    <td className="td">{ROLE_WORD[u.role]}</td>
                    <td className="td font-mono text-xs">{linked(u)}</td>
                    <td className="td">{u.role === 'student' ? <span className="text-xs text-ink-faint">in the contact list</span> : <EmailCell u={u} onSaved={refresh} />}</td>
                    <td className="td whitespace-nowrap">
                      {u.is_active ? <Badge tone="pass">Active</Badge> : <Badge tone="neutral">Off</Badge>}
                      {u.locked && <Badge tone="amber" className="ml-1">Locked</Badge>}
                      {u.must_change_password && <Badge tone="sky" className="ml-1">New password due</Badge>}
                    </td>
                    <td className="td whitespace-nowrap text-ink-soft">{u.last_login_at?.replace('T', ' ').slice(0, 16) ?? 'Never'}</td>
                    <td className="td whitespace-nowrap text-right">
                      {confirm === u.id ? (
                        <span className="inline-flex items-center gap-1 text-sm">Reset password?
                          <button type="button" className="btn btn-danger !py-0.5" disabled={reset.isPending} onClick={() => reset.mutate(u)}>Yes, reset</button>
                          <button type="button" className="btn btn-quiet !py-0.5" onClick={() => setConfirm(null)}>Cancel</button></span>
                      ) : (
                        <>
                          <button type="button" className="btn btn-quiet" onClick={() => setConfirm(u.id)}><KeyRound className="h-3.5 w-3.5" aria-hidden />Reset password</button>
                          <button type="button" className="btn btn-quiet" disabled={u.id === me?.id || toggle.isPending} onClick={() => toggle.mutate(u)}>{u.is_active ? 'Turn off' : 'Turn on'}</button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {(toggle.error || reset.error) && <p className="text-sm text-fail" role="alert">{((toggle.error || reset.error) as Error).message}</p>}
      </div>
    </>
  )
}

function EmailCell({ u, onSaved }: { u: AuthUser; onSaved: () => void }) {
  const [editing, setEditing] = useState(false)
  const [v, setV] = useState(u.email ?? '')
  const save = useMutation({ mutationFn: () => patch(`/api/admin/users/${u.id}`, { email: v.trim() || null }), onSuccess: () => { setEditing(false); onSaved() } })
  if (!editing) return <button type="button" className="text-left text-sm hover:underline" onClick={() => setEditing(true)}>{u.email || <span className="text-ink-faint">add email</span>}</button>
  return (
    <form className="flex items-center gap-1" onSubmit={(e) => { e.preventDefault(); save.mutate() }}>
      <label className="sr-only" htmlFor={`em-${u.id}`}>Email for {u.username}</label>
      <input id={`em-${u.id}`} type="email" className="input !py-0.5" value={v} autoFocus onChange={(e) => setV(e.target.value)} />
      <button type="submit" className="btn !py-0.5" disabled={save.isPending}>Save</button>
      {save.error && <span className="text-xs text-fail">{(save.error as Error).message}</span>}
    </form>
  )
}
