import { useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Plus, SearchX } from 'lucide-react'
import { get } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { cn } from '../../lib/utils'
import { payText, rupees, TYPE_WORD, whereText } from '../../lib/format'
import type { Dashboard, OpportunityRow } from '../../lib/types'
import { Badge, Empty, ErrorState, PageHeader, Tabs } from '../../components/ui'
import { DataTable, type Column } from '../../components/DataTable'
import { TableSkeleton } from '../../components/Skeleton'
import { SearchBox } from '../../components/SearchBox'
import { ApplyBy } from '../../components/Deadline'
import { ReviewList } from './Reviews'

const KINDS = [{ id: 'all', label: 'All' }, { id: 'job', label: 'Jobs' }, { id: 'training', label: 'Training' }, { id: 'mentor', label: 'Mentors' }]
const TYPE_TONE = { job: 'navy', training: 'neutral', mentor: 'accent' } as const

/** Every listing in one place: live ones to match against, the review queue, and rejected or closed ones. */
export default function Opportunities() {
  const { user } = useAuth()
  const admin = user?.role === 'ngo_admin'
  const [params, setParams] = useSearchParams()
  const tab = ['live', 'review', 'rejected', 'closed'].includes(params.get('tab') ?? '') ? params.get('tab')! : 'live'
  const dash = useQuery({ queryKey: ['dashboard'], queryFn: () => get<Dashboard>('/api/dashboard') })
  const waiting = dash.data?.counts.pending_reviews ?? 0
  return (
    <>
      <PageHeader title="Opportunities" sub="Live jobs, training and mentors, with how many students could take each one. New and changed listings wait under Review until an admin approves them."
        actions={admin ? <Link to="/ngo/opportunities/new" className="btn btn-primary"><Plus className="h-4 w-4" aria-hidden />Add opportunity</Link> : undefined} />
      <div className="space-y-4 px-4 py-6 sm:px-8">
        <Tabs value={tab} onChange={(t) => setParams({ tab: t })} tabs={[{ id: 'live', label: 'Live' }, { id: 'review', label: `Waiting for review${waiting ? ` (${waiting})` : ''}` }, { id: 'rejected', label: 'Rejected' }, { id: 'closed', label: 'Closed' }]} />
        {tab === 'live' && <Live />}
        {tab === 'review' && <ReviewList status="pending" canAct={admin} />}
        {tab === 'rejected' && <ReviewList status="rejected" canAct={admin} />}
        {tab === 'closed' && <ReviewList status="closed" canAct={admin} />}
      </div>
    </>
  )
}

function Live() {
  const nav = useNavigate()
  const [q, setQ] = useState('')
  const [kind, setKind] = useState('all')
  const list = useQuery({ queryKey: ['opportunities'], queryFn: () => get<OpportunityRow[]>('/api/opportunities') })
  const rows = useMemo(() => {
    const terms = q.toLowerCase().split(/\s+/).filter(Boolean)
    return (list.data ?? []).filter((o) => (kind === 'all' || o.type === kind) && terms.every((t) => [o.opp_id, o.title, o.org_name, o.city, o.job_family, ...o.skills].join(' ').toLowerCase().includes(t)))
  }, [list.data, q, kind])

  const cols: Column<OpportunityRow>[] = [
    { key: 'title', header: 'Listing', sort: (o) => o.title.toLowerCase(), csv: (o) => o.title, render: (o) => <><div className="font-medium">{o.title}{o.managed && <Badge tone="sky" className="ml-1.5">Posted in the app</Badge>}</div><div className="text-xs text-ink-soft">{o.org_name} <span className="font-mono text-ink-faint">{o.opp_id}</span></div></> },
    { key: 'type', header: 'Type', sort: (o) => o.type, csv: (o) => o.type, render: (o) => <Badge tone={TYPE_TONE[o.type]}>{TYPE_WORD[o.type]}</Badge> },
    { key: 'where', header: 'Where', sort: (o) => o.city, csv: (o) => whereText(o.city, o.mode), className: 'whitespace-nowrap', render: (o) => whereText(o.city, o.mode) },
    { key: 'pay', header: 'Pay', sort: (o) => o.pay_max, csv: (o) => payText(o.pay_min, o.pay_max), className: 'whitespace-nowrap', render: (o) => payText(o.pay_min, o.pay_max) ?? <span className="text-ink-faint">{o.type === 'job' ? 'not disclosed' : '-'}</span> },
    { key: 'cost', header: 'Cost', sort: (o) => o.upfront_cost, csv: (o) => o.upfront_cost, className: 'whitespace-nowrap', render: (o) => (o.upfront_cost > 0 ? <Badge tone={o.type === 'job' ? 'fail' : 'amber'}>{rupees(o.upfront_cost)}</Badge> : 'Free') },
    { key: 'hours', header: 'Hours', sort: (o) => o.hours_per_week, csv: (o) => o.hours_per_week, render: (o) => <>{o.hours_per_week}{o.night_shift && <Badge tone="plum" className="ml-1">night</Badge>}</> },
    { key: 'safety', header: 'Safety', sort: (o) => o.safety_score, csv: (o) => o.safety_score, render: (o) => <span className={cn(o.safety_score <= 2 && 'font-medium text-fail')}>{o.safety_score}/5</span> },
    { key: 'deadline', header: 'Apply by', sort: (o) => o.apply_by ?? '9999', csv: (o) => o.apply_by ?? '', className: 'whitespace-nowrap', render: (o) => (o.apply_by ? <ApplyBy date={o.apply_by} /> : <span className="text-ink-faint">open</span>) },
    { key: 'fit', header: 'Students who fit', sort: (o) => o.eligible_count, csv: (o) => o.eligible_count, render: (o) => <span className="tabular-nums">{o.eligible_count}</span> },
    { key: 'load', header: 'In play', sort: (o) => o.load ?? 0, csv: (o) => o.load ?? 0, render: (o) => <span className="tabular-nums text-ink-soft">{o.load ?? 0} / {o.openings ?? 1}</span> },
  ]
  return (
    <>
      <SearchBox value={q} onChange={setQ} label="Search opportunities" placeholder="Search by title, company, city or skill. Try: python hyderabad" />
      <Tabs tabs={KINDS} value={kind} onChange={setKind} />
      {list.isLoading && <TableSkeleton rows={8} />}
      {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
      {list.data && rows.length === 0 && <Empty icon={SearchX} title="No listings match">Try fewer words, or switch to All.</Empty>}
      {rows.length > 0 && <DataTable columns={cols} rows={rows} rowKey={(o) => o.opp_id} onRowClick={(o) => nav(`/ngo/opportunities/${o.opp_id}`)} csvName="opportunities" initialSort={{ key: 'title', dir: 'asc' }} />}
    </>
  )
}
