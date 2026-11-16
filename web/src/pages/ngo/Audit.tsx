import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Download, ScrollText } from 'lucide-react'
import { get } from '../../lib/api'
import type { AuditEvent } from '../../lib/types'
import { Badge, Empty, ErrorState, PageHeader, type Tone } from '../../components/ui'
import { DataTable, type Column } from '../../components/DataTable'
import { TableSkeleton } from '../../components/Skeleton'

const ACTIONS = ['login.ok', 'login.failed', 'login.locked', 'login.blocked', 'login.throttled', 'logout', 'password.changed',
  'password.change_failed', 'user.created', 'user.deactivated', 'user.reactivated', 'user.password_reset', 'user.listings_changed',
  'student.view', 'intake.pdf', 'decision.saved', 'message.sent', 'listing.view', 'listing.created', 'listing.updated', 'listing.submitted',
  'listing.reviewed', 'listing.closed', 'listing.reopened', 'application.created', 'application.status', 'profile.updated', 'resume.read', 'note.added',
  'export.downloaded', 'sessions.revoked', 'audit.exported']

function tone(a: string): Tone {
  if (a.startsWith('login.failed') || a.startsWith('login.locked') || a.startsWith('login.blocked') || a.startsWith('login.throttled') || a === 'password.change_failed') return 'fail'
  if (a.startsWith('user.')) return 'amber'
  if (a === 'login.ok' || a === 'logout' || a === 'listing.reviewed') return 'pass'
  return 'neutral'
}

export default function Audit() {
  const cols: Column<AuditEvent>[] = [
    { key: 'at', header: 'When (UTC)', sort: (e) => e.at, className: 'whitespace-nowrap text-ink-soft', render: (e) => e.at.replace('T', ' ').slice(0, 19) },
    { key: 'who', header: 'Who', sort: (e) => e.username ?? '', className: 'font-mono text-xs', render: (e) => e.username ?? '' },
    { key: 'action', header: 'Action', sort: (e) => e.action, className: 'whitespace-nowrap', render: (e) => <Badge tone={tone(e.action)}>{e.action}</Badge> },
    { key: 'target', header: 'Target', sort: (e) => e.target ?? '', className: 'font-mono text-xs', render: (e) => e.target ?? '' },
    { key: 'detail', header: 'Detail', className: 'max-w-[32ch] text-ink-soft', render: (e) => e.detail ?? '' },
    { key: 'ip', header: 'Address', className: 'font-mono text-xs text-ink-faint', render: (e) => e.ip ?? '' },
  ]
  const [action, setAction] = useState('')
  const [username, setUsername] = useState('')
  const qs = new URLSearchParams()
  if (action) qs.set('action', action)
  if (username.trim()) qs.set('username', username.trim())
  const q = useQuery({ queryKey: ['audit', action, username], queryFn: () => get<AuditEvent[]>(`/api/admin/audit?${qs}`) })
  return (
    <>
      <PageHeader title="Audit log" sub="Who signed in, who opened a student, and every change to an account. It never holds names, phone numbers, emails, message text or passwords, and nobody can edit it."
        actions={<a className="btn" href={`/api/admin/audit.csv?${qs}`} download><Download className="h-4 w-4" aria-hidden />Download CSV</a>} />
      <div className="space-y-4 px-8 py-6">
        <div className="flex flex-wrap items-end gap-3">
          <div><label className="label" htmlFor="a-act">Action</label>
            <select id="a-act" className="input !w-auto" value={action} onChange={(e) => setAction(e.target.value)}>
              <option value="">All actions</option>{ACTIONS.map((a) => <option key={a}>{a}</option>)}</select></div>
          <div><label className="label" htmlFor="a-user">Username</label>
            <input id="a-user" className="input" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="any" autoComplete="off" /></div>
          <span className="pb-2 text-sm text-ink-soft" aria-live="polite">{q.data ? `${q.data.length} events, newest first` : ''}</span>
        </div>
        {q.isLoading && <TableSkeleton />}
        {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
        {q.data?.length === 0 && <Empty icon={ScrollText} title="No events match">Try another action, or clear the username.</Empty>}
        {q.data && q.data.length > 0 && <DataTable columns={cols} rows={q.data} rowKey={(e) => e.id} pageSize={50} />}
      </div>
    </>
  )
}
