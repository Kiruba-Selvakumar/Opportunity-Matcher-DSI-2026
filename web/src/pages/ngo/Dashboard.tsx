import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarClock, CalendarDays, ClipboardCheck, FileText, Hourglass, MessageCircle, MessageSquare, Phone, SearchX, Send, TimerReset, Users, UserRoundX } from 'lucide-react'
import { get, post } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { cn } from '../../lib/utils'
import type { Dashboard as D } from '../../lib/types'
import { Badge, Banner, ErrorState, PageHeader, Section } from '../../components/ui'
import { CardsSkeleton } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'

const STAGES: [string, string][] = [['interested', 'Interested'], ['shared', 'Shared'], ['shortlisted', 'Shortlisted'], ['interview', 'Interview'], ['offered', 'Offered'], ['hired', 'Hired']]

function Tile({ to, icon: Icon, n, label, hot }: { to: string; icon: typeof Users; n: number; label: string; hot?: boolean }) {
  return (
    <Link to={to} className={cn('card flex items-center gap-3 p-4 transition-shadow duration-300 ease-out hover:shadow-lift', hot && n > 0 && 'border-maple-line bg-maple-soft/40')}>
      <Icon className={cn('h-5 w-5 shrink-0', hot && n > 0 ? 'text-maple' : 'text-ink-soft')} aria-hidden />
      <span><span className="block font-serif text-2xl leading-none">{n}</span><span className="text-sm text-ink-soft">{label}</span></span>
    </Link>
  )
}

export default function Dashboard() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const toast = useToast()
  const { user } = useAuth()
  const admin = user?.role === 'ngo_admin'
  const q = useQuery({ queryKey: ['dashboard'], queryFn: () => get<D>('/api/dashboard'), refetchInterval: 30000 })
  const done = useMutation({ mutationFn: (id: number) => post(`/api/notes/${id}/done`, {}), onSuccess: () => { toast('Marked done.'); qc.invalidateQueries({ queryKey: ['dashboard'] }) } })
  const open = (sid: string) => nav(`/ngo/students/${sid}`)
  const d = q.data
  const top = d ? Math.max(1, d.funnel.interested) : 1

  return (
    <>
      <PageHeader title="Home" sub={admin ? 'What is waiting for your approval, and how students are moving from interest to a job.' : 'What needs you today, and how students are moving from interest to a job.'} />
      <div className="px-4 pb-16 sm:px-8">
        {q.isLoading && <div className="pt-6"><CardsSkeleton n={3} /></div>}
        {q.error && <div className="pt-6"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>}
        {d && (
          <>
            <div className="grid gap-3 pt-6 sm:grid-cols-2 xl:grid-cols-4">
              {admin ? <>
                <Tile to="/ngo/applications?tab=approve" icon={Send} n={d.counts.put_forward} label="Waiting for your approval" hot />
                <Tile to="/ngo/opportunities?tab=review" icon={ClipboardCheck} n={d.counts.pending_reviews} label="Listings to review" hot />
                <Tile to="/ngo/messages?tab=leads" icon={MessageCircle} n={d.counts.new_leads} label="WhatsApp from employers" hot />
                <Tile to="/ngo/messages" icon={MessageSquare} n={d.counts.unread_messages} label="Unread messages" hot />
              </> : <>
                <Tile to="/ngo/applications?tab=waiting" icon={Hourglass} n={d.counts.interests_waiting - d.counts.put_forward} label="New interest to check" hot />
                <Tile to="/ngo/applications?tab=interviews" icon={CalendarDays} n={d.counts.interviews_week} label="Interviews this week" />
                <Tile to="/ngo/messages" icon={MessageSquare} n={d.counts.unread_messages} label="Unread messages" hot />
                <Tile to="/ngo/students" icon={FileText} n={d.counts.with_resume} label={`of ${d.counts.students} students have a resume`} />
              </>}
            </div>
            {(d.attention.number_changes?.length ?? 0) > 0 && (
              <div className="pt-4"><Banner tone="amber" icon={Phone} lead={`${d.attention.number_changes!.length} new mobile number${d.attention.number_changes!.length === 1 ? '' : 's'} to confirm.`}>
                {d.attention.number_changes!.map((sid, i) => <span key={sid}>{i > 0 && ', '}<Link to={`/ngo/students/${sid}`} className="underline">{sid}</Link></span>)}
              </Banner></div>)}

            <Section title="How students are moving">
              <div className="card space-y-2.5 p-5">
                {STAGES.map(([key, label], i) => {
                  const n = d.funnel[key] ?? 0
                  const prev = i === 0 ? null : d.funnel[STAGES[i - 1][0]] ?? 0
                  return (
                    <div key={key} className="grid grid-cols-[110px_1fr_90px] items-center gap-3 text-sm">
                      <span className="text-ink-soft">{label}</span>
                      <div className="h-2.5 overflow-hidden rounded-full bg-sunk" role="meter" aria-valuenow={n} aria-valuemin={0} aria-valuemax={top} aria-label={label}><div className="h-full rounded-full bg-accent transition-all duration-500 ease-out" style={{ width: `${(n / top) * 100}%` }} /></div>
                      <span className="text-right tabular-nums">{n}{prev ? <span className="text-ink-faint"> · {prev ? Math.round((n / prev) * 100) : 0}%</span> : null}</span>
                    </div>)
                })}
                <p className="pt-1 text-xs text-ink-faint">The percentage is the share of the step before. {d.counts.active_listings} listing{d.counts.active_listings === 1 ? ' is' : 's are'} live and {d.counts.in_play} student{d.counts.in_play === 1 ? ' is' : 's are'} in play.</p>
              </div>
            </Section>

            <Section title="Needs attention">
              <div className="grid items-start gap-4 lg:grid-cols-2">
                <Panel title="Follow-ups due" icon={CalendarClock} empty="Nothing is due.">
                  {d.attention.followups.map((f) => (
                    <li key={f.id} className="flex items-start justify-between gap-2">
                      <span><button type="button" className="font-mono text-xs underline" onClick={() => open(f.student_id)}>{f.student_id}</button> <span className="text-ink-faint">due {f.due}</span><span className="block text-ink-soft">{f.text}</span></span>
                      <button type="button" className="btn btn-quiet !py-0.5" onClick={() => done.mutate(f.id)}>Done</button>
                    </li>))}
                </Panel>
                <Panel title="Students with no match" icon={UserRoundX} count={d.attention.no_matches.count} empty="Everyone has at least one match." chips>
                  {d.attention.no_matches.ids.map((id) => <li key={id}><button type="button" className="rounded-md border border-line bg-bg px-2 py-0.5 font-mono text-xs hover:bg-sunk" onClick={() => open(id)}>{id}</button></li>)}
                </Panel>
                <Panel title="Applications that have stopped moving" icon={Hourglass} empty="Nothing has been waiting more than a week.">
                  {d.attention.stale.map((a) => <li key={a.id}><button type="button" className="font-mono text-xs underline" onClick={() => open(a.student_id)}>{a.student_id}</button> · {a.title} <Badge tone="amber">{a.days} days in {a.status.replace('_', ' ')}</Badge></li>)}
                </Panel>
                <Panel title="Missing information" icon={SearchX} count={d.attention.missing_info.count} empty="Every profile is complete." chips>
                  {d.attention.missing_info.items.map((m) => <li key={m.id}><button type="button" className="rounded-md border border-line bg-bg px-2 py-0.5 font-mono text-xs hover:bg-sunk" title={`missing ${m.missing} thing${m.missing === 1 ? '' : 's'}`} onClick={() => open(m.id)}>{m.id}</button></li>)}
                </Panel>
              </div>
              <div className="mt-4 grid items-start gap-4 lg:grid-cols-2">
                <Panel title="Interviews this week" icon={CalendarDays} empty="No interviews in the next 7 days.">
                  {d.attention.interviews.map((iv) => <li key={iv.id}><span className="font-medium">{iv.when}</span> · {iv.title} · <button type="button" className="font-mono text-xs underline" onClick={() => open(iv.student_id)}>{iv.student_id}</button> <span className="text-ink-faint">{iv.mode === 'meet' ? 'Meet' : iv.mode === 'phone' ? 'phone' : 'in person'}, {iv.interviewer === 'ngo' ? 'NGO interviews' : 'employer interviews'}</span></li>)}
                </Panel>
                <Panel title="Closing soon" icon={TimerReset} empty="No listing closes in the next 7 days.">
                  {d.attention.closing.map((c) => <li key={c.opp_id}><Link to={`/ngo/opportunities/${c.opp_id}`} className="underline">{c.title}</Link> <Badge tone="amber">last day {c.apply_by}</Badge> <span className="text-ink-faint">{c.eligible} students fit</span></li>)}
                </Panel>
              </div>
              <div className="mt-4">
                <Panel title="Busiest listings" icon={ClipboardCheck} empty="No listing has applicants yet.">
                  {d.attention.busiest.map((b) => <li key={b.opp_id}><Link to={`/ngo/opportunities/${b.opp_id}`} className="underline">{b.title}</Link> <span className="text-ink-faint">{b.load} student{b.load === 1 ? '' : 's'} in play for {b.openings} opening{b.openings === 1 ? '' : 's'}</span></li>)}
                </Panel>
              </div>
            </Section>
          </>
        )}
      </div>
    </>
  )
}

function Panel({ title, icon: Icon, count, empty, chips, children }: { title: string; icon: typeof Users; count?: number; empty: string; chips?: boolean; children: React.ReactNode }) {
  const items = Array.isArray(children) ? children : [children]
  const has = items.some((c) => Array.isArray(c) ? c.length > 0 : !!c)
  return (
    <section className="card p-4" aria-label={title}>
      <h3 className="flex items-center gap-2 text-ink"><Icon className="h-4 w-4 text-ink-soft" aria-hidden />{title}{count ? <Badge tone="neutral">{count}</Badge> : null}</h3>
      {has ? <ul className={chips ? 'mt-2 flex flex-wrap gap-2 text-sm' : 'mt-2 space-y-1.5 text-sm'}>{children}</ul> : <p className="mt-2 text-sm text-ink-faint">{empty}</p>}
    </section>
  )
}

