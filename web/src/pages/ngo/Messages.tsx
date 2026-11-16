import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Briefcase, GraduationCap, Inbox } from 'lucide-react'
import { get } from '../../lib/api'
import { cn } from '../../lib/utils'
import type { OpportunityRow, Thread } from '../../lib/types'
import { Chat } from '../../components/Chat'
import { Badge, Empty, ErrorState, PageHeader, Spinner, Tabs } from '../../components/ui'
import { useAuth } from '../../lib/auth'
import Leads from './Leads'
import Broadcast from './Broadcast'

const key = (t: { thread_type: string; thread_id: string }) => `${t.thread_type}:${t.thread_id}`

/** Chats with students and employers; for admins also the WhatsApp leads from employers and bulk WhatsApp to students. */
export default function Messages() {
  const [params, setParams] = useSearchParams()
  const { user } = useAuth()
  const admin = user?.role === 'ngo_admin'
  const tab = admin && ['leads', 'bulk'].includes(params.get('tab') ?? '') ? params.get('tab')! : 'chats'
  const leadsUnread = useQuery({ queryKey: ['leads-unread'], queryFn: () => get<{ unread: number }>('/api/leads/unread'), enabled: admin, refetchInterval: 15000 })
  return (
    <>
      <PageHeader title="Messages" sub={admin ? 'Chats with students and employers, WhatsApp messages from employers, and bulk WhatsApp to students.' : 'Conversations with students and employers. Open one to read it and reply. Start a new one from a student or a listing.'} />
      <div className="px-4 py-6 sm:px-8">
        {admin && <div className="mb-5"><Tabs value={tab} onChange={(t) => setParams({ tab: t })} tabs={[{ id: 'chats', label: 'Chats' }, { id: 'leads', label: `WhatsApp from employers${leadsUnread.data?.unread ? ` (${leadsUnread.data.unread})` : ''}` }, { id: 'bulk', label: 'Bulk WhatsApp' }]} /></div>}
        {tab === 'chats' && <Chats />}
        {tab === 'leads' && <Leads />}
        {tab === 'bulk' && <Broadcast />}
      </div>
    </>
  )
}

function Chats() {
  const [params, setParams] = useSearchParams()
  const selected = params.get('thread') // for example student:S001 or listing:J001
  const threads = useQuery({ queryKey: ['threads'], queryFn: () => get<Thread[]>('/api/threads'), refetchInterval: 5000 })
  const opps = useQuery({ queryKey: ['opportunities'], queryFn: () => get<OpportunityRow[]>('/api/opportunities') })
  const title = (type: string, id: string) =>
    type === 'student' ? `Student ${id}` : `Listing ${id}${opps.data?.find((o) => o.opp_id === id) ? ` · ${opps.data.find((o) => o.opp_id === id)!.title}` : ''}`

  // a thread opened from another page may not have any messages yet, so show it at the top
  const list: Thread[] = [...(threads.data ?? [])]
  if (selected && !list.some((t) => key(t) === selected)) {
    const [thread_type, thread_id] = selected.split(':')
    if ((thread_type === 'student' || thread_type === 'listing') && thread_id)
      list.unshift({ thread_type, thread_id, count: 0, unread: 0, last_body: 'No messages yet', last_role: 'ngo', last_at: '' })
  }
  const current = list.find((t) => key(t) === selected)

  return (
    <>
      <div className="grid gap-5 lg:grid-cols-[320px_minmax(0,1fr)]">
        <div>
          {threads.isLoading && <Spinner />}
          {threads.error && <ErrorState error={threads.error} onRetry={() => threads.refetch()} />}
          {threads.data && list.length === 0 && <Empty icon={Inbox} title="No conversations yet">Students and employers can write to you from their own areas. You can also start one from a student or a listing.</Empty>}
          <ul className="space-y-2">
            {list.map((t) => (
              <li key={key(t)}>
                <button type="button" onClick={() => setParams({ thread: key(t) })} aria-current={key(t) === selected}
                  className={cn('card w-full px-3 py-2.5 text-left transition-colors', key(t) === selected ? 'border-accent bg-accent-soft' : 'hover:bg-[#f6f0e3]')}>
                  <span className="flex items-center gap-2 text-sm font-medium">
                    {t.thread_type === 'student' ? <GraduationCap className="h-4 w-4 text-ink-soft" aria-hidden /> : <Briefcase className="h-4 w-4 text-ink-soft" aria-hidden />}
                    <span className="truncate">{title(t.thread_type, t.thread_id)}</span>
                    {t.unread > 0 && <Badge tone="maple" className="ml-auto">{t.unread} new</Badge>}
                  </span>
                  <span className="mt-0.5 block truncate text-xs text-ink-soft">{t.last_role === 'ngo' ? 'You: ' : ''}{t.last_body}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div className="min-w-0">
          {current ? (
            <>
              <h2 className="mb-3">{title(current.thread_type, current.thread_id)}</h2>
              <Chat key={key(current)} threadType={current.thread_type} threadId={current.thread_id} role="ngo" />
            </>
          ) : (
            <Empty title="Pick a conversation">Choose one on the left to read it and reply.</Empty>
          )}
        </div>
      </div>
    </>
  )
}
