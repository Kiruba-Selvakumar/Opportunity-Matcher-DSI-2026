import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarClock, ClipboardList, FileText, Send } from 'lucide-react'
import { get, post } from '../../lib/api'
import { useApp } from '../../lib/app-context'
import { useAuth } from '../../lib/auth'
import { PROGRAM_WORD, type Interview, type NgoApplication } from '../../lib/types'
import { Badge, Empty, ErrorState, PageHeader, Spinner, Tabs } from '../../components/ui'
import { DataTable, type Column } from '../../components/DataTable'
import { TableSkeleton } from '../../components/Skeleton'
import { SearchBox } from '../../components/SearchBox'
import { useToast } from '../../components/Toast'
import { InterviewList, ScheduleForm } from '../../components/Interviews'
import { StatusPill } from '../student/StatusPill'

type Group = (a: NgoApplication) => boolean
const GROUPS: Record<string, Group> = {
  waiting: (a) => a.status === 'interested' && !a.recommended_by,
  approve: (a) => a.status === 'interested' && !!a.recommended_by,
  progress: (a) => ['shared', 'shortlisted', 'interview', 'offered'].includes(a.status),
  closed: (a) => ['hired', 'declined', 'not_a_fit', 'withdrawn'].includes(a.status),
  all: () => true,
}
const OLD: Record<string, string> = { interested: 'waiting', progress: 'progress', closed: 'closed', all: 'all' }
const LABEL: Record<string, string> = { shared: 'Share with employer', declined: 'Decline', shortlisted: 'Shortlisted', interview: 'Interview', offered: 'Offered', hired: 'Hired', not_a_fit: 'Not a fit' }

export default function Applications() {
  const [params, setParams] = useSearchParams()
  const { user } = useAuth()
  const admin = user?.role === 'ngo_admin'
  const want = params.get('tab') ?? OLD[params.get('status') ?? ''] ?? 'waiting'
  const tab = GROUPS[want] || want === 'interviews' ? want : 'waiting'
  const [q, setQ] = useState('')
  const { showNames } = useApp()
  const list = useQuery({ queryKey: ['ngo-applications'], queryFn: () => get<NgoApplication[]>('/api/applications'), refetchInterval: 20000 })

  const rows = useMemo(() => {
    const terms = q.toLowerCase().split(/\s+/).filter(Boolean)
    const g = GROUPS[tab] ?? GROUPS.all
    return (list.data ?? []).filter((a) => g(a) &&
      terms.every((t) => [a.student_id, a.candidate_code, a.title, a.branch, a.town, a.college, showNames ? a.name ?? '' : ''].join(' ').toLowerCase().includes(t)))
  }, [list.data, tab, q, showNames])
  const counts = (k: string) => (list.data ?? []).filter(GROUPS[k]).length

  const cols: Column<NgoApplication>[] = [
    { key: 'student', header: 'Student', sort: (a) => a.student_id, csv: (a) => a.student_id,
      render: (a) => <><Link to={`/ngo/students/${a.student_id}`} className="font-mono text-xs underline">{a.student_id}</Link>
        {a.program && <Badge tone={a.program === 'get_skills' ? 'plum' : 'navy'} className="ml-1.5">{PROGRAM_WORD[a.program]}</Badge>}
        <div className="text-xs text-ink-faint">{a.branch} · {a.college || a.town}</div>{showNames && a.name && <div className="text-sm font-medium">{a.name}</div>}</> },
    { key: 'listing', header: 'Listing', sort: (a) => a.title.toLowerCase(), csv: (a) => a.title, render: (a) => <><Link to={`/ngo/opportunities/${a.opp_id}`} className="font-medium hover:underline">{a.title}</Link><div className="font-mono text-[11px] text-ink-faint">{a.opp_id} · code {a.candidate_code}</div></> },
    { key: 'fit', header: 'Fit', sort: (a) => a.score ?? 0, csv: (a) => a.score ?? '', render: (a) => (a.score != null ? <><span className="tabular-nums">{a.score.toFixed(2)}</span>{a.fit && <div className="text-xs text-ink-faint">{a.fit}</div>}</> : <span className="text-ink-faint">-</span>) },
    { key: 'cv', header: 'Resume', sort: (a) => a.ats ?? -1, csv: (a) => a.ats ?? '', render: (a) => (a.ats != null ? <Badge tone={a.ats >= 70 ? 'pass' : a.ats >= 50 ? 'sky' : 'amber'}><FileText className="h-3 w-3" aria-hidden />{a.ats}</Badge> : <span className="text-xs text-ink-faint">none</span>) },
    { key: 'status', header: 'Status', sort: (a) => a.status, csv: (a) => a.status, render: (a) => <><StatusPill status={a.status} />{a.recommended_by && a.status === 'interested' && <div className="mt-1 text-xs text-ink-faint">Put forward by {a.recommended_by}</div>}{a.interviews.some((i) => i.status === 'scheduled') && <div className="mt-1 inline-flex items-center gap-1 text-xs text-sky"><CalendarClock className="h-3 w-3" aria-hidden />{a.interviews.find((i) => i.status === 'scheduled')!.when}</div>}</> },
    { key: 'days', header: 'In stage', sort: (a) => a.days_in_stage, csv: (a) => a.days_in_stage, render: (a) => <span className={a.days_in_stage >= 7 && !['hired', 'declined', 'not_a_fit', 'withdrawn'].includes(a.status) ? 'font-medium text-amber' : 'text-ink-soft'}>{a.days_in_stage} d</span> },
    { key: 'note', header: 'Notes', render: (a) => <div className="max-w-[28ch] text-xs text-ink-soft">{a.student_note && <div>Student: {a.student_note}</div>}{a.ngo_note && <div>NGO: {a.ngo_note}</div>}{a.employer_note && <div>Employer: {a.employer_note}</div>}</div> },
    { key: 'act', header: '', render: (a) => <Move a={a} admin={admin} /> },
  ]

  const sub = admin
    ? 'Staff put students forward; you check the resume beside the listing and share them with the employer. Then follow each one to an offer.'
    : 'Students who showed interest. Put the good fits forward for an admin to share, decline with a reason, and arrange interviews.'
  return (
    <>
      <PageHeader title="Applications" sub={sub} />
      <div className="space-y-4 px-4 py-6 sm:px-8">
        <Tabs value={tab} onChange={(t) => setParams({ tab: t })} tabs={[
          { id: 'waiting', label: `New interest (${counts('waiting')})` }, { id: 'approve', label: `${admin ? 'Waiting for your approval' : 'Put forward'} (${counts('approve')})` },
          { id: 'progress', label: `With employers (${counts('progress')})` }, { id: 'interviews', label: 'Interviews' },
          { id: 'closed', label: `Finished (${counts('closed')})` }, { id: 'all', label: 'All' }]} />
        {tab === 'interviews' ? <Interviews /> : (
          <>
            <SearchBox value={q} onChange={setQ} label="Search applications" placeholder="Search by student, candidate code, listing, college or town" />
            {list.isLoading && <TableSkeleton />}
            {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
            {list.data && rows.length === 0 && <Empty icon={ClipboardList} title="Nothing here">{tab === 'waiting' ? 'No student is waiting on you right now.' : tab === 'approve' ? 'Nobody has been put forward yet.' : 'No applications match.'}</Empty>}
            {rows.length > 0 && <DataTable columns={cols} rows={rows} rowKey={(a) => a.id} csvName="applications" initialSort={{ key: 'days', dir: 'desc' }} />}
          </>)}
      </div>
    </>
  )
}

function Interviews() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['interviews'], queryFn: () => get<Interview[]>('/api/interviews') })
  if (q.isLoading) return <Spinner />
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  if (!q.data?.length) return <Empty icon={CalendarClock} title="No interviews coming up">Schedule one from a student who is with an employer.</Empty>
  return <div className="max-w-4xl"><InterviewList items={q.data} side="ngo" showTitle onChanged={() => { qc.invalidateQueries({ queryKey: ['interviews'] }); qc.invalidateQueries({ queryKey: ['ngo-applications'] }) }} /></div>
}

function Move({ a, admin }: { a: NgoApplication; admin: boolean }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [pending, setPending] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [scheduling, setScheduling] = useState(false)
  const refresh = () => { ['ngo-applications', 'dashboard', 'interviews'].forEach((k) => qc.invalidateQueries({ queryKey: [k] })) }
  const go = useMutation({
    mutationFn: (v: { status: string; note: string }) => post(`/api/applications/${a.id}/status`, v),
    onSuccess: () => { toast('Updated.'); setPending(null); setNote(''); refresh() },
    onError: (e) => toast((e as Error).message, 'fail'),
  })
  const forward = useMutation({
    mutationFn: () => post(`/api/applications/${a.id}/recommend`, { note }),
    onSuccess: () => { toast('Put forward. An admin will check and share.'); setPending(null); setNote(''); refresh() },
    onError: (e) => toast((e as Error).message, 'fail'),
  })
  if (a.next.length === 0 && !a.can_recommend && a.status !== 'interested') return <span className="text-xs text-ink-faint">Finished</span>
  const moves = a.next.filter((s) => s !== 'shared')
  const needsNote = (s: string) => s === 'declined' || s === 'not_a_fit'
  const choose = (s: string) => (needsNote(s) ? setPending(s) : go.mutate({ status: s, note: '' }))
  const canSchedule = ['shared', 'shortlisted', 'interview'].includes(a.status)
  return (
    <div className="min-w-[220px] space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {a.status === 'interested' && admin && <Link to={`/ngo/applications/${a.id}/review`} className="btn btn-primary !py-1"><Send className="h-3.5 w-3.5" aria-hidden />Review and share</Link>}
        {a.status === 'interested' && !admin && a.can_recommend && <button type="button" className="btn btn-primary !py-1" onClick={() => setPending('forward')}>Put forward</button>}
        {a.status === 'interested' && !admin && <Link to={`/ngo/applications/${a.id}/review`} className="btn !py-1">Side by side</Link>}
        {moves.map((s) => <button key={s} type="button" disabled={go.isPending} onClick={() => choose(s)} className="btn !py-1">{LABEL[s]}</button>)}
        {canSchedule && <button type="button" className="btn !py-1" onClick={() => setScheduling(!scheduling)}><CalendarClock className="h-3.5 w-3.5" aria-hidden />Interview</button>}
      </div>
      {pending && (
        <form className="pop space-y-1.5" onSubmit={(e) => { e.preventDefault(); if (pending === 'forward') forward.mutate(); else go.mutate({ status: pending, note }) }}>
          <label className="sr-only" htmlFor={`rn-${a.id}`}>Note</label>
          <input id={`rn-${a.id}`} className="input" autoFocus value={note} maxLength={500} onChange={(e) => setNote(e.target.value)}
            placeholder={pending === 'forward' ? 'Why they fit (the admin reads this)' : pending === 'declined' ? 'Why? The student will read this' : 'Why not a fit?'} />
          <div className="flex gap-1.5">
            <button type="submit" className={pending === 'forward' ? 'btn btn-primary !py-1' : 'btn btn-danger !py-1'} disabled={(pending !== 'forward' && !note.trim()) || go.isPending || forward.isPending}>{pending === 'forward' ? 'Put forward' : LABEL[pending]}</button>
            <button type="button" className="btn btn-quiet !py-1" onClick={() => setPending(null)}>Cancel</button></div>
        </form>
      )}
      {scheduling && <ScheduleForm path={`/api/applications/${a.id}/interviews`} side="ngo" onDone={() => { setScheduling(false); refresh() }} onCancel={() => setScheduling(false)} />}
    </div>
  )
}
