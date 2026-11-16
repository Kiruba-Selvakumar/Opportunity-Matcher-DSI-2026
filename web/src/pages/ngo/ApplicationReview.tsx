import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Check, Send, X } from 'lucide-react'
import { get, post } from '../../lib/api'
import { useApp } from '../../lib/app-context'
import { useAuth } from '../../lib/auth'
import { payText, rupees, TYPE_WORD, whereText } from '../../lib/format'
import { PROGRAM_WORD, type ReviewBundle } from '../../lib/types'
import { Badge, Banner, Empty, ErrorState, KV, PageHeader, Section, Spinner } from '../../components/ui'
import { AtsForListing, ResumeViewer } from '../../components/Resume'
import { ApplyBy } from '../../components/Deadline'
import { useToast } from '../../components/Toast'
import { StatusPill } from '../student/StatusPill'
import { BreakdownFold } from './Match'

const CHECK_TONE = { pass: 'pass', unknown: 'amber', fail: 'fail' } as const

/** Before a student is shared: the listing and the match on one side, the student's resume on the other. */
export default function ApplicationReview() {
  const { id = '' } = useParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const toast = useToast()
  const { user } = useAuth()
  const { showNames } = useApp()
  const admin = user?.role === 'ngo_admin'
  const [note, setNote] = useState('')
  const [declining, setDeclining] = useState(false)
  const q = useQuery({ queryKey: ['app-review', id], queryFn: () => get<ReviewBundle>(`/api/applications/${id}/review`) })
  const done = (msg: string) => { toast(msg); ['ngo-applications', 'dashboard'].forEach((k) => qc.invalidateQueries({ queryKey: [k] })); nav('/ngo/applications?tab=approve') }
  const move = useMutation({ mutationFn: (status: string) => post(`/api/applications/${id}/status`, { status, note }), onSuccess: (_, s) => done(s === 'shared' ? 'Shared. The employer was told by email and in the app.' : 'Declined. The student will see your reason.'), onError: (e) => toast((e as Error).message, 'fail') })
  const forward = useMutation({ mutationFn: () => post(`/api/applications/${id}/recommend`, { note }), onSuccess: () => done('Put forward. An admin will check and share.'), onError: (e) => toast((e as Error).message, 'fail') })

  const b = q.data
  const a = b?.application
  const o = b?.listing
  const s = b?.student
  return (
    <>
      <PageHeader title={o ? `${o.title}: check before sharing` : 'Check before sharing'}
        sub="Read the resume beside the listing. Share the student with the employer only when the fit is real. Employers see the candidate code and skills, never the resume or the name."
        actions={<Link to="/ngo/applications" className="btn"><ArrowLeft className="h-4 w-4" aria-hidden />Applications</Link>} />
      <div className="px-4 pb-24 sm:px-8">
        {q.isLoading && <div className="pt-6"><Spinner /></div>}
        {q.error && <div className="pt-6"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>}
        {b && a && o && s && (
          <div className="grid gap-6 pt-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <div className="min-w-0 space-y-2">
              <div className="card p-4 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusPill status={a.status} />
                  <Link to={`/ngo/students/${a.student_id}`} className="font-mono text-xs underline">{a.student_id}</Link>
                  {showNames && a.name && <span className="font-medium">{a.name}</span>}
                  {s.program && <Badge tone={s.program === 'get_skills' ? 'plum' : 'navy'}>{PROGRAM_WORD[s.program]}</Badge>}
                  <span className="text-ink-soft">{s.branch} · {s.college || s.college_town} · CGPA {s.cgpa ?? 'not known'}</span>
                </div>
                {a.student_note && <p className="mt-2 text-ink-soft">Student wrote: “{a.student_note}”</p>}
                {a.recommended_by && <p className="mt-1 text-ink-soft">Put forward by {a.recommended_by}{a.ngo_note ? `: “${a.ngo_note}”` : '.'}</p>}
              </div>

              <Section title="The listing">
                <div className="card p-4">
                  <p className="text-sm text-ink-soft">{o.org_name} · {TYPE_WORD[o.type] ?? o.type} · {whereText(o.city, o.mode)} <ApplyBy date={o.apply_by} /></p>
                  <KV items={[['Pay', payText(o.pay_min, o.pay_max) ?? 'Not disclosed'], ['Cost to join', o.upfront_cost > 0 ? rupees(o.upfront_cost) : 'Free'], ['Hours a week', o.hours_per_week], ['Safety', `${o.safety_score} of 5`]]} />
                  {o.description && <p className="mt-3 max-w-[75ch] text-sm">{o.description}</p>}
                  <div className="mt-3 flex flex-wrap gap-1.5 text-xs">{(o.skills ?? []).map((k) => <Badge key={k} tone={o.nice?.includes(k) ? 'neutral' : 'accent'}>{k}{o.nice?.includes(k) ? ' (nice to have)' : ''}</Badge>)}</div>
                </div>
              </Section>

              <Section title="The match">
                {b.match ? (
                  <div className="card space-y-3 p-4">
                    <div className="flex flex-wrap items-baseline gap-3"><span className="font-serif text-2xl">{b.match.final_score.toFixed(2)}</span>{a.fit && <Badge tone="sky">{a.fit}</Badge>}{b.match.standing && <span className="text-sm text-ink-soft">Ranks {b.match.standing.rank} of {b.match.standing.of} students it fits</span>}</div>
                    <div className="flex flex-wrap gap-1.5 text-xs">{Object.entries(b.match.checks).map(([k, c]) => <Badge key={k} tone={CHECK_TONE[c.status]}>{k}: {c.note || c.status}</Badge>)}</div>
                    <div className="flex flex-wrap gap-1.5 text-xs">{b.match.overlap.map((k) => <Badge key={k} tone="accent"><Check className="h-3 w-3" aria-hidden />{k}</Badge>)}{b.match.missing.map((k) => <Badge key={k} tone="neutral">Missing {k}</Badge>)}</div>
                    <BreakdownFold b={b.match} />
                  </div>) : <Banner tone="amber" lead="No live match.">This listing is not live any more, so there is no score.</Banner>}
              </Section>

              <Section title="The resume, read against this listing"><div className="card p-4"><AtsForListing a={b.ats} /></div></Section>
            </div>

            <div className="min-w-0 pt-2 xl:sticky xl:top-4 xl:self-start">
              {a.has_resume ? <ResumeViewer src={`/api/students/${a.student_id}/resume.pdf`} height={900} />
                : <Empty title="No resume on file">Ask the student to add one from their profile, or <Link to={`/ngo/students/${a.student_id}?tab=resume`} className="underline">upload it</Link>.</Empty>}
            </div>
          </div>
        )}
      </div>

      {a && a.status === 'interested' && (
        <div className="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-surface/95 px-4 py-3 backdrop-blur lg:left-[232px] sm:px-8">
          <div className="flex flex-wrap items-center gap-2">
            <label className="sr-only" htmlFor="rv-note">Note</label>
            <input id="rv-note" className="input max-w-md" value={note} maxLength={500} onChange={(e) => setNote(e.target.value)}
              placeholder={declining ? 'Why not? The student will read this' : admin ? 'Note for the record (optional)' : 'Why they fit (the admin reads this)'} />
            {admin && !declining && <button type="button" className="btn btn-primary" disabled={move.isPending} onClick={() => move.mutate('shared')}><Send className="h-4 w-4" aria-hidden />Share with the employer</button>}
            {!admin && a.can_recommend && !declining && <button type="button" className="btn btn-primary" disabled={forward.isPending} onClick={() => forward.mutate()}>Put forward</button>}
            {!declining ? <button type="button" className="btn" onClick={() => setDeclining(true)}><X className="h-4 w-4" aria-hidden />Decline</button>
              : <><button type="button" className="btn btn-danger" disabled={!note.trim() || move.isPending} onClick={() => move.mutate('declined')}>Decline and tell the student</button><button type="button" className="btn btn-quiet" onClick={() => setDeclining(false)}>Cancel</button></>}
          </div>
        </div>
      )}
    </>
  )
}
