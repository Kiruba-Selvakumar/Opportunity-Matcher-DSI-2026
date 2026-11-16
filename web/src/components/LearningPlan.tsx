import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowDown, ArrowRight, ArrowUp, Check, Clock, GraduationCap, ListChecks, Route, X } from 'lucide-react'
import { del, get, post, put } from '../lib/api'
import { dateWords, rupees, TYPE_WORD, whereText } from '../lib/format'
import { cn } from '../lib/utils'
import type { LearningPlan, PlanFix, PlanOption, PlanRole, PlanStep } from '../lib/types'
import { Badge, Empty, ErrorState, Spinner, type Tone } from './ui'
import { useToast } from './Toast'

/**
 * A learning plan: courses and mentors taken one after another, and what they do for each of the student's roles,
 * checked against each role's last day to apply. Students can pick their own and put them in the order they want.
 * It is a preview: their real matches change only when they add the skill.
 */
export function LearningPlanView({ path, forStudent = false }: { path: string; forStudent?: boolean }) {
  const q = useQuery({ queryKey: ['plan', path], queryFn: () => get<LearningPlan>(path) })
  const [editing, setEditing] = useState(false)
  if (q.isLoading) return <Spinner text="Working out the plan" />
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const p = q.data!
  const canChoose = forStudent && (p.options?.length ?? 0) > 0
  if (editing) return <ChoosePlan plan={p} path={path} onDone={() => setEditing(false)} />
  return (
    <div className="space-y-4">
      {(canChoose || p.custom) && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Badge tone={p.custom ? 'accent' : 'neutral'}>{p.custom ? (forStudent ? 'Your own plan' : 'Chosen by the student') : 'Suggested plan'}</Badge>
          {canChoose && <button type="button" className="btn" onClick={() => setEditing(true)}><ListChecks className="h-4 w-4" aria-hidden />{p.custom ? 'Change my courses' : 'Choose my own courses'}</button>}
        </div>)}
      <PlanBody p={p} forStudent={forStudent} />
    </div>
  )
}

/** What the plan does for each role (first, because that is what a student cares about), then the steps in order. */
function PlanBody({ p, forStudent, onFix }: { p: LearningPlan; forStudent: boolean; onFix?: (f: PlanFix) => void }) {
  const dropped = p.dropped?.length ?? 0
  return (
    <div className="space-y-4">
      <p className="max-w-[75ch] text-sm text-ink-soft">{p.message}</p>
      {dropped > 0 && <p className="max-w-[75ch] text-xs text-ink-faint">{dropped} of the courses picked earlier {dropped === 1 ? 'is' : 'are'} no longer open to you, so {dropped === 1 ? 'it is' : 'they are'} left out.</p>}
      {(p.late ?? 0) > 0 && <LateWarning p={p} forStudent={forStudent} onFix={onFix} />}
      {p.steps.length > 0 && <PlanTime p={p} />}
      {(p.roles?.length ?? 0) > 0 && <Roles roles={p.roles!} forStudent={forStudent} />}
      {p.steps.length === 0 ? (
        <Empty icon={Route} title={p.custom ? 'No course picked yet' : 'No course to suggest yet'}>{forStudent ? 'Talk to your placement officer about mentors or free courses.' : 'No eligible, upcoming training teaches what these jobs ask for.'}</Empty>
      ) : (
        <div>
          <h3 className="mb-2 text-ink-soft">{p.steps.length > 1 ? 'The steps, one after another' : 'The step'}</h3>
          <ol className="space-y-3 border-l-2 border-line pl-5">
            {p.steps.map((s, i) => (
              <li key={s.opp_id} className="relative">
                <span className="absolute -left-[31px] top-3 flex h-5 w-5 items-center justify-center rounded-full bg-accent text-xs font-semibold text-surface">{i + 1}</span>
                <article className="card p-4">
                  <StepMeta s={s} />
                  <h4 className="mt-1 text-base">{s.title} <span className="text-sm font-normal text-ink-soft">{s.org_name}</span></h4>
                  {s.no_batch
                    ? <p className="mt-1 text-sm text-fail">Its only batch starts before the step before it ends, so it cannot fit here. Move it earlier or drop it.</p>
                    : s.covered_by_earlier
                      ? <p className="mt-1 text-sm text-ink-soft">An earlier step already teaches what this one does.</p>
                      : <p className="mt-1 text-sm">Teaches {s.teaches.map((t) => <Badge key={t} tone="accent" className="mr-1">{t}</Badge>)}</p>}
                </article>
              </li>
            ))}
          </ol>
        </div>
      )}
      {(p.still_missing?.length ?? 0) > 0 && <p className="text-xs text-ink-faint">Still to learn some other way: {p.still_missing!.join(', ')}.</p>}
    </div>
  )
}

const STATUS: Record<PlanRole['status'], [string, Tone]> = {
  in_time: ['In time', 'pass'], late: ['Late', 'fail'], no_deadline: ['No last day', 'neutral'],
  not_helped: ['Not helped by this plan', 'neutral'], unknown: ['Self-paced: no end date', 'amber'],
}
const roleSub = (r: PlanRole) => [r.org_name, r.pay_lpa ? `${r.pay_lpa} LPA` : null].filter(Boolean).join(" · ")
const statusText = (r: PlanRole) => (r.status === 'late' ? `${r.days_late} day${r.days_late === 1 ? '' : 's'} late` : STATUS[r.status][0])

/** One row per role: score now and with the plan, when the student would be ready, and its last day to apply. */
function Roles({ roles, forStudent }: { roles: PlanRole[]; forStudent: boolean }) {
  const score = (r: PlanRole) => (
    <span className="tabular-nums">{r.before.toFixed(2)} <ArrowRight className="inline h-3.5 w-3.5" aria-label="to" /> <strong className={r.after > r.before ? 'text-pass' : ''}>{r.after.toFixed(2)}</strong></span>
  )
  const badge = (r: PlanRole) => <Badge tone={STATUS[r.status][1]}>{r.status === 'late' && <AlertTriangle className="h-3 w-3" aria-hidden />}{statusText(r)}</Badge>
  return (
    <div className="card p-4 text-sm">
      <h3 className="mb-2 text-ink-soft">{forStudent ? 'What this plan does for your roles' : 'What this plan does for the student’s roles'}</h3>
      <table className="hidden w-full sm:table">
        <thead><tr className="text-left text-xs text-ink-faint">
          <th className="py-1.5 font-medium">Role</th><th className="py-1.5 font-medium">Score now → with the plan</th>
          <th className="py-1.5 font-medium">Ready by</th><th className="py-1.5 font-medium">Last day to apply</th><th className="py-1.5 font-medium"><span className="sr-only">Status</span></th>
        </tr></thead>
        <tbody>
          {roles.map((r) => (
            <tr key={r.opp_id} className="border-t border-line">
              <td className="py-2 pr-3">{r.title}<span className="block text-xs text-ink-faint">{roleSub(r)}</span></td>
              <td className="py-2 pr-3">{score(r)}</td>
              <td className="py-2 pr-3">{r.ready_by ? dateWords(r.ready_by) : '–'}</td>
              <td className="py-2 pr-3">{r.apply_by ? dateWords(r.apply_by) : 'None'}</td>
              <td className="py-2 text-right">{badge(r)}</td>
            </tr>))}
        </tbody>
      </table>
      <ul className="space-y-2 sm:hidden">
        {roles.map((r) => (
          <li key={r.opp_id} className="rounded-md border border-line p-3">
            <div className="flex items-start justify-between gap-2"><span className="font-medium">{r.title}<span className="block text-xs font-normal text-ink-faint">{roleSub(r)}</span></span>{badge(r)}</div>
            <div className="mt-1 text-ink-soft">Score {score(r)}</div>
            <div className="text-xs text-ink-soft">Ready by {r.ready_by ? dateWords(r.ready_by) : '–'} · Last day {r.apply_by ? dateWords(r.apply_by) : 'none'}</div>
          </li>))}
      </ul>
      {forStudent && <p className="mt-2 text-xs text-ink-faint">These scores are a preview. Your matches change once you add the new skill to your profile.</p>}
    </div>
  )
}

/** Which roles the plan makes late, and changes that would fix it. In the chooser the fixes can be applied in one click. */
function LateWarning({ p, forStudent, onFix }: { p: LearningPlan; forStudent: boolean; onFix?: (f: PlanFix) => void }) {
  const late = (p.roles ?? []).filter((r) => r.status === 'late')
  return (
    <div className="space-y-2 rounded-md border border-fail-line bg-fail-soft px-3 py-2.5 text-sm" role="status">
      {late.map((r) => {
        const fixes = (p.fixes ?? []).filter((f) => f.role_id === r.opp_id)
        return (
          <div key={r.opp_id}>
            <p className="flex items-start gap-1.5 text-fail">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <span><strong className="font-semibold">{r.title}</strong> stops taking applications on {dateWords(r.apply_by!)}, but {forStudent ? 'you would' : 'the student would'} be ready only on {dateWords(r.ready_by!)}.</span>
            </p>
            {fixes.length > 0 ? (
              <div className="mt-1.5 flex flex-wrap items-center gap-2 pl-5">
                <span className="text-ink-soft">To make it:</span>
                {fixes.map((f) => {
                  const lose = f.loses?.length ? `, you lose the boost for ${f.loses.join(" and ")}` : ''
                  const words = f.kind === 'move' ? `Take ${f.title} first` : `Drop ${f.title}${lose}`
                  return onFix
                    ? <button key={f.kind + f.opp_id} type="button" className="btn !py-1 text-xs" onClick={() => onFix(f)}>{words} (ready {dateWords(f.ready_by!)})</button>
                    : <span key={f.kind + f.opp_id} className="text-ink">{words} (ready {dateWords(f.ready_by!)}).</span>
                })}
              </div>
            ) : <p className="mt-1 pl-5 text-ink-soft">No change to this plan gets it in time. Ask your placement officer whether you can apply while you are still learning.</p>}
          </div>)
      })}
    </div>
  )
}

function StepMeta({ s }: { s: PlanStep }) {
  const when = s.starts_on ? `${dateWords(s.starts_on)}${s.ends_on ? ` to ${dateWords(s.ends_on)}` : ''}` : s.any_time ? 'Start any time' : 'No batch'
  return (
    <span className="flex flex-wrap items-center gap-2 text-sm text-ink-soft">
      <Badge tone="neutral"><GraduationCap className="h-3 w-3" aria-hidden />{TYPE_WORD[s.type]}</Badge>
      <span>{when}</span>
      <span>· {timeText(s)}</span>
      <span>· {whereText(s.city, s.mode)}</span>
      <span>· {s.cost > 0 ? rupees(s.cost) : 'Free'}</span>
    </span>
  )
}

const MAX_PICKS = 6

/** Tick the courses and mentors you want and put them in order. The plan below follows every change; nothing is
 *  kept until Save. */
function ChoosePlan({ plan, path, onDone }: { plan: LearningPlan; path: string; onDone: () => void }) {
  const qc = useQueryClient()
  const toast = useToast()
  const options = plan.options ?? []
  const byId = Object.fromEntries(options.map((o) => [o.opp_id, o])) as Record<string, PlanOption>
  const [order, setOrder] = useState<string[]>((plan.order ?? []).filter((id) => byId[id]))
  const [view, setView] = useState<LearningPlan>(plan)
  const preview = useMutation({
    mutationFn: (ids: string[]) => post<LearningPlan>('/api/me/plan/preview', { opp_ids: ids }),
    onSuccess: setView,
    onError: (e) => toast((e as Error).message, 'fail'),
  })
  const finish = (p: LearningPlan) => { qc.setQueryData(['plan', path], p); onDone() }
  const save = useMutation({
    mutationFn: () => put<LearningPlan>('/api/me/plan/choices', { opp_ids: order }),
    onSuccess: (p) => { toast('Your plan is saved.'); finish(p) },
    onError: (e) => toast((e as Error).message, 'fail'),
  })
  const reset = useMutation({
    mutationFn: () => del<LearningPlan>('/api/me/plan/choices'),
    onSuccess: (p) => { toast('Back to the suggested plan.'); finish(p) },
  })
  useEffect(() => { preview.mutate(order) }, [order])   // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = (id: string) => setOrder((now) => (now.includes(id) ? now.filter((x) => x !== id) : now.length >= MAX_PICKS ? now : [...now, id]))
  const move = (i: number, by: number) => setOrder((now) => {
    const next = [...now]; const j = i + by
    if (j < 0 || j >= next.length) return now
    ;[next[i], next[j]] = [next[j], next[i]]
    return next
  })
  return (
    <div className="space-y-4">
      <div className="card space-y-3 p-4">
        <div>
          <h3 className="text-base">Pick the courses and mentors you want</h3>
          <p className="text-sm text-ink-soft">Tick up to {MAX_PICKS}. You take them one after another, in the order below. The plan underneath shows what they do for each role, and warns you if one would make you miss a last day to apply. Nothing is saved until you choose Save.</p>
        </div>
        {order.length > 0 && (
          <div>
            <h4 className="mb-1.5 text-sm font-medium">Your order</h4>
            <ol className="space-y-1.5">
              {order.map((id, i) => (
                <li key={id} className="flex items-center gap-2 rounded-md border border-line bg-bg px-2.5 py-1.5 text-sm">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-semibold text-surface" aria-hidden>{i + 1}</span>
                  <span className="min-w-0 flex-1">{byId[id]?.title ?? id} <span className="text-ink-faint">· {byId[id] ? timeText(byId[id]) : ''}</span></span>
                  <button type="button" className="btn btn-quiet !p-1" aria-label={`Move ${byId[id]?.title} earlier`} disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp className="h-4 w-4" aria-hidden /></button>
                  <button type="button" className="btn btn-quiet !p-1" aria-label={`Move ${byId[id]?.title} later`} disabled={i === order.length - 1} onClick={() => move(i, 1)}><ArrowDown className="h-4 w-4" aria-hidden /></button>
                  <button type="button" className="btn btn-quiet !p-1" aria-label={`Remove ${byId[id]?.title}`} onClick={() => toggle(id)}><X className="h-4 w-4" aria-hidden /></button>
                </li>))}
            </ol>
          </div>)}
        <ul className="divide-y divide-line">
          {options.map((o) => {
            const on = order.includes(o.opp_id)
            const full = !on && order.length >= MAX_PICKS
            return (
              <li key={o.opp_id}>
                <label className={cn('flex cursor-pointer items-start gap-3 py-3', full && 'cursor-not-allowed opacity-60')}>
                  <input type="checkbox" className="mt-1 h-4 w-4 accent-[#2c6148]" checked={on} disabled={full} onChange={() => toggle(o.opp_id)} />
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-2"><strong className="font-medium">{o.title}</strong>{o.suggested && <Badge tone="sky">Suggested</Badge>}</span>
                    <StepMeta s={o} />
                    <span className="mt-1 block text-sm">Teaches {o.teaches.map((t) => <Badge key={t} tone="accent" className="mr-1">{t}</Badge>)}</span>
                  </span>
                </label>
              </li>)
          })}
        </ul>
        <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3">
          <button type="button" className="btn btn-primary" disabled={save.isPending} onClick={() => save.mutate()}><Check className="h-4 w-4" aria-hidden />Save my plan</button>
          <button type="button" className="btn btn-quiet" onClick={onDone}>Cancel</button>
          {plan.custom && <button type="button" className="btn btn-quiet ml-auto" disabled={reset.isPending} onClick={() => reset.mutate()}>Back to the suggested plan</button>}
        </div>
      </div>
      <div aria-live="polite" className={cn('transition-opacity', preview.isPending && 'opacity-60')}>
        <PlanBody p={view} forStudent onFix={(f) => setOrder(f.order)} />
      </div>
    </div>
  )
}

/** "4 weeks · about 8 h a week (≈32 h)", or "Self-paced, about 2 h a week" for anything with no set length. */
export function timeText(s: PlanStep): string {
  const perWeek = s.hours_per_week ? `about ${s.hours_per_week} h a week` : ''
  if (s.self_paced) return `Self-paced${perWeek ? `, ${perWeek}` : ''}`
  return `${s.weeks} week${s.weeks === 1 ? '' : 's'}${perWeek ? ` · ${perWeek}` : ''}${s.total_hours ? ` (≈${s.total_hours} h)` : ''}`
}

/** One line on how long the whole plan takes, one step after another. */
function PlanTime({ p }: { p: LearningPlan }) {
  const parts: string[] = []
  if (p.finish_by) parts.push(`Done by ${dateWords(p.finish_by)}`)
  if (p.weeks_total) parts.push(`about ${p.weeks_total} week${p.weeks_total === 1 ? '' : 's'} from today`)
  if (p.hours_total) parts.push(`about ${p.hours_total} hours in all`)
  const open = p.open_ended ?? 0
  const tail = open > 0 ? ` ${open} ${open === 1 ? 'step is' : 'steps are'} self-paced, so ${open === 1 ? 'it has' : 'they have'} no end date.` : ''
  if (!parts.length && !tail) return null
  return (
    <p className="flex max-w-[75ch] items-start gap-1.5 text-sm">
      <Clock className="mt-0.5 h-4 w-4 shrink-0 text-ink-soft" aria-hidden />
      <span>{parts.length ? parts.join(' · ') + '.' : ''}{tail}</span>
    </p>
  )
}
