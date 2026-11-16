import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Inbox } from 'lucide-react'
import { get } from '../../lib/api'
import type { Decision } from '../../lib/types'
import { Badge, Empty, ErrorState, PageHeader, Tabs, type Tone } from '../../components/ui'
import { DataTable, type Column } from '../../components/DataTable'
import { TableSkeleton } from '../../components/Skeleton'

const TABS = [
  { id: 'all', label: 'All' },
  { id: 'accept', label: 'Accepted' },
  { id: 'reject', label: 'Rejected' },
  { id: 'flag', label: 'Flagged' },
]
const TONE: Record<string, Tone> = { accept: 'pass', reject: 'fail', flag: 'amber' }
const WORD: Record<string, string> = { accept: 'Accepted', reject: 'Rejected', flag: 'Flagged' }

export default function Decisions({ embedded = false }: { embedded?: boolean }) {
  const [tab, setTab] = useState('all')
  const q = useQuery({
    queryKey: ['decisions', tab],
    queryFn: () => get<Decision[]>(`/api/decisions${tab === 'all' ? '' : `?decision=${tab}`}`),
  })
  const cols: Column<Decision>[] = [
    { key: 'when', header: 'When', sort: (d) => d.created_at ?? '', csv: (d) => d.created_at, className: 'whitespace-nowrap text-ink-soft', render: (d) => d.created_at?.replace('T', ' ') },
    { key: 'student', header: 'Student', sort: (d) => d.student_id, csv: (d) => d.student_id, className: 'font-mono text-xs', render: (d) => d.student_id },
    { key: 'opp', header: 'Opportunity', sort: (d) => d.opp_id, csv: (d) => d.opp_id, className: 'font-mono text-xs', render: (d) => d.opp_id },
    { key: 'rank', header: 'Rank', sort: (d) => d.rank, csv: (d) => d.rank, render: (d) => d.rank ?? '' },
    { key: 'score', header: 'Score', sort: (d) => d.final_score, csv: (d) => d.final_score, render: (d) => d.final_score?.toFixed(2) ?? '' },
    { key: 'decision', header: 'Decision', sort: (d) => d.decision, csv: (d) => d.decision, render: (d) => <><Badge tone={TONE[d.decision]}>{WORD[d.decision]}</Badge>{d.what_if && <Badge tone="sky" className="ml-1">What-if</Badge>}</> },
    { key: 'reason', header: 'Reason', csv: (d) => d.reject_reason, render: (d) => d.reject_reason ?? '' },
    { key: 'note', header: 'Note', csv: (d) => d.note, className: 'max-w-[28ch]', render: (d) => d.note ?? '' },
    { key: 'by', header: 'Decided by', sort: (d) => d.decided_by ?? '', csv: (d) => d.decided_by, render: (d) => d.decided_by ?? '' },
    { key: 'secs', header: 'Seconds', sort: (d) => d.seconds_to_decide, csv: (d) => d.seconds_to_decide, render: (d) => (d.seconds_to_decide != null ? d.seconds_to_decide.toFixed(0) : '') },
  ]
  return (
    <>
      {!embedded && <PageHeader title="Decisions" sub="Every accept, reject and flag that staff have saved, newest first. They feed a small, capped nudge in the score once there are enough of them." />}
      <div className={embedded ? 'space-y-5' : 'space-y-5 px-4 py-6 sm:px-8'}>
        <Tabs tabs={TABS} value={tab} onChange={setTab} />
        {q.isLoading && <TableSkeleton />}
        {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
        {q.data && q.data.length === 0 && <Empty icon={Inbox} title="No decisions here yet">Open a student, then accept, reject or flag one of their matches.</Empty>}
        {q.data && q.data.length > 0 && <DataTable columns={cols} rows={q.data} rowKey={(d) => d.id} csvName="decisions" initialSort={{ key: 'when', dir: 'desc' }} />}
      </div>
    </>
  )
}
