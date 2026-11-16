import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarClock, FileText, Gavel, MessageSquare, UserPen, Workflow } from 'lucide-react'
import { get, post } from '../../lib/api'
import type { CaseNote, TimelineEvent } from '../../lib/types'
import { Badge, Empty, ErrorState, Spinner } from '../../components/ui'
import { useToast } from '../../components/Toast'

export function NotesPanel({ sid }: { sid: string }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [body, setBody] = useState('')
  const [due, setDue] = useState('')
  const notes = useQuery({ queryKey: ['notes', sid], queryFn: () => get<CaseNote[]>(`/api/students/${sid}/notes`) })
  const refresh = () => { qc.invalidateQueries({ queryKey: ['notes', sid] }); qc.invalidateQueries({ queryKey: ['timeline', sid] }); qc.invalidateQueries({ queryKey: ['dashboard'] }) }
  const add = useMutation({
    mutationFn: () => post('/api/students/' + sid + '/notes', { body, follow_up_on: due || null }),
    onSuccess: () => { toast('Note saved.'); setBody(''); setDue(''); refresh() }, onError: (e) => toast((e as Error).message, 'fail'),
  })
  const done = useMutation({ mutationFn: (id: number) => post(`/api/notes/${id}/done`, {}), onSuccess: () => { toast('Marked done.'); refresh() } })
  const today = new Date().toISOString().slice(0, 10)
  return (
    <div className="space-y-3">
      <form className="card grid gap-3 p-4 sm:grid-cols-[1fr_170px_auto] sm:items-end" onSubmit={(e) => { e.preventDefault(); add.mutate() }}>
        <div><label className="label" htmlFor="cn-body">Add a note (only NGO staff see it)</label>
          <textarea id="cn-body" className="input min-h-[60px]" maxLength={2000} value={body} onChange={(e) => setBody(e.target.value)} placeholder="What you talked about, and what happens next." /></div>
        <div><label className="label" htmlFor="cn-due">Follow up on</label><input id="cn-due" type="date" className="input" min={today} value={due} onChange={(e) => setDue(e.target.value)} /></div>
        <button type="submit" className="btn btn-primary" disabled={!body.trim() || add.isPending}>Save note</button>
      </form>
      {notes.isLoading && <Spinner />}
      {notes.error && <ErrorState error={notes.error} onRetry={() => notes.refetch()} />}
      {notes.data?.length === 0 && <p className="text-sm text-ink-faint">No notes yet.</p>}
      <ul className="space-y-2">
        {notes.data?.map((n) => (
          <li key={n.id} className="card p-3 text-sm">
            <p className="whitespace-pre-wrap">{n.body}</p>
            <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-ink-faint">
              <span>{n.author} · {n.created_at.slice(0, 10)}</span>
              {n.follow_up_on && (n.done ? <Badge tone="neutral">Follow-up done</Badge> : <Badge tone={n.follow_up_on <= today ? 'amber' : 'sky'}><CalendarClock className="h-3 w-3" aria-hidden />Follow up {n.follow_up_on}</Badge>)}
              {n.follow_up_on && !n.done && <button type="button" className="underline" onClick={() => done.mutate(n.id)}>Mark done</button>}
            </div>
          </li>))}
      </ul>
    </div>
  )
}

const ICON = { decision: Gavel, application: Workflow, note: FileText, message: MessageSquare, edit: UserPen }

export function Timeline({ sid }: { sid: string }) {
  const q = useQuery({ queryKey: ['timeline', sid], queryFn: () => get<TimelineEvent[]>(`/api/students/${sid}/timeline`) })
  if (q.isLoading) return <Spinner />
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  if (!q.data?.length) return <Empty title="Nothing yet">Decisions, applications, messages and notes for this student appear here.</Empty>
  return (
    <ol className="max-w-3xl space-y-2 border-l-2 border-line pl-4">
      {q.data.map((e, i) => {
        const Icon = ICON[e.kind]
        return (
          <li key={i} className="relative text-sm"><span className="absolute -left-[26px] top-0.5 flex h-5 w-5 items-center justify-center rounded-full border border-line bg-surface"><Icon className="h-3 w-3 text-ink-soft" aria-hidden /></span>
            <span className="text-xs text-ink-faint">{e.at.replace('T', ' ').slice(0, 16)}</span><span className="block">{e.text}</span></li>)
      })}
    </ol>
  )
}
