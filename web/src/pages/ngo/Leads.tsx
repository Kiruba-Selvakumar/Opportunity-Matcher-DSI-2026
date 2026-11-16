import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, Building2, FilePlus2, Inbox, Link2, RotateCcw, Send } from 'lucide-react'
import { get, post } from '../../lib/api'
import { cn } from '../../lib/utils'
import type { LeadThread, OpportunityRow } from '../../lib/types'
import { Badge, Banner, Empty, ErrorState, Spinner, Tabs } from '../../components/ui'
import { useToast } from '../../components/Toast'

const STATUS_TONE = { new: 'maple', mapped: 'pass', dismissed: 'neutral' } as const
const STATUS_WORD = { new: 'New', mapped: 'Linked to a listing', dismissed: 'Dismissed' }

/** Employers who wrote to the NGO's WhatsApp number. Read, reply, and turn each one into a listing. */
export default function Leads() {
  const [params, setParams] = useSearchParams()
  const [filter, setFilter] = useState('new')
  const selected = Number(params.get('lead')) || null
  const list = useQuery({ queryKey: ['leads', filter], queryFn: () => get<LeadThread[]>(`/api/leads${filter === 'all' ? '' : `?status=${filter}`}`), refetchInterval: 10000 })
  return (
    <div className="grid gap-5 lg:grid-cols-[320px_minmax(0,1fr)]">
      <div className="space-y-3">
        <Tabs value={filter} onChange={setFilter} tabs={[{ id: 'new', label: 'New' }, { id: 'mapped', label: 'Done' }, { id: 'dismissed', label: 'Dismissed' }, { id: 'all', label: 'All' }]} />
        {list.isLoading && <Spinner />}
        {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
        {list.data?.length === 0 && <Empty icon={Inbox} title="No messages here">When an employer writes to the NGO's WhatsApp number, it shows up here.</Empty>}
        <ul className="space-y-2">{list.data?.map((t) => (
          <li key={t.id}><button type="button" onClick={() => setParams({ tab: 'leads', lead: String(t.id) })} aria-current={t.id === selected}
            className={cn('card w-full px-3 py-2.5 text-left transition-colors', t.id === selected ? 'border-accent bg-accent-soft' : 'hover:bg-[#f6f0e3]')}>
            <span className="flex items-center gap-2 text-sm font-medium"><Building2 className="h-4 w-4 text-ink-soft" aria-hidden /><span className="truncate">{t.profile_name || t.phone}</span>
              {t.unread > 0 && <Badge tone="maple" className="ml-auto">{t.unread} new</Badge>}</span>
            <span className="mt-0.5 block truncate text-xs text-ink-soft">{t.last_body}</span>
          </button></li>))}
        </ul>
      </div>
      <div className="min-w-0">{selected ? <Conversation key={selected} id={selected} /> : <Empty title="Pick a conversation">Choose one on the left to read it, reply and make it into a listing.</Empty>}</div>
    </div>
  )
}

function Conversation({ id }: { id: number }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [text, setText] = useState('')
  const [linkTo, setLinkTo] = useState('')
  const opps = useQuery({ queryKey: ['opportunities'], queryFn: () => get<OpportunityRow[]>('/api/opportunities') })
  const q = useQuery({ queryKey: ['lead', id], queryFn: () => get<LeadThread>(`/api/leads/${id}`) })
  const refresh = () => { qc.invalidateQueries({ queryKey: ['lead', id] }); qc.invalidateQueries({ queryKey: ['leads'] }); qc.invalidateQueries({ queryKey: ['dashboard'] }) }
  const reply = useMutation({ mutationFn: () => post(`/api/leads/${id}/reply`, { text }), onSuccess: () => { setText(''); toast('Sent on WhatsApp.'); refresh() }, onError: (e) => toast((e as Error).message, 'fail') })
  const status = useMutation({ mutationFn: (s: string) => post(`/api/leads/${id}/status`, { status: s }), onSuccess: () => { toast('Updated.'); refresh() } })
  const link = useMutation({ mutationFn: () => post(`/api/leads/${id}/status`, { status: 'mapped', opp_id: linkTo }), onSuccess: () => { setLinkTo(''); toast('Linked to the listing.'); refresh() }, onError: (e) => toast((e as Error).message, 'fail') })
  if (q.isLoading) return <Spinner />
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const t = q.data!
  const lastIn = [...(t.messages ?? [])].reverse().find((m) => m.direction === 'in')
  const stale = lastIn && Date.now() - new Date(lastIn.at).getTime() > 24 * 3600 * 1000
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><h2>{t.profile_name || 'Employer'}</h2><p className="font-mono text-xs text-ink-soft">+{t.phone} <Badge tone={STATUS_TONE[t.status]} className="ml-1">{STATUS_WORD[t.status]}</Badge>{t.mapped_opp_id && <Link to={`/ngo/opportunities/${t.mapped_opp_id}`} className="ml-2 underline">{t.mapped_opp_id}</Link>}</p></div>
        <div className="flex flex-wrap gap-2">
          <Link to={`/ngo/opportunities/new?lead=${id}`} className="btn btn-primary"><FilePlus2 className="h-4 w-4" aria-hidden />Make a listing from this</Link>
          {t.status === 'dismissed' ? <button type="button" className="btn" onClick={() => status.mutate('new')}><RotateCcw className="h-4 w-4" aria-hidden />Reopen</button>
            : <button type="button" className="btn" onClick={() => status.mutate('dismissed')}><Archive className="h-4 w-4" aria-hidden />Dismiss</button>}
        </div>
      </div>
      <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); link.mutate() }}>
        <div className="min-w-[16rem] flex-1"><label className="label" htmlFor="lead-link">Or add it to a listing that is already live</label>
          <select id="lead-link" className="input" value={linkTo} onChange={(e) => setLinkTo(e.target.value)}>
            <option value="">Choose a listing</option>{opps.data?.map((o) => <option key={o.opp_id} value={o.opp_id}>{o.title} at {o.org_name} ({o.opp_id})</option>)}</select></div>
        <button type="submit" className="btn" disabled={!linkTo || link.isPending}><Link2 className="h-4 w-4" aria-hidden />Link it</button>
      </form>
      <ol className="card max-h-[52vh] space-y-2 overflow-y-auto p-4">
        {t.messages?.map((m) => (
          <li key={m.id} className={cn('max-w-[80%] rounded-lg px-3 py-2 text-sm', m.direction === 'in' ? 'bg-sunk' : 'ml-auto bg-accent-soft')}>
            <p className="whitespace-pre-wrap">{m.body}</p>
            <p className="mt-1 text-[11px] text-ink-faint">{m.at.replace('T', ' ').slice(0, 16)}{m.sent_by ? ` · ${m.sent_by}` : ''}</p>
          </li>))}
      </ol>
      {stale && <Banner tone="amber" lead="More than a day since they wrote.">WhatsApp only delivers a free-text reply within 24 hours of their last message. Call them, or wait for them to write again.</Banner>}
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); reply.mutate() }}>
        <label className="sr-only" htmlFor="lead-reply">Reply</label>
        <input id="lead-reply" className="input" value={text} maxLength={1000} onChange={(e) => setText(e.target.value)} placeholder="Reply on WhatsApp" />
        <button type="submit" className="btn btn-primary" disabled={!text.trim() || reply.isPending}><Send className="h-4 w-4" aria-hidden />Send</button>
      </form>
    </div>
  )
}
