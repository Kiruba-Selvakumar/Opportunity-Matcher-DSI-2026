import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Bookmark, BookmarkCheck, Check, GraduationCap, MessageSquare, SearchX } from 'lucide-react'
import { ApiError, get } from '../../lib/api'
import { dateWords, payText, rupees, TYPE_WORD, whereForYou } from '../../lib/format'
import type { StudentListing, StudentSelf } from '../../lib/types'
import { Badge, Banner, Empty, ErrorState, KV, PageHeader, Section, Spinner } from '../../components/ui'
import { ApplyBy } from '../../components/Deadline'
import { StatusPill } from './StatusPill'
import { LIVE_STATUSES, useListingActions } from './useListingActions'

const FIT_TONE: Record<string, 'pass' | 'sky' | 'amber' | 'neutral'> = { 'Strong fit': 'pass', 'Good fit': 'sky', Stretch: 'amber', 'Possible fit': 'neutral' }

/** One listing in full, so a student can read it before showing interest. */
export default function ListingDetail() {
  const { oppId = '' } = useParams()
  const q = useQuery({ queryKey: ['listing', oppId], queryFn: () => get<StudentListing>(`/api/me/browse/${oppId}`), retry: false })
  const me = useQuery({ queryKey: ['me-student'], queryFn: () => get<StudentSelf>('/api/me/student') })
  const o = q.data
  const back = <Link to="/student/browse" className="btn whitespace-nowrap"><ArrowLeft className="h-4 w-4" aria-hidden />All listings</Link>

  if (q.error instanceof ApiError && q.error.status === 404) {
    return (
      <>
        <PageHeader title="Listing not open" sub="This listing has closed or is not published." actions={back} />
        <Empty icon={SearchX} title="This listing is not open">It may have been filled or closed. <Link to="/student/browse" className="underline">Browse</Link> shows everything that is open now.</Empty>
      </>
    )
  }
  return (
    <>
      <PageHeader title={o?.title ?? 'Listing'} sub={o ? `${o.org_name} · ${TYPE_WORD[o.type]}` : 'Loading the listing.'} actions={back} />
      <div className="px-4 pb-16 sm:px-8">
        {q.isLoading && <div className="pt-6"><Spinner /></div>}
        {q.error && <div className="pt-6"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>}
        {o && <Body o={o} town={me.data?.profile.college_town ?? ''} />}
      </div>
    </>
  )
}

function Body({ o, town }: { o: StudentListing; town: string }) {
  const pay = payText(o.pay_min, o.pay_max)
  const have = new Set(o.overlap)
  const learn = new Set(o.missing)
  const plus = new Set(o.nice)
  const where = town ? whereForYou(o.city, o.mode, town) : o.city
  return (
    <>
      <div className="flex flex-wrap items-center gap-2 pt-6 text-sm">
        <Badge tone={FIT_TONE[o.fit] ?? 'neutral'}>{o.fit}</Badge>
        {o.application && <StatusPill status={o.application.status} />}
        {o.crowded && <Badge tone="amber">Many students have applied</Badge>}
        <ApplyBy date={o.apply_by} />
      </div>
      <div className="mt-4 space-y-3">
        {!o.eligible && (
          <Banner tone="fail" lead="You cannot take this one right now.">
            {o.blockers.join('; ')}. If something has changed, <Link to="/student/profile" className="underline">update your profile</Link>.
          </Banner>
        )}
        {o.eligible && o.checks.length > 0 && <Banner tone="amber" lead="Check with your officer.">{o.checks.join('; ')}.</Banner>}
      </div>

      <Section title="About the role">
        <p className="max-w-[75ch]">{o.description || <span className="text-ink-soft">The employer has not added a description yet. Ask the NGO if you want to know more.</span>}</p>
      </Section>

      <Section title="What it asks for">
        <ul className="flex flex-wrap gap-1.5" aria-label="Skills it asks for">
          {o.skills.map((s) => (
            <li key={s}>
              <Badge tone={have.has(s) ? 'accent' : learn.has(s) ? 'amber' : 'neutral'}>
                {have.has(s) && <Check className="h-3 w-3" aria-hidden />}{s}
                <span className="sr-only">{have.has(s) ? ', you have this' : learn.has(s) ? ', to learn' : ''}</span>
                {plus.has(s) && <span className="font-normal">· is a plus</span>}
              </Badge>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-ink-soft">
          {o.missing.length === 0 ? 'You already have every skill it asks for.' : `You have ${o.overlap.length} of the ${o.skills.length}. The ones in amber are the ones to learn.`}
        </p>
        {o.related.length > 0 && <p className="mt-1 text-xs text-ink-soft">{o.related.map((r) => `Your ${r.have} counts for part of ${r.need}.`).join(' ')}</p>}
        {o.type === 'training' && o.teaches.length > 0 && <p className="mt-2 text-sm">Teaches {o.teaches.join(', ')}, which the jobs that fit you best ask for.</p>}
        {o.gap_closers.length > 0 && (
          <div className="mt-3 rounded-lg border border-pear-line bg-pear-soft px-3 py-2 text-sm">
            <div className="flex items-center gap-1.5 font-medium text-ink"><GraduationCap className="h-4 w-4" aria-hidden />Close the gap</div>
            <ul className="mt-1 space-y-0.5 text-ink-soft">
              {o.gap_closers.map((g) => <li key={g.opp_id}><Link to={`/student/browse/${g.opp_id}`} className="underline">{g.title}</Link> teaches {g.covers.join(', ')}{g.cost > 0 ? ` (costs ${rupees(g.cost)})` : ' (free)'}.</li>)}
            </ul>
          </div>
        )}
      </Section>

      <Section title="The practical side">
        <div className="card p-5">
          <KV items={[
            ['Where', where],
            [o.type === 'job' ? 'Pay' : 'Cost', o.type === 'job' ? (pay ? `About ${pay}` : 'Not given') : (o.upfront_cost > 0 ? rupees(o.upfront_cost) : 'Free')],
            ...(o.type === 'job' ? [['Cost to join', o.upfront_cost > 0 ? rupees(o.upfront_cost) : 'Free'] as [string, string]] : []),
            ['Hours a week', String(o.hours_per_week)],
            ['Night shifts', o.night_shift ? 'Yes' : 'No'],
            ['Languages', o.languages_required.join(', ') || 'None listed'],
            ['Openings', String(o.openings)],
            ...(o.apply_by ? [['Apply by', dateWords(o.apply_by)] as [string, string]] : []),
            ...(o.type === 'training' && o.starts_on
              ? [['Next batch', `${dateWords(o.starts_on)}${o.duration_weeks ? `, ${o.duration_weeks} weeks` : ''}`] as [string, string]] : []),
          ]} />
        </div>
      </Section>

      <Actions o={o} />
    </>
  )
}

function Actions({ o }: { o: StudentListing }) {
  const { interest, save } = useListingActions()
  const [asking, setAsking] = useState(false)
  const [note, setNote] = useState('')
  const live = o.application && LIVE_STATUSES.includes(o.application.status)
  return (
    <div className="sticky bottom-0 z-10 -mx-4 mt-6 border-t border-line bg-bg/95 px-4 py-3 backdrop-blur sm:-mx-8 sm:px-8">
      {live ? (
        <p className="text-sm text-ink-soft">{o.application?.words} <Link to="/student/applications" className="underline">See the steps</Link></p>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          {!asking && <button type="button" className="btn btn-primary" disabled={!o.eligible} title={o.eligible ? undefined : o.blockers.join('; ')} onClick={() => setAsking(true)}>I'm interested</button>}
          <button type="button" className="btn" onClick={() => save.mutate({ oppId: o.opp_id, saved: o.saved })} disabled={save.isPending} aria-pressed={o.saved}>
            {o.saved ? <BookmarkCheck className="h-4 w-4" aria-hidden /> : <Bookmark className="h-4 w-4" aria-hidden />}{o.saved ? 'Saved' : 'Save'}
          </button>
          <Link to={`/student/messages?about=${encodeURIComponent(o.opp_id)}`} className="btn btn-quiet"><MessageSquare className="h-4 w-4" aria-hidden />Ask the NGO about this</Link>
        </div>
      )}
      {asking && (
        <form className="pop mt-3 space-y-2 rounded-lg bg-surface p-3" onSubmit={(e) => { e.preventDefault(); interest.mutate({ oppId: o.opp_id, note }, { onSuccess: () => { setAsking(false); setNote('') } }) }}>
          <label className="label" htmlFor="interest-note">Tell the NGO why (optional)</label>
          <textarea id="interest-note" className="input min-h-[70px]" maxLength={500} value={note} autoFocus onChange={(e) => setNote(e.target.value)} placeholder="For example: I did a project with these tools." />
          <div className="flex gap-2"><button type="submit" className="btn btn-primary" disabled={interest.isPending}>{interest.isPending ? 'Sending' : 'Send to the NGO'}</button><button type="button" className="btn btn-quiet" onClick={() => setAsking(false)}>Cancel</button></div>
        </form>
      )}
    </div>
  )
}
