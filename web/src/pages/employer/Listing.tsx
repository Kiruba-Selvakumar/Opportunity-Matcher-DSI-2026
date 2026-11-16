import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, CalendarPlus, Check, Copy, MessageSquare, Pencil, RotateCcw, Send, Users, XCircle } from 'lucide-react'
import { get, post } from '../../lib/api'
import { payText, rupees, TYPE_WORD, whereText } from '../../lib/format'
import type { Applicant, ListingDetailFull } from '../../lib/types'
import { Badge, Banner, Empty, ErrorState, KV, Meter, PageHeader, Section, Tabs } from '../../components/ui'
import { CardsSkeleton } from '../../components/Skeleton'
import { useConfirm } from '../../components/Confirm'
import { useToast } from '../../components/Toast'
import { APPLICANT_LABEL, ListingStatusBadge } from './StatusBadge'
import { InterviewList, ScheduleForm } from '../../components/Interviews'
import { ApplyBy } from '../../components/Deadline'

const ACTION: Record<string, string> = { shortlisted: 'Shortlist', interview: 'Invite to interview', offered: 'Make an offer', hired: 'Mark as hired', not_a_fit: 'Not a fit' }

export default function Listing() {
  const { oid = '' } = useParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const confirm = useConfirm()
  const toast = useToast()
  const [tab, setTab] = useState('applicants')
  const q = useQuery({ queryKey: ['my-listing', oid], queryFn: () => get<ListingDetailFull>(`/api/me/listings/${oid}`) })
  const o = q.data
  const done = (msg: string) => { toast(msg); qc.invalidateQueries({ queryKey: ['my-listing', oid] }); qc.invalidateQueries({ queryKey: ['my-listings'] }) }
  const act = useMutation({
    mutationFn: ({ path }: { path: string; ok: string }) => post(path, {}),
    onSuccess: (_, v) => done(v.ok), onError: (e) => toast((e as Error).message, 'fail'),
  })
  const copy = useMutation({ mutationFn: () => post<{ opp_id: string }>(`/api/me/listings/${oid}/copy`, {}), onSuccess: (r) => { toast('Copied. This is a draft.'); qc.invalidateQueries({ queryKey: ['my-listings'] }); nav(`/employer/${r.opp_id}`) } })

  const close = async () => { if (await confirm({ title: 'Close this listing?', body: 'Students will no longer see it, and anyone who showed interest will be told it has closed.', confirmLabel: 'Close listing', danger: true })) act.mutate({ path: `/api/me/listings/${oid}/close`, ok: 'Listing closed.' }) }

  return (
    <>
      <PageHeader title={o?.title ?? 'Listing'} sub={o ? `${o.org_name} · ${TYPE_WORD[o.type]} · ${whereText(o.city, o.mode)}` : 'Loading your listing.'}
        actions={<div className="flex flex-wrap gap-2"><Link to="/employer" className="btn"><ArrowLeft className="h-4 w-4" aria-hidden />My listings</Link></div>} />
      <div className="px-4 pb-16 sm:px-8">
        {q.isLoading && <div className="pt-6"><CardsSkeleton n={2} /></div>}
        {q.error && <div className="pt-6"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>}
        {o && (
          <>
            <div className="flex flex-wrap items-center gap-2 pt-5">
              <ListingStatusBadge status={o.status} />
              <ApplyBy date={o.apply_by} />
              {o.editable && o.status !== 'closed' && <Link to={`/employer/${oid}/edit`} className="btn"><Pencil className="h-4 w-4" aria-hidden />Edit</Link>}
              {o.editable && (o.status === 'draft' || o.status === 'rejected') && <button type="button" className="btn btn-primary" onClick={() => act.mutate({ path: `/api/me/listings/${oid}/submit`, ok: 'Sent to the NGO for review.' })}><Send className="h-4 w-4" aria-hidden />Submit for review</button>}
              {o.editable && o.status === 'closed' && o.closed_reason !== 'filled' && <button type="button" className="btn" onClick={() => act.mutate({ path: `/api/me/listings/${oid}/reopen`, ok: 'Reopened.' })}><RotateCcw className="h-4 w-4" aria-hidden />Reopen</button>}
              {o.editable && o.status !== 'closed' && <button type="button" className="btn" onClick={close}><XCircle className="h-4 w-4" aria-hidden />Close</button>}
              {o.editable && <button type="button" className="btn" disabled={copy.isPending} onClick={() => copy.mutate()}><Copy className="h-4 w-4" aria-hidden />Copy</button>}
              <Link to={`/employer/messages?listing=${oid}`} className="btn btn-quiet"><MessageSquare className="h-4 w-4" aria-hidden />Message the NGO</Link>
            </div>
            <div className="mt-4 space-y-3">
              {o.status === 'draft' && <Banner tone="sky" lead="This is a draft.">Only you can see it. Submit it when it is ready.</Banner>}
              {o.status === 'pending' && <Banner tone="amber" lead="Waiting for the NGO.">Students cannot see this yet. You will be told when it is reviewed.</Banner>}
              {o.status === 'rejected' && <Banner tone="fail" lead="Not approved.">{o.review_note || 'The NGO did not give a reason. Message them.'} Fix it and send it again.</Banner>}
              {o.status === 'closed' && <Banner tone="amber" lead={o.closed_reason === 'filled' ? 'Filled.' : 'Closed.'}>{o.closed_reason === 'filled' ? 'All openings are taken. Copy this listing to post it again.' : 'Students cannot see this.'}</Banner>}
              {!o.managed && <Banner tone="sky" lead="The NGO manages this listing.">You can see who fits and who was shared with you. To change it, message the NGO.</Banner>}
            </div>

            <Section title="Listing details">
              <div className="card p-5">
                <KV items={[
                  ['Listing id', <span className="font-mono text-xs">{o.opp_id}</span>], ['Kind', TYPE_WORD[o.type]], ['Where', whereText(o.city, o.mode)],
                  ['Pay', payText(o.pay_min, o.pay_max) ?? 'Not disclosed'], ['Cost to join', o.upfront_cost > 0 ? rupees(o.upfront_cost) : 'Free'],
                  ['Hours a week', o.hours_per_week], ['Night shift', o.night_shift ? 'Yes' : 'No'], ['Openings', o.openings],
                  ['Safety score', o.status === 'active' || o.managed ? `${o.safety_score} of 5` : 'Set by the NGO'], ['Languages', o.languages_required.join(', ') || 'None listed'],
                ]} />
                {o.description && <p className="mt-4 max-w-[75ch] text-sm">{o.description}</p>}
                <h3 className="mb-2 mt-4 text-ink-soft">Skills asked for</h3>
                <div className="flex flex-wrap gap-1.5">{o.skills.map((s) => <Badge key={s} tone="accent">{s}</Badge>)}{o.skills.length === 0 && <span className="text-sm text-ink-faint">None of the skills were recognised. Use common names such as Python or SQL.</span>}</div>
              </div>
            </Section>

            <Section title="Students" right={<span className="text-sm text-ink-soft">{o.status === 'active' ? `${o.eligible_count} of ${o.total_students} can take this` : ''}</span>}>
              <Tabs value={tab} onChange={setTab} tabs={[{ id: 'applicants', label: `Applicants (${o.applicants.length})` }, { id: 'fit', label: `Best fit (${o.candidates.length})` }]} />
              <div className="mt-4">
                {tab === 'applicants' ? <Applicants list={o.applicants} oid={oid} onChange={() => done('Updated.')} /> : <BestFit o={o} />}
              </div>
            </Section>
          </>
        )}
      </div>
    </>
  )
}

function Applicants({ list, onChange }: { list: Applicant[]; oid: string; onChange: () => void }) {
  const confirm = useConfirm()
  const toast = useToast()
  const [noteFor, setNoteFor] = useState<number | null>(null)
  const [scheduleFor, setScheduleFor] = useState<number | null>(null)
  const [note, setNote] = useState('')
  const move = useMutation({
    mutationFn: ({ id, status, note }: { id: number; status: string; note: string }) => post(`/api/me/applications/${id}/status`, { status, note }),
    onSuccess: () => { setNoteFor(null); setNote(''); onChange() }, onError: (e) => toast((e as Error).message, 'fail'),
  })
  const go = async (a: Applicant, status: string) => {
    if (status === 'not_a_fit') { setNoteFor(a.id); return }
    if (status === 'hired' && !(await confirm({ title: 'Mark as hired?', body: 'This counts toward your openings. When all openings are taken, the listing closes.', confirmLabel: 'Mark as hired' }))) return
    move.mutate({ id: a.id, status, note: '' })
  }
  if (list.length === 0) return <Empty icon={Users} title="No applicants yet">When students show interest, the NGO checks them and shares the good fits with you. They appear here.</Empty>
  return (
    <ul className="space-y-3">
      {list.map((a) => {
        const [label, tone] = APPLICANT_LABEL[a.status] ?? [a.status, 'neutral' as const]
        const closed = a.status === 'hired' || a.status === 'not_a_fit'
        return (
          <li key={a.id} className="card p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex flex-wrap items-center gap-2 text-sm"><span className="font-mono text-xs">{a.candidate_code}</span><span className="font-medium">{a.branch}</span><span className="text-ink-soft">· {a.town} · CGPA {a.cgpa ?? 'not known'}</span></div>
                <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
                  {a.overlap.map((s) => <Badge key={s} tone="accent"><Check className="h-3 w-3" aria-hidden />{s}</Badge>)}
                  {a.missing.map((s) => <Badge key={s} tone="neutral">Missing {s}</Badge>)}
                </div>
                {a.student_note && <p className="mt-2 max-w-[75ch] text-sm text-ink-soft">“{a.student_note}”</p>}
                {a.employer_note && <p className="mt-1 text-xs text-ink-faint">Your note: {a.employer_note}</p>}
              </div>
              <div className="text-right"><Badge tone={tone}>{label}</Badge>{!closed && <div className="mt-1 text-xs text-ink-faint">{a.days_in_stage === 0 ? 'today' : `${a.days_in_stage} day${a.days_in_stage === 1 ? '' : 's'} in this stage`}</div>}</div>
            </div>
            {a.next.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2 border-t border-line pt-3">
                {/* "Schedule interview" moves a shortlisted candidate to the interview stage, so it replaces the plain button */}
                {a.next.filter((s) => !(s === 'interview' && a.can_schedule)).map((s, i) => <button key={s} type="button" className={s === 'not_a_fit' ? 'btn btn-quiet' : i === 0 ? 'btn btn-primary' : 'btn'} disabled={move.isPending} onClick={() => go(a, s)}>{ACTION[s]}</button>)}
                {a.can_schedule && <button type="button" className={a.status === 'shortlisted' ? 'btn btn-primary' : 'btn'} onClick={() => setScheduleFor(scheduleFor === a.id ? null : a.id)}><CalendarPlus className="h-4 w-4" aria-hidden />Schedule interview</button>}
              </div>
            )}
            {a.interviews.length > 0 && <div className="mt-3"><InterviewList items={a.interviews} side="employer" onChanged={onChange} /></div>}
            {scheduleFor === a.id && <div className="mt-3"><ScheduleForm path={`/api/me/applications/${a.id}/interviews`} side="employer" onDone={() => { setScheduleFor(null); onChange() }} onCancel={() => setScheduleFor(null)} /></div>}
            {noteFor === a.id && (
              <form className="pop mt-3 flex flex-wrap items-end gap-2 rounded-lg bg-bg p-3" onSubmit={(e) => { e.preventDefault(); move.mutate({ id: a.id, status: 'not_a_fit', note }) }}>
                <div className="min-w-[220px] flex-1"><label className="label" htmlFor={`nf-${a.id}`}>Why not (the student will read this)</label>
                  <input id={`nf-${a.id}`} className="input" value={note} maxLength={500} autoFocus onChange={(e) => setNote(e.target.value)} placeholder="For example: we need someone with Power BI now" /></div>
                <button type="submit" className="btn btn-danger" disabled={!note.trim() || move.isPending}>Save</button>
                <button type="button" className="btn btn-quiet" onClick={() => setNoteFor(null)}>Cancel</button>
              </form>
            )}
          </li>
        )
      })}
    </ul>
  )
}

function BestFit({ o }: { o: ListingDetailFull }) {
  if (o.status !== 'active') return <Empty title="Not live yet">Best-fit students appear once the NGO approves this listing.</Empty>
  if (o.candidates.length === 0) return <Empty title="No student fits yet">Talk to the NGO about what could change.</Empty>
  return (
    <>
      <p className="mb-3 max-w-[75ch] text-xs text-ink-faint">These are the students the system thinks fit best. They have not been shared with you yet. Each has a candidate code. Give the NGO the code when you want to talk about someone.</p>
      <div className="space-y-3">
        {o.candidates.map((c, i) => (
          <article key={c.candidate_code} className="card p-4">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 text-sm"><span className="font-mono text-xs text-ink-faint">#{i + 1}</span><span className="font-mono text-xs">{c.candidate_code}</span><span className="font-medium">{c.branch}</span><span className="text-ink-soft">· {c.town} · CGPA {c.cgpa ?? 'not known'}</span></div>
                <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">{c.overlap.map((s) => <Badge key={s} tone="accent"><Check className="h-3 w-3" aria-hidden />{s}</Badge>)}{c.missing.map((s) => <Badge key={s} tone="neutral">Missing {s}</Badge>)}</div>
              </div>
              <div className="w-28 text-right"><div className="font-serif text-xl">{c.final_score.toFixed(2)}</div><Meter value={c.final_score} label="Fit score" /></div>
            </div>
          </article>
        ))}
      </div>
    </>
  )
}
