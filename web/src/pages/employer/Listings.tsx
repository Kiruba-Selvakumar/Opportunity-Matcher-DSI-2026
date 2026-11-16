import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Briefcase, Plus } from 'lucide-react'
import { get } from '../../lib/api'
import { TYPE_WORD, whereText } from '../../lib/format'
import type { ListingSummary } from '../../lib/types'
import { Empty, ErrorState, PageHeader } from '../../components/ui'
import { DataTable, type Column } from '../../components/DataTable'
import { TableSkeleton } from '../../components/Skeleton'
import { ListingStatusBadge } from './StatusBadge'
import { ApplyBy } from '../../components/Deadline'

export default function Listings() {
  const nav = useNavigate()
  const q = useQuery({ queryKey: ['my-listings'], queryFn: () => get<ListingSummary[]>('/api/me/listings') })
  const cols: Column<ListingSummary>[] = [
    { key: 'title', header: 'Listing', sort: (r) => r.title.toLowerCase(), render: (r) => <><div className="font-medium">{r.title}</div><div className="text-xs text-ink-soft">{r.org_name} · {TYPE_WORD[r.type]} · {whereText(r.city, r.mode)}</div>{r.status === 'rejected' && r.review_note && <div className="mt-1 text-xs text-fail">{r.review_note}</div>}</> },
    { key: 'status', header: 'Status', sort: (r) => r.status, render: (r) => <><ListingStatusBadge status={r.status} />{r.status === 'active' && r.apply_by && <div className="mt-1"><ApplyBy date={r.apply_by} /></div>}</> },
    { key: 'openings', header: 'Openings', sort: (r) => r.openings, render: (r) => r.openings },
    { key: 'fit', header: 'Students who fit', sort: (r) => r.eligible_count, render: (r) => (r.status === 'active' ? r.eligible_count : <span className="text-ink-faint">-</span>) },
    { key: 'applicants', header: 'Applicants', sort: (r) => r.applicants, render: (r) => r.applicants },
    { key: 'updated', header: 'Updated', sort: (r) => r.updated_at ?? '', render: (r) => <span className="text-ink-soft">{r.updated_at?.slice(0, 10) ?? 'NGO listing'}</span> },
  ]
  return (
    <>
      <PageHeader title="My listings" sub="The jobs and training you offer. New and changed listings are checked by the NGO before students see them."
        actions={<Link to="/employer/new" className="btn btn-primary"><Plus className="h-4 w-4" aria-hidden />Add listing</Link>} />
      <div className="px-4 py-6 sm:px-8">
        {q.isLoading && <TableSkeleton />}
        {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
        {q.data?.length === 0 && <Empty icon={Briefcase} title="No listings yet">Add your first one. It takes about two minutes.<br /><Link to="/employer/new" className="btn btn-primary mt-3">Add listing</Link></Empty>}
        {q.data && q.data.length > 0 && <DataTable columns={cols} rows={q.data} rowKey={(r) => r.opp_id} onRowClick={(r) => nav(`/employer/${r.opp_id}`)} initialSort={{ key: 'updated', dir: 'desc' }} />}
      </div>
    </>
  )
}
