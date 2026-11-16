import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Check, FileText, Megaphone, Pencil, Trophy, XCircle } from 'lucide-react'
import { get, post } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { payText, rupees, TYPE_WORD, whereText } from '../../lib/format'
import { PROGRAM_WORD, type OpportunityDetail as Detail } from '../../lib/types'
import { Badge, Banner, Empty, ErrorState, Fold, KV, Meter, PageHeader, Section, Spinner } from '../../components/ui'
import { ApplyBy } from '../../components/Deadline'
import { useConfirm } from '../../components/Confirm'
import { useToast } from '../../components/Toast'

const REMOVED_WORD: Record<string, string> = {
  location: 'cannot or will not move there',
  budget: 'cannot afford the upfront cost',
  language: 'do not speak a required language',
  family: 'have a family limit it breaks (night shift, safety or distance)',
}

export default function OpportunityDetail() {
  const params = useParams()
  const oid = params.oid
  const nav = useNavigate()
  const qc = useQueryClient()
  const confirm = useConfirm()
  const toast = useToast()
  const { user } = useAuth()
  const admin = user?.role === 'ngo_admin'
  const q = useQuery({ queryKey: ['opportunity', oid], queryFn: () => get<Detail>(`/api/opportunities/${oid}`) })
  const o = q.data
  const posted = !!oid && oid.startsWith('E')
  const close = useMutation({
    mutationFn: () => post(`/api/listings/${oid}/close`, {}),
    onSuccess: () => { toast('Closed. Students no longer see it.'); qc.invalidateQueries({ queryKey: ['opportunities'] }); nav('/ngo/opportunities') },
    onError: (e) => toast((e as Error).message, 'fail'),
  })
  const askClose = async () => { if (await confirm({ title: 'Close this listing?', body: 'Students will no longer see it, and the employer is told.', confirmLabel: 'Close listing', danger: true })) close.mutate() }

  return (
    <>
      <PageHeader title={o?.title ?? 'Opportunity'} sub={o ? `${o.org_name} · ${TYPE_WORD[o.type]} · ${whereText(o.city, o.mode)}. These are the students who fit best, after the hard checks.` : 'Loading the listing.'}
        actions={<div className="flex flex-wrap gap-2">
          {admin && o && <Link to={`/ngo/messages?tab=bulk&opp=${oid}`} className="btn"><Megaphone className="h-4 w-4" aria-hidden />Tell best-fit students</Link>}
          {admin && posted && <Link to={`/ngo/opportunities/${oid}/edit`} className="btn"><Pencil className="h-4 w-4" aria-hidden />Edit</Link>}
          {admin && posted && <button type="button" className="btn" onClick={askClose} disabled={close.isPending}><XCircle className="h-4 w-4" aria-hidden />Close</button>}
          <Link to={`/ngo/messages?thread=listing:${oid}`} className="btn">Message employer</Link>
          <Link to="/ngo/opportunities" className="btn"><ArrowLeft className="h-4 w-4" aria-hidden />All listings</Link></div>} />
      <div className="px-8 pb-16">
        {q.isLoading && <div className="pt-6"><Spinner /></div>}
        {q.error && <div className="pt-6"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>}
        {o && (
          <>
            <Section title="Listing details">
              <div className="space-y-3">
                {o.type === 'job' && o.upfront_cost > 0 && <Banner tone="fail" lead="Red flag.">This job asks for {rupees(o.upfront_cost)} up front. Real employers do not charge a deposit to hire.</Banner>}
                {o.night_shift && <Banner tone="amber" lead="Night shifts.">Students with a no-night-shift limit are not shown below.</Banner>}
                {o.safety_score <= 2 && <Banner tone="amber" lead="Low safety score.">This listing scores {o.safety_score} out of 5, so students who need a safe workplace are not shown below.</Banner>}
                <div className="card p-5">
                  <KV items={[
                    ['Listing id', <span className="font-mono text-xs">{o.opp_id}</span>],
                    ['Type', TYPE_WORD[o.type]],
                    ['Where', whereText(o.city, o.mode)],
                    ['Pay', payText(o.pay_min, o.pay_max) ?? 'Not disclosed'],
                    ['Cost to join', o.upfront_cost > 0 ? rupees(o.upfront_cost) : 'Free'],
                    ['Hours a week', o.hours_per_week],
                    ['Night shift', o.night_shift ? 'Yes' : 'No'],
                    ['Safety', `${o.safety_score} of 5`],
                    ['Languages', o.languages_required.join(', ') || 'None listed'],
                    ['Last day to apply', o.apply_by ? <ApplyBy date={o.apply_by} /> : 'Open until closed'],
                    ...(o.type === 'training' && o.starts_on ? [['Next batch', `${o.starts_on}${o.duration_weeks ? `, ${o.duration_weeks} weeks` : ''}${o.batch_every_weeks ? `, every ${o.batch_every_weeks} weeks` : ''}`] as [string, string]] : []),
                  ]} />
                  <h3 className="mb-2 mt-4 text-ink-soft">Skills asked for</h3>
                  <div className="flex flex-wrap gap-1.5">{o.skills.map((s) => <Badge key={s} tone="accent">{s}</Badge>)}</div>
                </div>
              </div>
            </Section>

            <Section title="Best-fit students" right={<span className="text-sm text-ink-soft">{o.eligible_count} of {o.total_students} can take this</span>}>
              {o.candidates.length === 0 && <Empty title="No student fits yet">Every student is removed by a hard check. See the list below to find out why.</Empty>}
              <div className="space-y-3">
                {o.candidates.map((c, i) => (
                  <article key={c.student_id} className={`card p-4 ${i === 0 ? 'settle shadow-lift' : 'pop'}`}>
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div>
                        <div className="flex items-center gap-2 text-sm">
                          <span className="font-mono text-xs text-ink-faint">#{i + 1}</span>
                          <span className="font-mono text-xs">{c.student_id}</span>
                          <Badge tone={c.program === 'get_skills' ? 'plum' : 'navy'}>{PROGRAM_WORD[c.program]}</Badge>
                          <span className="font-medium">{c.branch}</span>
                          <span className="text-ink-soft">· {c.college || c.town} · CGPA {c.cgpa ?? 'not known'}</span>
                        </div>
                        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
                          {c.overlap.map((s) => <Badge key={s} tone="accent"><Check className="h-3 w-3" aria-hidden />{s}</Badge>)}
                          {c.missing.map((s) => <Badge key={s} tone="neutral">Missing {s}</Badge>)}
                          {c.needs_move && <Badge tone="sky">Would move</Badge>}
                          {c.concerns.map((s) => <Badge key={s} tone="amber">{s}</Badge>)}
                          {c.standing && <Badge tone="neutral"><Trophy className="h-3 w-3" aria-hidden />{c.standing.rank} of {c.standing.of}</Badge>}
                          {c.ats != null && <Badge tone="sky"><FileText className="h-3 w-3" aria-hidden />Resume {c.ats}</Badge>}
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        <div className="w-28 text-right"><div className="font-serif text-xl">{c.final_score.toFixed(2)}</div><Meter value={c.final_score} label="Fit score" /></div>
                        {(
                          <div className="flex gap-1">
                            <Link className="btn" to={`/ngo/students/${c.student_id}`}>Open student</Link>
                          </div>
                        )}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </Section>

            {Object.keys(o.removed_by).length > 0 && (
              <Section title="Who was left out">
                <Fold title="Students removed by the hard checks">
                  <ul className="space-y-1.5 text-sm">
                    {Object.entries(o.removed_by).map(([k, n]) => (
                      <li key={k}><strong>{n}</strong> students {REMOVED_WORD[k] ?? k}.</li>
                    ))}
                  </ul>
                  <p className="mt-2 text-xs text-ink-faint">A student can fail more than one check, so these counts can add up to more than the total.</p>
                </Fold>
              </Section>
            )}
          </>
        )}
      </div>
    </>
  )
}
