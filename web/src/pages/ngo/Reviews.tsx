import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, ClipboardCheck, OctagonAlert, TriangleAlert, X } from 'lucide-react'
import { get, post } from '../../lib/api'
import type { ReviewItem } from '../../lib/types'
import { Badge, Empty, ErrorState } from '../../components/ui'
import { CardsSkeleton } from '../../components/Skeleton'
import { useConfirm } from '../../components/Confirm'
import { useToast } from '../../components/Toast'
import { ListingStatusBadge } from '../employer/StatusBadge'

/** Listings posted in the app, by status. Only an NGO admin approves, rejects or closes; staff can read the queue. */
export function ReviewList({ status, canAct }: { status: 'pending' | 'rejected' | 'closed'; canAct: boolean }) {
  const q = useQuery({ queryKey: ['reviews', status], queryFn: () => get<ReviewItem[]>(`/api/listings/review?status=${status}`) })
  return (
    <div className="max-w-4xl space-y-4">
      {status === 'pending' && !canAct && <p className="text-sm text-ink-soft">An NGO admin approves or rejects these. You can read them and message the employer.</p>}
      {q.isLoading && <CardsSkeleton n={2} />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data?.length === 0 && <Empty icon={ClipboardCheck} title={status === 'pending' ? 'Nothing is waiting' : 'Nothing here'}>{status === 'pending' ? 'When an employer submits a listing, it appears here.' : 'Listings with this status appear here.'}</Empty>}
      {q.data?.map((r) => <ReviewCard key={r.opp_id} r={r} canAct={canAct} />)}
    </div>
  )
}

function ReviewCard({ r, canAct }: { r: ReviewItem; canAct: boolean }) {
  const qc = useQueryClient()
  const toast = useToast()
  const confirm = useConfirm()
  const [score, setScore] = useState(r.safety_score || 3)
  const [note, setNote] = useState('')
  const [rejecting, setRejecting] = useState(false)
  const [tell, setTell] = useState(true)
  const f = r.form
  const reds = r.flags.filter((x) => x.level === 'red').length
  const refresh = () => { qc.invalidateQueries({ queryKey: ['reviews'] }); qc.invalidateQueries({ queryKey: ['dashboard'] }); qc.invalidateQueries({ queryKey: ['opportunities'] }) }
  const review = useMutation({
    mutationFn: (decision: 'approve' | 'reject') => post<{ emailed?: number; told?: number }>(`/api/listings/${r.opp_id}/review`, { decision, safety_score: score, note, tell_students: decision === 'approve' && tell }),
    onSuccess: (res: { emailed?: number; told?: number }, d) => { toast(d === 'approve' ? `Approved. It is live now${res.emailed ? ', and the employer was emailed' : ''}.${res.told ? ` ${res.told} student${res.told === 1 ? '' : 's'} told on WhatsApp.` : ''}` : `Rejected. The employer has been told${res.emailed ? ' by email too' : ''}.`); setRejecting(false); refresh() },
    onError: (e) => toast((e as Error).message, 'fail'),
  })
  const close = useMutation({ mutationFn: () => post(`/api/listings/${r.opp_id}/close`, {}), onSuccess: () => { toast('Closed.'); refresh() }, onError: (e) => toast((e as Error).message, 'fail') })
  const approve = async () => {
    if (reds > 0 && !(await confirm({ title: 'Approve despite red flags?', body: 'This listing has red flags. Are you sure it is safe for students?', confirmLabel: 'Approve anyway', danger: true }))) return
    review.mutate('approve')
  }
  return (
    <article className="card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><div className="flex flex-wrap items-center gap-2 text-sm text-ink-soft"><ListingStatusBadge status={r.status} /><span className="font-mono text-xs">{r.opp_id}</span>{r.edited_since_review && <Badge tone="sky">Edited since last review</Badge>}</div>
          <h2 className="mt-1.5 !text-xl">{f.title}</h2><p className="text-sm text-ink-soft">{f.org_name} · posted by {r.owner}</p></div>
        {canAct && r.status !== 'closed' && r.status !== 'pending' && <button type="button" className="btn btn-quiet" onClick={() => close.mutate()}>Close it</button>}
      </div>
      {r.flags.length > 0 ? (
        <ul className="mt-3 space-y-1.5" aria-label="Things to check">
          {r.flags.map((x, i) => <li key={i} className={`flex items-start gap-2 rounded-md border px-3 py-1.5 text-sm ${x.level === 'red' ? 'border-fail-line bg-fail-soft text-fail' : 'border-amber-line bg-amber-soft text-amber'}`}>
            {x.level === 'red' ? <OctagonAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> : <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />}<span><strong className="font-semibold">{x.level === 'red' ? 'Red flag.' : 'Check.'}</strong> {x.text}</span></li>)}
        </ul>
      ) : <p className="mt-3 flex items-center gap-1.5 text-sm text-pass"><Check className="h-4 w-4" aria-hidden />No flags found.</p>}
      <dl className="mt-3 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
        {([['Kind', f.type], ['Where', f.mode === 'remote' ? 'Remote' : `${f.city} (${f.mode})`], ['Pay', f.pay_text || 'Not given'], ['Cost to student', f.upfront_cost_text || '0'],
          ['Hours a week', f.hours_per_week], ['Night shift', f.night_shift ? 'Yes' : 'No'], ['Languages', f.languages.join(', ')], ['Openings', f.openings]] as [string, string | number][]).map(([k, v]) => (
          <div key={k} className="flex justify-between gap-3 border-b border-dotted border-line-strong py-1"><dt className="text-ink-soft">{k}</dt><dd className="font-medium">{v}</dd></div>))}
      </dl>
      {f.apply_by && <p className="mt-2 text-sm"><span className="text-ink-soft">Last day to apply:</span> {f.apply_by}</p>}
      {f.description && <p className="mt-3 max-w-[75ch] text-sm">{f.description}</p>}
      <p className="mt-3 text-sm"><span className="text-ink-soft">Skills asked for:</span> {f.required_skills_text} <span className="text-ink-faint">({r.mapped_skills} found in the skill list)</span></p>
      {r.review_note && r.status !== 'pending' && <p className="mt-2 rounded-md bg-bg px-3 py-2 text-sm"><strong className="font-medium">Review note:</strong> {r.review_note}{r.reviewed_by && <span className="text-ink-faint"> ({r.reviewed_by})</span>}</p>}

      {r.status === 'pending' && canAct && (
        <div className="mt-4 space-y-3 border-t border-line pt-4">
          <div className="grid gap-3 sm:grid-cols-[160px_1fr]">
            <div><label className="label" htmlFor={`s-${r.opp_id}`}>Safety score</label>
              <select id={`s-${r.opp_id}`} className="input" value={score} onChange={(e) => setScore(Number(e.target.value))}>{[5, 4, 3, 2, 1].map((n) => <option key={n} value={n}>{n} of 5{n === 5 ? ' (safest)' : n === 1 ? ' (least safe)' : ''}</option>)}</select></div>
            <div><label className="label" htmlFor={`n-${r.opp_id}`}>{rejecting ? 'Why not (required)' : 'Note to the employer (optional)'}</label>
              <input id={`n-${r.opp_id}`} className="input" value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} placeholder={rejecting ? 'Say what to fix' : 'Anything they should know'} /></div>
          </div>
          {!rejecting && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={tell} onChange={(e) => setTell(e.target.checked)} />When it goes live, tell the students it fits best on WhatsApp (only those who agreed)</label>}
          <div className="flex flex-wrap gap-2">
            {!rejecting && <button type="button" className="btn btn-primary" disabled={review.isPending} onClick={approve}><Check className="h-4 w-4" aria-hidden />Approve</button>}
            {!rejecting ? <button type="button" className="btn" onClick={() => setRejecting(true)}><X className="h-4 w-4" aria-hidden />Reject</button>
              : <><button type="button" className="btn btn-danger" disabled={!note.trim() || review.isPending} onClick={() => review.mutate('reject')}>Reject and tell the employer</button><button type="button" className="btn btn-quiet" onClick={() => setRejecting(false)}>Cancel</button></>}
          </div>
        </div>
      )}
      <p className="mt-3 text-xs text-ink-faint">Last updated {r.updated_at.slice(0, 10)}.</p>
    </article>
  )
}
