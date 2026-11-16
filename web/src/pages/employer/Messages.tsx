import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { MessageSquare } from 'lucide-react'
import { get } from '../../lib/api'
import type { ListingSummary } from '../../lib/types'
import { Chat } from '../../components/Chat'
import { Empty, PageHeader } from '../../components/ui'

export default function Messages() {
  const [params, setParams] = useSearchParams()
  const q = useQuery({ queryKey: ['my-listings'], queryFn: () => get<ListingSummary[]>('/api/me/listings') })
  const live = (q.data ?? []).filter((l) => l.status !== 'draft')
  const oid = params.get('listing') ?? live[0]?.opp_id ?? ''
  return (
    <>
      <PageHeader title="Messages" sub="Talk to the NGO about a listing: how many students you need, a change to the role, or a question about a candidate." />
      <div className="max-w-3xl space-y-3 px-4 py-6 sm:px-8">
        {live.length > 1 && (
          <div><label className="label" htmlFor="m-list">About which listing</label>
            <select id="m-list" className="input" value={oid} onChange={(e) => setParams({ listing: e.target.value })}>{live.map((l) => <option key={l.opp_id} value={l.opp_id}>{l.title} ({l.opp_id})</option>)}</select></div>
        )}
        {oid ? <Chat key={oid} threadType="listing" threadId={oid} role="lister" /> : <Empty icon={MessageSquare} title="No listings to talk about yet">Submit a listing first. Then you can message the NGO about it.</Empty>}
      </div>
    </>
  )
}
