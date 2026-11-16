import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MessageSquare, Send } from 'lucide-react'
import { get, post } from '../lib/api'
import { cn } from '../lib/utils'
import type { ChatMessage, ChatRole } from '../lib/types'
import { Badge, ErrorState, Spinner } from './ui'

const WHO: Record<ChatRole, string> = { ngo: 'NGO staff', student: 'Student', lister: 'Employer' }
const MAX = 2000

export interface AboutOption { id: string; label: string }

/** One conversation. `role` is who is typing on this screen. Polls every 5 seconds. */
export function Chat({ threadType, threadId, role, aboutOptions, initialAbout, className }: {
  threadType: 'student' | 'listing'; threadId: string; role: ChatRole; aboutOptions?: AboutOption[]; initialAbout?: string; className?: string
}) {
  const qc = useQueryClient()
  const [body, setBody] = useState('')
  const [about, setAbout] = useState(initialAbout ?? '')
  const bottom = useRef<HTMLDivElement>(null)
  const key = ['thread', threadType, threadId, role]
  const q = useQuery({
    queryKey: key,
    queryFn: () => get<ChatMessage[]>(`/api/threads/${threadType}/${threadId}/messages`),
    refetchInterval: 5000,
  })
  const send = useMutation({
    mutationFn: () => post<ChatMessage>(`/api/threads/${threadType}/${threadId}/messages`,
      { body, about_opp_id: about || null }),
    onSuccess: () => {
      setBody(''); setAbout('')
      qc.invalidateQueries({ queryKey: key })
      qc.invalidateQueries({ queryKey: ['threads'] })
    },
  })
  const titleOf = (id: string | null) => aboutOptions?.find((o) => o.id === id)?.label ?? id
  const count = q.data?.length ?? 0
  useEffect(() => { bottom.current?.scrollIntoView({ block: 'end' }) }, [count])

  const submit = () => { if (body.trim() && !send.isPending) send.mutate() }
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() }
  }

  return (
    <section className={cn('card flex min-h-[420px] flex-col', className)} aria-label="Conversation">
      <div className="flex-1 space-y-3 overflow-y-auto p-4" style={{ maxHeight: '55vh' }} role="log" aria-live="polite">
        {q.isLoading && <Spinner text="Loading messages" />}
        {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
        {q.data && q.data.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center py-10 text-center text-sm text-ink-soft">
            <MessageSquare className="mb-2 h-5 w-5 text-ink-faint" aria-hidden />No messages yet. Write the first one below.
          </div>
        )}
        {q.data?.map((m) => {
          const mine = m.sender_role === role
          return (
            <div key={m.id} className={cn('flex flex-col', mine ? 'items-end' : 'items-start')}>
              <div className={cn('max-w-[75%] rounded-xl border px-3 py-2 text-sm', mine ? 'border-accent/30 bg-accent-soft' : 'border-line bg-bg')}>
                {m.about_opp_id && <Badge tone="neutral" className="mb-1">About {titleOf(m.about_opp_id)}</Badge>}
                <p className="whitespace-pre-wrap break-words">{m.body}</p>
              </div>
              <span className="mt-0.5 text-xs text-ink-faint">{mine ? 'You' : WHO[m.sender_role]} · {m.created_at.replace('T', ' ').slice(0, 16)}</span>
            </div>
          )
        })}
        <div ref={bottom} />
      </div>
      <div className="border-t border-line p-3">
        {aboutOptions && aboutOptions.length > 0 && (
          <div className="mb-2">
            <label htmlFor="about" className="sr-only">Which opportunity is this about</label>
            <select id="about" className="input !w-auto max-w-full !py-1 !text-xs" value={about} onChange={(e) => setAbout(e.target.value)}>
              <option value="">Not about one opportunity</option>
              {aboutOptions.map((o) => <option key={o.id} value={o.id}>About: {o.label}</option>)}
            </select>
          </div>
        )}
        <div className="flex items-end gap-2">
          <label htmlFor="msg" className="sr-only">Message</label>
          <textarea id="msg" className="input min-h-[44px] flex-1 resize-y" rows={2} value={body} maxLength={MAX}
            onChange={(e) => setBody(e.target.value)} onKeyDown={onKey} placeholder="Write a message. Enter sends, Shift+Enter adds a line." />
          <button type="button" className="btn btn-primary" onClick={submit} disabled={!body.trim() || send.isPending}>
            <Send className="h-4 w-4" aria-hidden />{send.isPending ? 'Sending' : 'Send'}
          </button>
        </div>
        <div className="mt-1.5 flex justify-between text-xs text-ink-faint">
          <span>Phone numbers and emails are removed from messages.</span>
          <span>{body.length}/{MAX}</span>
        </div>
        {send.error && <p className="mt-1 text-sm text-fail" role="alert">{(send.error as Error).message}</p>}
      </div>
    </section>
  )
}
