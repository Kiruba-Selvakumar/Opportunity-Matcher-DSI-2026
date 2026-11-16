import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Bookmark, BookmarkCheck, SearchX } from 'lucide-react'
import { get } from '../../lib/api'
import { cn } from '../../lib/utils'
import { payText, rupees, TYPE_WORD, whereText } from '../../lib/format'
import { Badge, Empty, ErrorState, PageHeader, Tabs } from '../../components/ui'
import { DataTable, type Column } from '../../components/DataTable'
import { TableSkeleton } from '../../components/Skeleton'
import { SearchBox } from '../../components/SearchBox'
import { StatusPill } from './StatusPill'
import { ApplyBy } from '../../components/Deadline'
import { LIVE_STATUSES, useListingActions } from './useListingActions'

interface Item {
  opp_id: string; title: string; org_name: string; type: 'job' | 'training' | 'mentor'; city: string; mode: string
  score: number; fit: string; eligible: boolean; blockers: string[]; checks: string[]
  pay_min: number | null; pay_max: number | null; upfront_cost: number; hours_per_week: number; night_shift: boolean
  overlap: string[]; missing: string[]; crowded: boolean; description: string
  application: { id: number; status: string } | null; saved: boolean
  apply_by: string | null; closing_soon: boolean; starts_on: string | null; duration_weeks: number | null
}
const TABS = [{ id: 'all', label: 'All' }, { id: 'job', label: 'Jobs' }, { id: 'training', label: 'Training' }, { id: 'mentor', label: 'Mentors' }]
const FIT: Record<string, 'pass' | 'sky' | 'amber' | 'neutral'> = { 'Strong fit': 'pass', 'Good fit': 'sky', 'Possible fit': 'neutral' }

export default function Browse() {
  const [q, setQ] = useState('')
  const [tab, setTab] = useState('all')
  const [fitsOnly, setFitsOnly] = useState(true)
  const list = useQuery({ queryKey: ['browse'], queryFn: () => get<Item[]>('/api/me/browse') })
  const [params] = useSearchParams()
  const linked = params.get('opp')            // a WhatsApp message links straight to one listing
  useEffect(() => {
    const hit = linked && list.data?.find((i) => i.opp_id === linked)
    if (hit) { setQ(hit.title); setFitsOnly(false) }
  }, [linked, list.data])
  const { interest, save } = useListingActions()

  const rows = useMemo(() => {
    const terms = q.toLowerCase().split(/\s+/).filter(Boolean)
    return (list.data ?? []).filter((i) => (tab === 'all' || i.type === tab) && (!fitsOnly || i.eligible) &&
      terms.every((t) => [i.title, i.org_name, i.city, i.description, ...i.overlap, ...i.missing].join(' ').toLowerCase().includes(t)))
  }, [list.data, q, tab, fitsOnly])

  const cols: Column<Item>[] = [
    { key: 'title', header: 'Listing', sort: (i) => i.title.toLowerCase(), className: 'min-w-[220px]',
      render: (i) => <><Link to={`/student/browse/${i.opp_id}`} className="font-medium underline decoration-line-strong underline-offset-2 hover:decoration-ink">{i.title}</Link><div className="text-xs text-ink-soft">{i.org_name} · {TYPE_WORD[i.type]}</div>
        {!i.eligible && <div className="mt-1 text-xs text-fail">{i.blockers.join('; ')}</div>}{i.crowded && <Badge tone="amber" className="mt-1">Many have applied</Badge>}
        {i.apply_by && <div className="mt-1"><ApplyBy date={i.apply_by} /></div>}
        {i.type === 'training' && i.starts_on && <div className="mt-1 text-xs text-ink-faint">Next batch from {i.starts_on}{i.duration_weeks ? `, ${i.duration_weeks} weeks` : ''}</div>}</> },
    { key: 'fit', header: 'Fit', sort: (i) => i.score, render: (i) => <><Badge tone={FIT[i.fit] ?? 'neutral'}>{i.fit}</Badge><div className="mt-1 text-xs text-ink-faint">{i.overlap.length} of {i.overlap.length + i.missing.length} skills</div></> },
    { key: 'where', header: 'Where', sort: (i) => i.city, className: 'whitespace-nowrap', render: (i) => whereText(i.city, i.mode) },
    { key: 'pay', header: 'Pay', sort: (i) => i.pay_max, className: 'whitespace-nowrap', render: (i) => payText(i.pay_min, i.pay_max) ?? <span className="text-ink-faint">-</span> },
    { key: 'cost', header: 'Cost', sort: (i) => i.upfront_cost, className: 'whitespace-nowrap', render: (i) => (i.upfront_cost > 0 ? rupees(i.upfront_cost) : 'Free') },
    { key: 'act', header: '', className: 'whitespace-nowrap',
      render: (i) => i.application && LIVE_STATUSES.includes(i.application.status) ? <StatusPill status={i.application.status} /> : (
        <div className="flex items-center gap-1.5">
          <button type="button" className="btn btn-primary !py-1" disabled={!i.eligible || interest.isPending} title={i.eligible ? undefined : i.blockers.join('; ')} onClick={() => interest.mutate({ oppId: i.opp_id, note: '' })}>I'm interested</button>
          <button type="button" className={cn('btn btn-quiet !px-2 !py-1')} aria-pressed={i.saved} aria-label={i.saved ? 'Remove from saved' : 'Save for later'} onClick={() => save.mutate({ oppId: i.opp_id, saved: i.saved })}>{i.saved ? <BookmarkCheck className="h-4 w-4" aria-hidden /> : <Bookmark className="h-4 w-4" aria-hidden />}</button>
        </div>) },
  ]
  return (
    <>
      <PageHeader title="Browse" sub="Every live listing, best fit first. The top 5 are on My matches. Here you can search and look at the rest." />
      <div className="space-y-4 px-4 py-6 sm:px-8">
        <SearchBox value={q} onChange={setQ} label="Search listings" placeholder="Search by title, company, city or skill. Try: python  (press / to jump here)" />
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-[260px] flex-1"><Tabs tabs={TABS} value={tab} onChange={setTab} /></div>
          <label className="flex items-center gap-2 pb-2 text-sm"><input type="checkbox" checked={fitsOnly} onChange={(e) => setFitsOnly(e.target.checked)} />Only ones I can take</label>
        </div>
        {list.isLoading && <TableSkeleton rows={8} />}
        {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
        {list.data && rows.length === 0 && <Empty icon={SearchX} title="Nothing matches">{fitsOnly ? 'Try turning off "Only ones I can take" to see what is out of reach and why.' : 'Try fewer words.'}</Empty>}
        {rows.length > 0 && <DataTable columns={cols} rows={rows} rowKey={(i) => i.opp_id} initialSort={{ key: 'fit', dir: 'desc' }} />}
      </div>
    </>
  )
}
