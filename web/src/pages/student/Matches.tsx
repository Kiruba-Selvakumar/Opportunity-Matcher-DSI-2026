import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Bookmark, BookmarkCheck, Check, Clock, FileText, GraduationCap, HandHeart, MapPin, Moon, TrendingUp, Trophy, Wallet } from 'lucide-react'
import { get } from '../../lib/api'
import { cn } from '../../lib/utils'
import { payText, rupees, TYPE_WORD, whereForYou } from '../../lib/format'
import type { Match, ProfilePayload, StudentSelf } from '../../lib/types'
import { Badge, Banner, ErrorState, PageHeader, Section } from '../../components/ui'
import { CardsSkeleton } from '../../components/Skeleton'
import { StatusPill } from './StatusPill'
import { ApplyBy } from '../../components/Deadline'
import { LearningPlanView } from '../../components/LearningPlan'
import { LIVE_STATUSES, useListingActions } from './useListingActions'

const FIT_TONE: Record<string, 'pass' | 'sky' | 'amber' | 'neutral'> = { 'Strong fit': 'pass', 'Good fit': 'sky', Stretch: 'amber', 'Possible fit': 'neutral' }

export default function Matches() {
  const me = useQuery({ queryKey: ['me-student'], queryFn: () => get<StudentSelf>('/api/me/student') })
  const prof = useQuery({ queryKey: ['me-profile'], queryFn: () => get<ProfilePayload>('/api/me/profile') })
  const p = me.data?.profile
  const hello = me.data?.name ? `Hi ${me.data.name.split(' ')[0]}, here are your matches` : 'Your matches'
  const incomplete = prof.data && prof.data.completeness.percent < 100 ? prof.data.completeness : null

  return (
    <>
      <PageHeader title={hello} sub="These are the opportunities picked for you, and why. Your placement officer makes the final call." />
      <div className="px-4 pb-16 sm:px-8">
        {me.error && <div className="pt-6"><ErrorState error={me.error} onRetry={() => me.refetch()} /></div>}
        {me.isLoading && <div className="pt-6"><CardsSkeleton n={3} /></div>}
        {p && me.data && (
          <>
            {incomplete && (
              <div className="pt-6">
                <Banner tone="sky" lead={`Your profile is ${incomplete.percent}% complete.`} icon={HandHeart}>
                  {incomplete.items.find((i) => !i.done && i.impact > 0)
                    ? `${incomplete.items.find((i) => !i.done && i.impact > 0)!.impact} matches are marked "check" because we do not know ${incomplete.items.find((i) => !i.done && i.impact > 0)!.label.toLowerCase()}. `
                    : 'A few answers will make your matches more accurate. '}
                  <Link to="/student/profile" className="underline">Finish your profile</Link>
                </Banner>
              </div>
            )}
            <Section title="Opportunities for you">
              {me.data.matches.length === 0 && (
                <div className="card max-w-[75ch] space-y-2 p-5 text-sm">
                  <h3 className="text-base">No strong match yet</h3>
                  {me.data.eligible_total === 0
                    ? <p className="text-ink-soft">Nothing is open to you right now because of where you can work or what you can spend. If that has changed, <Link to="/student/profile" className="underline">update your profile</Link> and this page updates at once.</p>
                    : <p className="text-ink-soft">{me.data.eligible_total} listing{me.data.eligible_total === 1 ? ' is' : 's are'} open to you, but none fit your skills strongly yet. <Link to="/student/browse" className="underline">Browse them all</Link>, <Link to="/student/profile" className="underline">add the skills you have</Link>, or look at the training in your matches to build new ones.</p>}
                  <p className="text-ink-soft">Your placement officer can also help. <Link to="/student/messages" className="underline">Send them a message</Link>.</p>
                </div>)}
              {me.data.matches.length > 0 && me.data.matches.length < 5 && <p className="mb-3 max-w-[75ch] text-xs text-ink-faint">We only show matches that are a real fit, so there are {me.data.matches.length === 1 ? 'only 1' : `${me.data.matches.length}`} here. <Link to="/student/browse" className="underline">Browse</Link> lists everything that is open to you.</p>}
              <div className="space-y-4">{me.data.matches.map((m, i) => <MatchCard key={m.opp_id} m={m} town={p.college_town} first={i === 0} />)}</div>
            </Section>
            <Section title="Your learning plan">
              <p className="mb-4 max-w-[75ch] text-sm text-ink-soft">Courses and mentors that teach what your best jobs ask for, one after another: what they do for each job, and whether you would be ready before its last day to apply.</p>
              <LearningPlanView path="/api/me/plan" forStudent />
            </Section>
            {me.data.why_not.length > 0 && (
              <Section title="Options we left out, and why">
                <ul className="max-w-[75ch] space-y-1.5 text-sm text-ink-soft">
                  {me.data.why_not.map((w) => <li key={w.opp_id}><strong className="font-medium text-ink">{w.title}</strong> in {w.city}: {w.fails.map((f) => f.note).join('; ')}.</li>)}
                </ul>
                <p className="mt-3 text-sm text-ink-soft">If something here has changed, <Link to="/student/profile" className="underline">update your profile</Link> and your matches update at once.</p>
              </Section>
            )}
          </>
        )}
      </div>
    </>
  )
}

function MatchCard({ m, town, first }: { m: Match; town: string; first: boolean }) {
  const { interest, save } = useListingActions()
  const [asking, setAsking] = useState(false)
  const [note, setNote] = useState('')
  const pay = payText(m.pay_min, m.pay_max)
  const app = m.application
  const live = app && LIVE_STATUSES.includes(app.status)

  return (
    <article className={cn('card p-5', first ? 'settle-2 shadow-lift' : 'pop')}>
      <div className="flex flex-wrap items-center gap-2 text-sm text-ink-soft">
        <Badge tone={FIT_TONE[m.fit] ?? 'neutral'}>{m.fit || 'Match'}</Badge>
        <Badge tone="neutral">{TYPE_WORD[m.type]}</Badge>
        {app && <StatusPill status={app.status} />}
        {m.crowded && <Badge tone="amber">Many students have applied</Badge>}
        <ApplyBy date={m.apply_by} />
      </div>
      <h2 className="mt-2 !text-xl"><Link to={`/student/browse/${m.opp_id}`} className="underline decoration-line-strong underline-offset-4 hover:decoration-ink">{m.title}</Link></h2>
      <p className="text-sm text-ink-soft">{m.org_name}</p>
      <p className="mt-3 max-w-[75ch]">{m.headline || m.reason}</p>
      <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink-soft">
        <li className="inline-flex items-center gap-1.5"><MapPin className="h-3.5 w-3.5" aria-hidden />{whereForYou(m.city, m.mode, town)}</li>
        <li className="inline-flex items-center gap-1.5"><Wallet className="h-3.5 w-3.5" aria-hidden />{m.upfront_cost > 0 ? `Costs ${rupees(m.upfront_cost)}` : 'Free to join'}{pay ? `, pays about ${pay}` : ''}</li>
        <li className="inline-flex items-center gap-1.5"><Clock className="h-3.5 w-3.5" aria-hidden />{m.hours_per_week} hours a week</li>
        {m.night_shift && <li className="inline-flex items-center gap-1.5"><Moon className="h-3.5 w-3.5" aria-hidden />Includes night shifts</li>}
      </ul>
      {m.overlap.length > 0 && <p className="mt-3 flex flex-wrap items-center gap-1.5 text-xs text-ink-soft">You already have:{m.overlap.map((s) => <Badge key={s} tone="accent"><Check className="h-3 w-3" aria-hidden />{s}</Badge>)}</p>}
      {m.related.length > 0 && <p className="mt-2 text-xs text-ink-soft">{m.related.filter((r) => r.credit >= 0.5).map((r) => `Your ${r.have} counts for part of ${r.need}.`).join(' ')}</p>}
      {m.missing.length > 0 && <p className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-ink-soft">To be a stronger fit, learn:{m.missing.map((s) => <Badge key={s} tone="amber">{s}</Badge>)}</p>}
      {m.standing && m.standing.of >= 5 && m.standing.rank / m.standing.of <= 0.25 && <p className="mt-2 inline-flex items-center gap-1.5 text-xs text-pass"><Trophy className="h-3.5 w-3.5" aria-hidden />You are among the strongest of the {m.standing.of} students this fits.</p>}
      {(m.upskill?.steps.filter((x) => x.ease >= 0.5).length ?? 0) > 0 && <p className="mt-2 inline-flex items-center gap-1.5 text-xs text-ink-soft"><TrendingUp className="h-3.5 w-3.5" aria-hidden />Within easy reach: {m.upskill!.steps.filter((x) => x.ease >= 0.5).map((x) => x.from ? `${x.skill}, since you know ${x.from}` : `${x.skill}, from ${x.via?.title}`).join('; ')}.</p>}
      {m.ats && m.ats.keywords_missing.length > 0 && <p className="mt-2 inline-flex items-center gap-1.5 text-xs text-ink-soft"><FileText className="h-3.5 w-3.5" aria-hidden />Your resume does not mention {m.ats.keywords_missing.join(', ')}. If you know {m.ats.keywords_missing.length === 1 ? 'it' : 'them'}, add {m.ats.keywords_missing.length === 1 ? 'it' : 'them'}.</p>}
      {m.gap_closers.length > 0 && (
        <div className="mt-3 rounded-lg border border-pear-line bg-pear-soft px-3 py-2 text-sm">
          <div className="flex items-center gap-1.5 font-medium text-ink"><GraduationCap className="h-4 w-4" aria-hidden />Close the gap</div>
          <ul className="mt-1 space-y-0.5 text-ink-soft">{m.gap_closers.map((g) => <li key={g.opp_id}>{g.title} teaches {g.covers.join(', ')}{g.cost > 0 ? ` (costs ${rupees(g.cost)})` : ' (free)'}.</li>)}</ul>
        </div>
      )}
      {m.warnings.length > 0 && <p className="mt-2 text-xs text-amber">Check with your officer: {m.warnings.map((w) => w.split(': ')[1]).join(', ')}.</p>}
      {app && <p className="mt-3 text-sm text-ink-soft">{app.words} <Link to="/student/applications" className="underline">See the steps</Link></p>}

      {!live && (
        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-line pt-3">
          {!asking && <button type="button" className="btn btn-primary" onClick={() => setAsking(true)}>I'm interested</button>}
          <button type="button" className="btn" onClick={() => save.mutate({ oppId: m.opp_id, saved: !!m.saved })} disabled={save.isPending} aria-pressed={!!m.saved}>
            {m.saved ? <BookmarkCheck className="h-4 w-4" aria-hidden /> : <Bookmark className="h-4 w-4" aria-hidden />}{m.saved ? 'Saved' : 'Save'}
          </button>
        </div>
      )}
      {asking && (
        <form className="pop mt-3 space-y-2 rounded-lg bg-bg p-3" onSubmit={(e) => { e.preventDefault(); interest.mutate({ oppId: m.opp_id, note }, { onSuccess: () => { setAsking(false); setNote('') } }) }}>
          <label className="label" htmlFor={`n-${m.opp_id}`}>Tell the NGO why (optional)</label>
          <textarea id={`n-${m.opp_id}`} className="input min-h-[70px]" maxLength={500} value={note} autoFocus onChange={(e) => setNote(e.target.value)} placeholder="For example: I did a project with these tools." />
          <div className="flex gap-2"><button type="submit" className="btn btn-primary" disabled={interest.isPending}>{interest.isPending ? 'Sending' : 'Send to the NGO'}</button><button type="button" className="btn btn-quiet" onClick={() => setAsking(false)}>Cancel</button></div>
        </form>
      )}
    </article>
  )
}
