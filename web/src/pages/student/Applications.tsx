import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bookmark, ClipboardList, MoreHorizontal } from 'lucide-react'
import { del, get, post } from '../../lib/api'
import type { StudentApplication } from '../../lib/types'
import { Badge, Empty, ErrorState, PageHeader, Tabs } from '../../components/ui'
import { CardsSkeleton } from '../../components/Skeleton'
import { useConfirm } from '../../components/Confirm'
import { useToast } from '../../components/Toast'
import { STATUS, StatusPill } from './StatusPill'
import { dateWords, TYPE_WORD } from '../../lib/format'
import { InterviewList } from '../../components/Interviews'
import { Lifeline } from '../../components/Lifeline'

interface Saved { opp_id: string; title: string; org_name: string; type: 'job' | 'training' | 'mentor'; city: string; fit: string; eligible: boolean }

export default function Applications() {
  const [tab, setTab] = useState('apps')
  const qc = useQueryClient()
  const confirm = useConfirm()
  const toast = useToast()
  const apps = useQuery({ queryKey: ['my-applications'], queryFn: () => get<StudentApplication[]>('/api/me/applications') })
  const saved = useQuery({ queryKey: ['my-saved'], queryFn: () => get<Saved[]>('/api/me/saved') })
  const refresh = () => { qc.invalidateQueries({ queryKey: ['my-applications'] }); qc.invalidateQueries({ queryKey: ['my-saved'] }); qc.invalidateQueries({ queryKey: ['me-student'] }) }
  const withdraw = useMutation({ mutationFn: (id: number) => post(`/api/me/applications/${id}/withdraw`, {}), onSuccess: () => { toast('You stepped back from this one.'); refresh() }, onError: (e) => toast((e as Error).message, 'fail') })
  const interest = useMutation({ mutationFn: (oid: string) => post('/api/me/applications', { opp_id: oid, note: '' }), onSuccess: () => { toast('Sent. The NGO will look at it next.'); refresh() }, onError: (e) => toast((e as Error).message, 'fail') })
  const unsave = useMutation({ mutationFn: (oid: string) => del(`/api/me/saved/${oid}`), onSuccess: () => { toast('Removed from saved.'); refresh() } })
  const ask = async (a: StudentApplication) => { if (await confirm({ title: 'Step back from this one?', body: 'The NGO and the employer will see that you withdrew. You can show interest again later.', confirmLabel: 'Withdraw', danger: true })) withdraw.mutate(a.id) }

  return (
    <>
      <PageHeader title="Applications" sub="Every opportunity you asked about, and where it is now. You can step back at any time." />
      <div className="max-w-3xl space-y-4 px-4 py-6 sm:px-8">
        <Tabs value={tab} onChange={setTab} tabs={[{ id: 'apps', label: `Applications${apps.data ? ` (${apps.data.length})` : ''}` }, { id: 'saved', label: `Saved${saved.data ? ` (${saved.data.length})` : ''}` }]} />
        {tab === 'apps' && (
          <>
            {apps.isLoading && <CardsSkeleton n={2} />}
            {apps.error && <ErrorState error={apps.error} onRetry={() => apps.refetch()} />}
            {apps.data?.length === 0 && <Empty icon={ClipboardList} title="No applications yet">Open <Link to="/student" className="underline">My matches</Link> and choose "I'm interested" on one you like.</Empty>}
            {apps.data?.map((a) => <AppCard key={a.id} a={a} onWithdraw={() => ask(a)} />)}
          </>
        )}
        {tab === 'saved' && (
          <>
            {saved.isLoading && <CardsSkeleton n={2} />}
            {saved.data?.length === 0 && <Empty icon={Bookmark} title="Nothing saved">Choose Save on a match to keep it here for later.</Empty>}
            {saved.data?.map((s) => (
              <article key={s.opp_id} className="card flex flex-wrap items-center justify-between gap-3 p-4">
                <div><div className="text-sm text-ink-soft"><Badge tone="neutral">{s.fit}</Badge> {TYPE_WORD[s.type]} · {s.city}</div><div className="mt-1 font-medium"><Link to={`/student/browse/${s.opp_id}`} className="underline decoration-line-strong underline-offset-2 hover:decoration-ink">{s.title}</Link></div><div className="text-sm text-ink-soft">{s.org_name}</div></div>
                <div className="flex gap-2"><button type="button" className="btn btn-primary" disabled={!s.eligible || interest.isPending} onClick={() => interest.mutate(s.opp_id)}>I'm interested</button><button type="button" className="btn btn-quiet" onClick={() => unsave.mutate(s.opp_id)}>Remove</button></div>
              </article>
            ))}
          </>
        )}
      </div>
    </>
  )
}

/** One application: what it is, when you applied, and a line showing where it is now. View opens the details. */
function AppCard({ a, onWithdraw }: { a: StudentApplication; onWithdraw: () => void }) {
  const [open, setOpen] = useState(false)
  const [menu, setMenu] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!menu) return
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !box.current?.contains(e.target as Node)) setMenu(false)
    }
    document.addEventListener('mousedown', close); document.addEventListener('keydown', close)
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', close) }
  }, [menu])
  const detailsId = `app-${a.id}-details`
  return (
    <article className="card p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="!text-lg">{a.title}</h2>
          <p className="text-sm text-ink-soft">{a.org_name} · Applied {dateWords(a.created_at)}{a.city ? ` · ${a.city}` : ''}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <div ref={box} className="relative">
            <button type="button" className="btn btn-quiet !px-2" aria-label={`More for ${a.title}`} aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu(!menu)}>
              <MoreHorizontal className="h-5 w-5" aria-hidden />
            </button>
            {menu && (
              <div role="menu" className="absolute right-0 z-20 mt-1 w-56 rounded-lg border border-line bg-surface py-1 text-sm shadow-lift">
                <Link role="menuitem" to={`/student/browse/${a.opp_id}`} className="block px-3 py-2 hover:bg-bg">Open the listing</Link>
                <Link role="menuitem" to={`/student/messages?about=${encodeURIComponent(a.opp_id)}`} className="block px-3 py-2 hover:bg-bg">Ask the NGO about this</Link>
                {a.can_withdraw && <button role="menuitem" type="button" className="block w-full px-3 py-2 text-left text-fail hover:bg-bg" onClick={() => { setMenu(false); onWithdraw() }}>Withdraw</button>}
              </div>
            )}
          </div>
          <button type="button" className="btn btn-primary" aria-expanded={open} aria-controls={detailsId} onClick={() => setOpen(!open)}>{open ? 'Hide' : 'View'}</button>
        </div>
      </div>
      <div className="mt-4"><Lifeline status={a.status} reviewing={a.reviewing} stoppedAt={a.stopped_at} /></div>
      {open && (
        <div id={detailsId} className="mt-2 space-y-3 border-t border-line pt-3">
          <div className="flex items-center gap-2 text-sm"><StatusPill status={a.status} /><Badge tone="neutral">{TYPE_WORD[a.type]}</Badge></div>
          <p className="text-sm">{a.words}</p>
          {a.ngo_note && <p className="rounded-md bg-bg px-3 py-2 text-sm"><strong className="font-medium">Note from the NGO:</strong> {a.ngo_note}</p>}
          {a.employer_note && <p className="rounded-md bg-bg px-3 py-2 text-sm"><strong className="font-medium">Note from the employer:</strong> {a.employer_note}</p>}
          {a.interviews.length > 0 && <div><h3 className="mb-1.5 text-ink-soft">Your interview</h3><InterviewList items={a.interviews} side="student" /></div>}
          <div>
            <h3 className="mb-1.5 text-ink-soft">Steps so far</h3>
            <ol className="space-y-1.5 border-l-2 border-line pl-4 text-sm" aria-label="Steps so far">
              {a.events.map((e, i) => (
                <li key={i} className="relative"><span className="absolute -left-[22px] top-1.5 h-2 w-2 rounded-full bg-accent" aria-hidden />
                  <span className="text-ink-soft">{dateWords(e.at)} · {e.by}:</span> {STATUS[e.to]?.[0] ?? e.to}{e.note ? <span className="text-ink-soft"> · “{e.note}”</span> : null}</li>
              ))}
            </ol>
          </div>
        </div>
      )}
    </article>
  )
}
