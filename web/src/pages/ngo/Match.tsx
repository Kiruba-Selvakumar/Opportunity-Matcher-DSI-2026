import { useEffect, useMemo, useRef, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, Check, FileText, Flag, MapPin, RotateCcw, Scale, Search, TrendingUp, Trophy, Wallet, X } from 'lucide-react'
import { get, post } from '../../lib/api'
import { cn } from '../../lib/utils'
import type { Breakdown, Match as MatchT, MatchesResponse, Profile, RawText, WhatIf, WhyNot } from '../../lib/types'
import { Badge, Empty, ErrorState, Fold, KV, Meter, Section, Spinner, type Tone } from '../../components/ui'
import { BorderTrail } from '../../components/motion/border-trail'
import { TextEffect } from '../../components/motion/text-effect'
import { ApplyBy } from '../../components/Deadline'
import { payText, rupees } from '../../lib/format'
import { PROGRAM_WORD } from '../../lib/types'

const LIMITS: { id: string; label: string }[] = [
  { id: 'near_home_only', label: 'Near home only' },
  { id: 'no_night_shift', label: 'No night shifts' },
  { id: 'safe_workplace_required', label: 'Safe workplace required' },
]
const LIMIT_WORD = Object.fromEntries(LIMITS.map((l) => [l.id, l.label]))
const REJECT_REASONS = ['not interested', 'skills gap', 'location', 'cost', 'family', 'other']
const CHECK_LABEL = { location: 'Location', budget: 'Budget', language: 'Language', family: 'Family' } as const
const CHECK_TONE: Record<string, Tone> = { pass: 'pass', unknown: 'amber', fail: 'fail' }
const TYPE_TONE: Record<string, Tone> = { job: 'navy', training: 'neutral', mentor: 'accent' }
const FIELD_WORD: Record<string, string> = {
  cgpa: 'CGPA', backlogs: 'Backlogs', english_level: 'English level', can_relocate: 'Relocation', budget: 'Budget',
}

function fromProfile(p: Profile): WhatIf {
  return {
    can_relocate: p.can_relocate === true ? 'yes' : p.can_relocate === false ? 'no' : 'unknown',
    budget: p.budget,
    family_limits: [...p.family_limits],
  }
}
const same = (a: WhatIf, b: WhatIf) =>
  a.can_relocate === b.can_relocate && a.budget === b.budget &&
  [...a.family_limits].sort().join() === [...b.family_limits].sort().join()

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

/** The matches for one student: profile, what-if, the top 5 compared side by side, and what the hard checks removed. */
export function MatchesPanel({ sid }: { sid: string }) {
  const opened = useRef(Date.now())
  const profile = useQuery({ queryKey: ['profile', sid], queryFn: () => get<Profile>(`/api/students/${sid}`) })
  const base = useQuery({ queryKey: ['matches', sid], queryFn: () => get<MatchesResponse>(`/api/students/${sid}/matches`) })

  const [ov, setOv] = useState<WhatIf | null>(null)
  useEffect(() => { if (profile.data && !ov) setOv(fromProfile(profile.data)) }, [profile.data, ov])
  const original = useMemo(() => (profile.data ? fromProfile(profile.data) : null), [profile.data])
  const dirty = !!ov && !!original && !same(ov, original)
  const debounced = useDebounced(ov, 350)

  const whatif = useQuery({
    queryKey: ['whatif', sid, JSON.stringify(debounced)],
    queryFn: () => post<MatchesResponse>(`/api/students/${sid}/whatif`, debounced),
    enabled: dirty && !!debounced,
    placeholderData: keepPreviousData,
  })
  const shown = dirty ? (whatif.data ?? base.data) : base.data
  const p = profile.data

  return (
    <>
      {profile.error && <div className="pt-6"><ErrorState error={profile.error} onRetry={() => profile.refetch()} /></div>}
      {profile.isLoading && <div className="pt-6"><Spinner text="Reading the student profile" /></div>}
      {p && ov && original && (
        <>
          <Section title="Profile">
            <ProfileCard p={p} />
          </Section>
          <Section title="What if?" right={dirty ? (
            <div className="flex items-center gap-2">
              <Badge tone="sky">What-if mode</Badge>
              <button type="button" className="btn btn-quiet" onClick={() => setOv(original)}><RotateCcw className="h-3.5 w-3.5" aria-hidden />Reset</button>
            </div>) : undefined}>
            <WhatIfPanel ov={ov} setOv={setOv} />
            <p className="mt-2 max-w-[75ch] text-xs text-ink-faint">Changes here re-score this student live. They are never saved to the data files.</p>
          </Section>
          <Section title="Top 5" right={whatif.isFetching && dirty ? <Spinner text="Re-scoring" /> : undefined}>
            {base.error && <ErrorState error={base.error} onRetry={() => base.refetch()} />}
            {base.isLoading && <Spinner text="Picking the best matches" />}
            {whatif.error && dirty && <ErrorState error={whatif.error} onRetry={() => whatif.refetch()} />}
            {shown && shown.matches.length === 0 && (
              <Empty icon={Search} title="No eligible matches">Every option was removed by a hard check. Open "Why not?" below to see which check removed each one.</Empty>
            )}
            {shown && shown.matches.length > 1 && <div className="mb-4"><ComparePanel ms={shown.matches} /></div>}
            {shown && (
              <div className="space-y-4" key={dirty ? `w-${JSON.stringify(debounced)}` : 'base'}>
                {shown.matches.map((m, i) => (
                  <MatchCard key={m.opp_id} m={m} sid={sid} whatIf={dirty} opened={opened} first={i === 0} animate={!dirty} />
                ))}
              </div>
            )}
          </Section>
          {shown && (
            <Section title="Why not?">
              <WhyNotList items={shown.why_not} />
            </Section>
          )}
        </>
      )}
    </>
  )
}

function ProfileCard({ p }: { p: Profile }) {
  const reloc = p.can_relocate === true ? 'Yes' : p.can_relocate === false ? 'No' : null
  const unknown = (f: string) => <Badge tone="amber">not known</Badge>
  return (
    <div className="card settle p-5">
      {p.edited_fields && p.edited_fields.length > 0 && (
        <p className="mb-3 flex flex-wrap items-center gap-1.5 text-xs text-ink-soft"><Badge tone="sky">Edited by the student</Badge>{p.edited_fields.map((f) => f.replace('_', ' ')).join(', ')}{p.edited_at ? ` on ${p.edited_at.slice(0, 10)}` : ''}</p>
      )}
      <KV items={[
        ['Program', p.program ? PROGRAM_WORD[p.program] : 'Placements'],
        ['Branch', p.branch],
        ['College', p.college || 'Not given'],
        ['College town', p.college_town],
        ['Graduating', p.grad_year],
        ['CGPA', p.cgpa ?? unknown('cgpa')],
        ['Backlogs', p.backlogs ?? unknown('backlogs')],
        ['English level', p.english_level ?? unknown('english_level')],
        ['Languages', p.languages.join(', ') || 'None listed'],
        ['Can relocate', reloc ?? unknown('can_relocate')],
        ['Budget', p.budget != null ? `Rs ${p.budget.toLocaleString('en-IN')}` : unknown('budget')],
        ['Family limits', p.family_limits.length ? p.family_limits.map((l) => LIMIT_WORD[l]).join(', ') : 'None'],
        ['Projects', p.projects],
      ]} />
      <div className="mt-4">
        <h3 className="mb-2 text-ink-soft">Skills</h3>
        <div className="flex flex-wrap gap-1.5">
          {p.skills.map((s) => <Badge key={s} tone="accent">{s}</Badge>)}
          {p.unmatched.map((s) => <Badge key={s} tone="neutral" className="italic">{s}</Badge>)}
          {p.skills.length + p.unmatched.length === 0 && <span className="text-sm text-ink-faint">No skills found in the text.</span>}
        </div>
        {p.unmatched.length > 0 && <p className="mt-2 text-xs text-ink-faint">Grey chips were not found in the skill list, so they are not scored.</p>}
        <div className="mt-4"><ParsedFold p={p} /></div>
        {p.missing_fields.length > 0 && (
          <p className="mt-3 flex flex-wrap items-center gap-1.5 text-xs text-ink-soft">
            Not known:
            {p.missing_fields.map((f) => <Badge key={f} tone="amber">{FIELD_WORD[f] ?? f}</Badge>)}
          </p>
        )}
      </div>
    </div>
  )
}

function WhatIfPanel({ ov, setOv }: { ov: WhatIf; setOv: (v: WhatIf) => void }) {
  const toggle = (id: string) =>
    setOv({ ...ov, family_limits: ov.family_limits.includes(id) ? ov.family_limits.filter((x) => x !== id) : [...ov.family_limits, id] })
  return (
    <div className="card grid gap-5 p-5 md:grid-cols-3">
      <div>
        <label htmlFor="reloc" className="label">Can relocate</label>
        <select id="reloc" className="input" value={ov.can_relocate} onChange={(e) => setOv({ ...ov, can_relocate: e.target.value as WhatIf['can_relocate'] })}>
          <option value="yes">Yes</option>
          <option value="no">No</option>
          <option value="unknown">Not known</option>
        </select>
      </div>
      <div>
        <label htmlFor="budget" className="label">Budget (Rs)</label>
        <input id="budget" className="input" type="number" min={0} step={500} placeholder="Not known" value={ov.budget ?? ''}
          onChange={(e) => setOv({ ...ov, budget: e.target.value === '' ? null : Math.max(0, Number(e.target.value)) })} />
      </div>
      <fieldset>
        <legend className="label">Family limits</legend>
        <div className="flex flex-wrap gap-1.5">
          {LIMITS.map((l) => {
            const on = ov.family_limits.includes(l.id)
            return (
              <button key={l.id} type="button" aria-pressed={on} onClick={() => toggle(l.id)}
                className={cn('rounded-full border px-2.5 py-1 text-xs font-medium transition-colors duration-150',
                  on ? 'border-accent bg-accent-soft text-accent' : 'border-line-strong bg-surface text-ink-soft hover:bg-sunk')}>
                {l.label}
              </button>
            )
          })}
        </div>
      </fieldset>
    </div>
  )
}

type Mode = null | 'reject' | 'flag'

function MatchCard({ m, sid, whatIf, opened, first, animate }: {
  m: MatchT; sid: string; whatIf: boolean; opened: React.MutableRefObject<number>; first: boolean; animate: boolean
}) {
  const qc = useQueryClient()
  const [mode, setMode] = useState<Mode>(null)
  const [reason, setReason] = useState(REJECT_REASONS[0])
  const [note, setNote] = useState('')
  const [saved, setSaved] = useState<string | null>(null)

  const save = useMutation({
    mutationFn: (decision: 'accept' | 'reject' | 'flag') =>
      post('/api/decisions', {
        student_id: sid, opp_id: m.opp_id, rank: m.rank, final_score: m.final_score, decision,
        reject_reason: decision === 'reject' ? reason : null, note: note.trim() || null, what_if: whatIf,
        seconds_to_decide: Math.round((Date.now() - opened.current) / 100) / 10,
      }).then(() => decision),
    onSuccess: (d) => {
      setSaved(d === 'accept' ? 'Accepted' : d === 'reject' ? 'Rejected' : 'Flagged for help')
      setMode(null); setNote('')
      qc.invalidateQueries({ queryKey: ['decisions'] })
    },
  })
  const err = save.error as Error | null

  const pay = m.pay_min != null && m.pay_max != null ? `${(((m.pay_min + m.pay_max) / 2) / 100000).toFixed(1)} LPA` : null
  return (
    <article className={cn('card relative p-5', animate && first && 'settle-2', animate && !first && 'pop', first && 'shadow-lift')}>
      {first && <BorderTrail size={64} className="bg-gradient-to-r from-sky via-pear to-sky" />}
      {first && <div className="pointer-events-none absolute inset-x-0 top-0 h-20 rounded-t-lg bg-gradient-to-b from-sky-soft/70 to-transparent" />}
      <div className="relative">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm text-ink-soft">
              <span className="font-mono text-xs">#{m.rank}</span>
              <Badge tone={TYPE_TONE[m.type]}>{m.type}</Badge>
              {m.fit && <Badge tone={m.fit === 'Strong fit' ? 'pass' : m.fit === 'Good fit' ? 'sky' : m.fit === 'Stretch' ? 'amber' : 'neutral'}>{m.fit}</Badge>}
              {m.crowded && <Badge tone="amber">Crowded</Badge>}
              <ApplyBy date={m.apply_by} />
              <span className="inline-flex items-center gap-1"><MapPin className="h-3.5 w-3.5" aria-hidden />{m.city === 'Remote' ? 'Remote' : m.city}</span>
              {m.upfront_cost > 0 && <span className="inline-flex items-center gap-1"><Wallet className="h-3.5 w-3.5" aria-hidden />Rs {m.upfront_cost.toLocaleString('en-IN')}</span>}
              {pay && <span>{pay}</span>}
            </div>
            <h2 className="mt-1 !text-xl">{first && animate ? <TextEffect>{m.title}</TextEffect> : m.title}</h2>
            <p className="text-sm text-ink-soft">{m.org_name} <span className="font-mono text-xs text-ink-faint">{m.opp_id}</span></p>
          </div>
          <div className="w-40 shrink-0 text-right">
            <div className="font-serif text-2xl">{m.final_score.toFixed(2)}</div>
            <Meter value={m.final_score} tone={first ? 'sky' : 'accent'} label={`Score for ${m.title}`} />
          </div>
        </div>

        <p className="mt-3 max-w-[75ch] text-base">{m.reason}</p>

        <div className="mt-3 flex flex-wrap gap-1.5">
          {(Object.keys(CHECK_LABEL) as (keyof typeof CHECK_LABEL)[]).map((k) => {
            const c = m.checks[k]
            return <Badge key={k} tone={CHECK_TONE[c.status]} className="max-w-full">{CHECK_LABEL[k]}: {c.note || (c.status === 'pass' ? 'ok' : c.status)}</Badge>
          })}
        </div>
        {(m.overlap.length > 0 || m.missing.length > 0) && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
            {m.overlap.map((s) => <Badge key={s} tone="accent"><Check className="h-3 w-3" aria-hidden />{s}</Badge>)}
            {m.missing.map((s) => <Badge key={s} tone="neutral">Missing {s}</Badge>)}
          </div>
        )}

        {m.gap_closers?.length > 0 && <p className="mt-2 text-xs text-ink-soft"><strong className="font-medium text-ink">Close the gap:</strong> {m.gap_closers.map((g) => `${g.title} (teaches ${g.covers.join(', ')})`).join('; ')}</p>}
        <Signals m={m} />
        {m.breakdown && <div className="mt-3"><BreakdownFold b={m.breakdown} /></div>}

        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-line pt-3">
          <button type="button" className="btn btn-primary" disabled={save.isPending} onClick={() => save.mutate('accept')}><Check className="h-4 w-4" aria-hidden />Accept</button>
          <button type="button" className={cn('btn', mode === 'reject' && 'bg-sunk')} onClick={() => setMode(mode === 'reject' ? null : 'reject')}><X className="h-4 w-4" aria-hidden />Reject</button>
          <button type="button" className={cn('btn', mode === 'flag' && 'bg-sunk')} onClick={() => setMode(mode === 'flag' ? null : 'flag')}><Flag className="h-4 w-4" aria-hidden />Flag for help</button>
          {saved && <Badge tone="pass" className="pop">{saved}{whatIf ? ' (what-if)' : ''}</Badge>}
        </div>

        {mode && (
          <div className="pop mt-3 grid gap-3 rounded-lg bg-bg p-3 md:grid-cols-[200px_1fr_auto] md:items-end">
            {mode === 'reject' && (
              <div>
                <label className="label" htmlFor={`rr-${m.opp_id}`}>Reason</label>
                <select id={`rr-${m.opp_id}`} className="input" value={reason} onChange={(e) => setReason(e.target.value)}>
                  {REJECT_REASONS.map((r) => <option key={r}>{r}</option>)}
                </select>
              </div>
            )}
            <div className={mode === 'flag' ? 'md:col-span-2' : ''}>
              <label className="label" htmlFor={`nt-${m.opp_id}`}>{mode === 'flag' ? 'Note (required)' : 'Note (optional)'}</label>
              <input id={`nt-${m.opp_id}`} className="input" value={note} onChange={(e) => setNote(e.target.value)}
                placeholder={mode === 'flag' ? 'What should a person check?' : 'Anything the next person should know'} />
            </div>
            <button type="button" className={cn('btn', mode === 'reject' ? 'btn-danger' : 'btn-primary')}
              disabled={save.isPending || (mode === 'flag' && !note.trim())} onClick={() => save.mutate(mode)}>
              {mode === 'reject' ? 'Save rejection' : 'Save flag'}
            </button>
          </div>
        )}
        {err && <p className="mt-2 text-sm text-fail" role="alert">{err.message}</p>}
      </div>
    </article>
  )
}

function WhyNotList({ items }: { items: WhyNot[] }) {
  return (
    <Fold title="High-skill matches the hard checks removed" right={<span className="text-xs text-ink-faint">{items.length} shown</span>}>
      {items.length === 0 ? (
        <p className="text-sm text-ink-soft">Nothing was removed. Every option passed the hard checks.</p>
      ) : (
        <ul className="space-y-3">
          {items.map((w) => (
            <li key={w.opp_id} className="text-sm">
              <div className="font-medium">{w.title} <span className="font-mono text-xs text-ink-faint">{w.opp_id}</span> <span className="text-ink-soft">· {w.city} · skill score {w.base_score.toFixed(2)}</span></div>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {w.fails.map((f) => <Badge key={f.check} tone="fail">{f.check}: {f.note}</Badge>)}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Fold>
  )
}



const ADJ: Record<string, string> = { branch_fit: 'Branch fits this kind of job', home_state: 'Stays in the home state', low_cgpa: 'CGPA below 6.0 for a job', crowded: 'Many students have already applied', staff_prior: 'What staff accepted for similar listings',
  upskill: 'The gap is easy to close (related skill or a training)', standing: 'How this student ranks among everyone it fits', ml: 'Learned from past staff and employer outcomes' }

export function BreakdownFold({ b }: { b: Breakdown }) {
  const sim = b.weight_sim * b.skill_sim
  const cov = b.weight_coverage * b.coverage
  return (
    <Fold title="How this score was made">
      <table className="w-full max-w-[60ch] text-sm">
        <tbody>
          <tr><td className="py-1 text-ink-soft">Skill similarity {b.skill_sim.toFixed(2)} × {b.weight_sim}</td><td className="py-1 text-right">{sim.toFixed(3)}</td></tr>
          <tr><td className="py-1 text-ink-soft">Required skills covered {b.coverage.toFixed(2)} × {b.weight_coverage}</td><td className="py-1 text-right">{cov.toFixed(3)}</td></tr>
          <tr className="border-t border-line"><td className="py-1 font-medium">Skill score</td><td className="py-1 text-right font-medium">{b.base_score.toFixed(3)}</td></tr>
          {Object.entries(b.adjustments ?? {}).map(([k, v]) => (
            <tr key={k}><td className="py-1 text-ink-soft">{ADJ[k] ?? k}</td><td className="py-1 text-right">{v > 0 ? '+' : ''}{v.toFixed(3)}</td></tr>))}
          <tr><td className="py-1 text-ink-soft">Penalty for long hours</td><td className="py-1 text-right">{b.penalty_hours ? `-${b.penalty_hours.toFixed(2)}` : '0'}</td></tr>
          <tr><td className="py-1 text-ink-soft">Penalty for low safety</td><td className="py-1 text-right">{b.penalty_safety ? `-${b.penalty_safety.toFixed(2)}` : '0'}</td></tr>
          <tr className="border-t border-line"><td className="py-1 font-medium">Final score</td><td className="py-1 text-right font-serif text-lg">{b.final_score.toFixed(3)}</td></tr>
        </tbody>
      </table>
      {(b.related?.length ?? 0) > 0 && <p className="mt-2 text-xs text-ink-soft">Counted partly: {b.related!.map((r) => `${r.have} for ${r.need} (${Math.round(r.credit * 100)}%)`).join(', ')}.</p>}
      {b.prior_note && <p className="mt-1 text-xs text-ink-soft">{b.prior_note}.</p>}
      {b.standing && <p className="mt-1 text-xs text-ink-soft">Ranks {b.standing.rank} of {b.standing.of} eligible students for this listing.</p>}
      {b.ml != null && <p className="mt-1 text-xs text-ink-soft">Learned chance of a yes from staff or the employer: {Math.round(b.ml * 100)}%.</p>}
      {b.upskill && <p className="mt-1 text-xs text-ink-soft">Upskilling reach {Math.round(b.upskill.reach * 100)}%: coverage could rise from {Math.round(b.coverage * 100)}% to {Math.round(b.upskill.potential * 100)}%.</p>}
      <p className="mt-2 max-w-[75ch] text-xs text-ink-faint">Coverage counts rarer skills more, and a nice-to-have skill half. Hard checks (location, budget, language, family) come first. A match that fails one is removed before any score counts.</p>
    </Fold>
  )
}

function ParsedFold({ p }: { p: Profile }) {
  const raw = useQuery({ queryKey: ['raw', p.student_id], queryFn: () => get<RawText>(`/api/students/${p.student_id}/raw`) })
  const yn = (v: boolean | null) => (v === true ? 'Yes' : v === false ? 'No' : 'Not known')
  const rows: [string, string, string][] = raw.data ? [
    ['Skills', raw.data.skills_text, `${p.skills_raw.join(', ') || 'none'} → ${p.skills.join(', ') || 'none'}`],
    ['CGPA', raw.data.cgpa_text, p.cgpa != null ? String(p.cgpa) : 'Not known'],
    ['Backlogs', raw.data.backlogs, p.backlogs != null ? String(p.backlogs) : 'Not known'],
    ['English', raw.data.english_text, p.english_level ?? 'Not known'],
    ['Languages', raw.data.languages_text, p.languages.join(', ') || 'None'],
    ['Can relocate', raw.data.can_relocate_text, yn(p.can_relocate)],
    ['Budget', raw.data.budget_text, p.budget != null ? `Rs ${p.budget.toLocaleString('en-IN')}` : 'Not known'],
    ['Family limits', raw.data.family_limits_text, p.family_limits.join(', ') || 'None'],
  ] : []
  return (
    <Fold title="How we read this student's text" right={<Badge tone="sky">{p.parse_method === 'llm' ? 'read by LLM' : 'read by rules'}</Badge>}>
      {raw.isLoading && <Spinner />}
      {raw.error && <ErrorState error={raw.error} onRetry={() => raw.refetch()} />}
      {rows.length > 0 && (
        <table className="w-full text-sm">
          <thead><tr><th className="th">Field</th><th className="th">What they wrote</th><th className="th">What we understood</th></tr></thead>
          <tbody>{rows.map(([k, a, b]) => (
            <tr key={k}><td className="td text-ink-soft">{k}</td><td className="td font-mono text-xs">{a || <span className="text-ink-faint">blank</span>}</td><td className="td">{b}</td></tr>
          ))}</tbody>
        </table>
      )}
      <p className="mt-2 text-xs text-ink-faint">Skill words that are not in the skill list stay grey and are not scored.</p>
    </Fold>
  )
}


/** Standing among students, the upskilling path, the learned chance and the resume score for this listing. */
function Signals({ m }: { m: MatchT }) {
  const steps = m.upskill?.steps.filter((x) => x.ease > 0) ?? []
  if (!m.standing && steps.length === 0 && m.ml == null && !m.ats) return null
  return (
    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-soft">
      {m.standing && <span className="inline-flex items-center gap-1"><Trophy className="h-3.5 w-3.5" aria-hidden />Ranks {m.standing.rank} of {m.standing.of} students it fits</span>}
      {steps.length > 0 && <span className="inline-flex items-center gap-1"><TrendingUp className="h-3.5 w-3.5" aria-hidden />Within reach: {steps.map((x) => x.from ? `${x.skill} (knows ${x.from})` : `${x.skill} (via ${x.via?.title})`).join(', ')}</span>}
      {m.ml != null && <span className="inline-flex items-center gap-1"><Bot className="h-3.5 w-3.5" aria-hidden />Past outcomes say {Math.round(m.ml * 100)}% yes</span>}
      {m.ats && <span className="inline-flex items-center gap-1"><FileText className="h-3.5 w-3.5" aria-hidden />Resume score {m.ats.score} for this listing{m.ats.keywords_missing.length ? ` (missing ${m.ats.keywords_missing.slice(0, 2).join(', ')})` : ''}</span>}
    </div>
  )
}

type Row = { label: string; value: (m: MatchT) => number | null; show: (m: MatchT) => string; best: 'high' | 'low' }
const ROWS: Row[] = [
  { label: 'Score', value: (m) => m.final_score, show: (m) => m.final_score.toFixed(2), best: 'high' },
  { label: 'Needed skills covered', value: (m) => m.breakdown?.coverage ?? null, show: (m) => m.breakdown ? `${Math.round(m.breakdown.coverage * 100)}%` : '-', best: 'high' },
  { label: 'Skills to learn', value: (m) => m.missing.length, show: (m) => m.missing.length ? m.missing.join(', ') : 'None', best: 'low' },
  { label: 'Easy to close the gap', value: (m) => m.upskill ? m.upskill.reach : null, show: (m) => m.upskill ? `${Math.round(m.upskill.reach * 100)}%` : '-', best: 'high' },
  { label: 'Rank among students', value: (m) => m.standing ? m.standing.percentile : null, show: (m) => m.standing ? `${m.standing.rank} of ${m.standing.of}` : '-', best: 'high' },
  { label: 'Resume score here', value: (m) => m.ats?.score ?? null, show: (m) => m.ats ? String(m.ats.score) : '-', best: 'high' },
  { label: 'Pay', value: (m) => (m.pay_min != null && m.pay_max != null ? (m.pay_min + m.pay_max) / 2 : null), show: (m) => payText(m.pay_min, m.pay_max) ?? '-', best: 'high' },
  { label: 'Cost up front', value: (m) => m.upfront_cost, show: (m) => (m.upfront_cost ? rupees(m.upfront_cost) : 'Free'), best: 'low' },
  { label: 'Needs a move', value: (m) => (m.checks.location.note.startsWith('needs move') ? 1 : 0), show: (m) => (m.checks.location.note.startsWith('needs move') ? `Yes, ${m.city}` : 'No'), best: 'low' },
  { label: 'Hours a week', value: (m) => m.hours_per_week, show: (m) => String(m.hours_per_week), best: 'low' },
]

/** "Which one is better?": the top matches side by side, with the best value in each row marked. */
function ComparePanel({ ms }: { ms: MatchT[] }) {
  const best = (r: Row) => {
    const vals = ms.map(r.value).filter((v): v is number => v != null)
    if (vals.length < 2 || new Set(vals).size === 1) return null
    return r.best === 'high' ? Math.max(...vals) : Math.min(...vals)
  }
  const [a, b] = ms
  const name = (m: MatchT) => (a.title === b.title ? `${m.title} at ${m.org_name}` : m.title)
  const why = ROWS.slice(1).filter((r) => { const x = r.value(a), y = r.value(b); return x != null && y != null && x !== y && (r.best === 'high' ? x > y : x < y) }).map((r) => r.label.toLowerCase())
  return (
    <Fold title="Which one is better? Compare the top matches" right={<Scale className="h-4 w-4 text-ink-soft" aria-hidden />}>
      <p className="mb-3 max-w-[75ch] text-sm text-ink-soft"><strong className="font-medium text-ink">{name(a)}</strong> ranks above <strong className="font-medium text-ink">{name(b)}</strong>{why.length ? `: better on ${why.slice(0, 3).join(', ')}.` : ' on the overall score.'}</p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead><tr><th className="th">&nbsp;</th>{ms.map((m) => <th key={m.opp_id} className="th min-w-[140px] normal-case tracking-normal">#{m.rank} {m.title}</th>)}</tr></thead>
          <tbody>{ROWS.map((r) => {
            const top = best(r)
            return (
              <tr key={r.label}><td className="td text-ink-soft">{r.label}</td>
                {ms.map((m) => <td key={m.opp_id} className={cn('td', top != null && r.value(m) === top && 'bg-pass-soft font-medium text-pass')}>{r.show(m)}</td>)}</tr>)
          })}</tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-ink-faint">Green marks the best value in each row. The score already weighs all of these; this view helps you explain the choice.</p>
    </Fold>
  )
}
