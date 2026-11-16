import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, CircleDashed, Clock, Download, FileUp, MessageCircle, Phone, Plus, Save, X } from 'lucide-react'
import { get, post, put, upload } from '../../lib/api'
import { cn } from '../../lib/utils'
import type { Consent, MyContact, ProfilePayload, ResumeSummary } from '../../lib/types'
import { Badge, ErrorState, Meter, PageHeader, Section } from '../../components/ui'
import { AtsReport } from '../../components/Resume'
import { CardsSkeleton } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'

const LIMITS: [string, string][] = [['near_home_only', 'Near home only'], ['no_night_shift', 'No night shifts'], ['safe_workplace_required', 'Safe workplace required']]
const LANGS = ['Telugu', 'English', 'Hindi']

export default function Profile() {
  const qc = useQueryClient()
  const toast = useToast()
  const q = useQuery({ queryKey: ['me-profile'], queryFn: () => get<ProfilePayload>('/api/me/profile') })
  const skills = useQuery({ queryKey: ['skills'], queryFn: () => get<string[]>('/api/skills'), staleTime: Infinity })
  const p = q.data?.profile
  const [form, setForm] = useState<{ can_relocate: string; budget: string; family_limits: string[]; languages: string[]; english_level: string } | null>(null)
  const [extra, setExtra] = useState<string[]>([])
  const [pick, setPick] = useState('')
  const [suggest, setSuggest] = useState<{ suggested: string[]; already: string[] } | null>(null)
  const [chosen, setChosen] = useState<string[]>([])
  const file = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!q.data) return
    const pr = q.data.profile
    setForm({ can_relocate: pr.can_relocate === true ? 'yes' : pr.can_relocate === false ? 'no' : 'unknown', budget: pr.budget == null ? '' : String(pr.budget),
              family_limits: pr.family_limits, languages: pr.languages, english_level: pr.english_level ?? '' })
    setExtra(q.data.extra_skills)
  }, [q.data])

  const refresh = () => { qc.invalidateQueries({ queryKey: ['me-profile'] }); qc.invalidateQueries({ queryKey: ['me-student'] }) }
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => put<ProfilePayload>('/api/me/profile', body),
    onSuccess: () => { toast('Saved. Your matches have been updated.'); refresh() }, onError: (e) => toast((e as Error).message, 'fail'),
  })
  const myCv = useQuery({ queryKey: ['me-resume'], queryFn: () => get<ResumeSummary | null>('/api/me/resume') })
  const consent = useQuery({ queryKey: ['me-consent'], queryFn: () => get<Consent>('/api/me/consent') })
  const agree = useMutation({
    mutationFn: (on: boolean) => put<Consent>('/api/me/consent', { whatsapp: on }),
    onSuccess: (c) => { toast(c.whatsapp ? 'You will get WhatsApp updates.' : 'No more WhatsApp updates.'); qc.invalidateQueries({ queryKey: ['me-consent'] }) },
  })
  const keep = useRef(false)
  const read = useMutation({
    mutationFn: (f: File) => { const d = new FormData(); d.append('file', f); return upload<{ suggested: string[]; already: string[]; resume: ResumeSummary | null }>(`/api/me/resume${keep.current ? '?keep=true' : ''}`, d) },
    onSuccess: (r) => { setSuggest(r); setChosen(r.suggested); if (r.resume) { toast('Resume saved. The NGO can now read it.'); qc.invalidateQueries({ queryKey: ['me-resume'] }) } },
    onError: (e) => toast((e as Error).message, 'fail'),
  })

  const toggle = (arr: string[], v: string) => (arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v])
  const saveCircumstances = () => form && save.mutate({
    can_relocate: form.can_relocate, budget: form.budget === '' ? null : Number(form.budget), family_limits: form.family_limits,
    languages: form.languages, ...(form.english_level ? { english_level: form.english_level } : {}),
  })
  const addSkills = (list: string[]) => { const next = [...new Set([...extra, ...list])]; setExtra(next); save.mutate({ extra_skills: next }) }
  const have = new Set(p?.skills ?? [])

  return (
    <>
      <PageHeader title="Profile" sub="Keep this up to date and your matches stay accurate. Changes apply at once." />
      <div className="max-w-3xl px-4 pb-16 sm:px-8">
        {q.isLoading && <div className="pt-6"><CardsSkeleton n={2} /></div>}
        {q.error && <div className="pt-6"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>}
        {q.data && p && form && (
          <>
            <Section title="How complete is it?">
              <div className="card p-5">
                <div className="flex items-center gap-3"><div className="w-40"><Meter value={q.data.completeness.percent / 100} label="Profile complete" /></div><span className="font-serif text-xl">{q.data.completeness.percent}%</span></div>
                <ul className="mt-3 space-y-1.5 text-sm">
                  {q.data.completeness.items.map((i) => (
                    <li key={i.field} className="flex items-start gap-2">
                      {i.done ? <Check className="mt-0.5 h-4 w-4 shrink-0 text-pass" aria-label="Done" /> : <CircleDashed className="mt-0.5 h-4 w-4 shrink-0 text-amber" aria-label="Not done" />}
                      <span className={cn(i.done && 'text-ink-soft')}>{i.label}{!i.done && i.impact > 0 && <span className="text-ink-soft"> · holding back {i.impact} match{i.impact === 1 ? '' : 'es'}</span>}</span>
                    </li>))}
                </ul>
                {q.data.edited_at && <p className="mt-3 text-xs text-ink-faint">You last changed this on {q.data.edited_at.slice(0, 10)}.</p>}
              </div>
            </Section>

            <Section title="Your situation">
              <form className="card grid gap-4 p-5 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); saveCircumstances() }}>
                <div><label className="label" htmlFor="p-rel">Can you move for a job?</label>
                  <select id="p-rel" className="input" value={form.can_relocate} onChange={(e) => setForm({ ...form, can_relocate: e.target.value })}><option value="yes">Yes</option><option value="no">No</option><option value="unknown">I am not sure</option></select></div>
                <div><label className="label" htmlFor="p-bud">How much can you spend up front (Rs)?</label>
                  <input id="p-bud" type="number" min={0} step={500} className="input" value={form.budget} placeholder="Not sure" onChange={(e) => setForm({ ...form, budget: e.target.value })} />
                  <p className="mt-1 text-xs text-ink-faint">Moving to a new city is counted too. Rs 10,000 is assumed.</p></div>
                <div><label className="label" htmlFor="p-eng">Your English</label>
                  <select id="p-eng" className="input" value={form.english_level} onChange={(e) => setForm({ ...form, english_level: e.target.value })}><option value="">Not sure</option><option value="basic">Basic</option><option value="intermediate">Good enough to work in</option><option value="fluent">Fluent</option></select></div>
                <fieldset><legend className="label">Languages you speak</legend>
                  <div className="flex flex-wrap gap-1.5">{LANGS.map((l) => <Chip key={l} on={form.languages.includes(l)} onClick={() => setForm({ ...form, languages: toggle(form.languages, l) })}>{l}</Chip>)}</div></fieldset>
                <fieldset className="sm:col-span-2"><legend className="label">Anything that limits where you can work?</legend>
                  <div className="flex flex-wrap gap-1.5">{LIMITS.map(([id, label]) => <Chip key={id} on={form.family_limits.includes(id)} onClick={() => setForm({ ...form, family_limits: toggle(form.family_limits, id) })}>{label}</Chip>)}</div></fieldset>
                <div className="sm:col-span-2"><button type="submit" className="btn btn-primary" disabled={save.isPending || form.languages.length === 0}>{save.isPending ? 'Saving' : 'Save changes'}</button></div>
              </form>
            </Section>

            <Section title="Your skills">
              <div className="card space-y-4 p-5">
                <div className="flex flex-wrap gap-1.5">
                  {p.skills.map((s) => <Badge key={s} tone={extra.includes(s) ? 'sky' : 'accent'}>{s}{extra.includes(s) && <button type="button" aria-label={`Remove ${s}`} className="-mr-1 ml-0.5 rounded-full p-0.5 hover:bg-black/10" onClick={() => { const n = extra.filter((x) => x !== s); setExtra(n); save.mutate({ extra_skills: n }) }}><X className="h-3 w-3" aria-hidden /></button>}</Badge>)}
                  {p.skills.length === 0 && <span className="text-sm text-ink-faint">No skills yet.</span>}
                </div>
                <p className="text-xs text-ink-faint">Blue skills are ones you added. The rest came from your original record, which only the NGO can change.</p>
                <div className="flex flex-wrap items-end gap-2">
                  <div className="min-w-[200px] flex-1"><label className="label" htmlFor="p-skill">Add a skill</label>
                    <select id="p-skill" className="input" value={pick} onChange={(e) => setPick(e.target.value)}><option value="">Choose a skill</option>{(skills.data ?? []).filter((s) => !have.has(s)).map((s) => <option key={s}>{s}</option>)}</select></div>
                  <button type="button" className="btn" disabled={!pick || save.isPending} onClick={() => { addSkills([pick]); setPick('') }}><Plus className="h-4 w-4" aria-hidden />Add</button>
                </div>
                <div className="border-t border-line pt-4">
                  <h3 className="mb-1 text-ink-soft">Or read it from your resume</h3>
                  <p className="mb-2 max-w-[75ch] text-xs text-ink-faint">Choose a PDF. We suggest skills we find. Nothing is added until you tick it. "Read only" does not keep the file; "Save as my resume" keeps it so the NGO can read it, and shows you how a hiring screen sees it.</p>
                  <input ref={file} type="file" accept="application/pdf,.pdf" className="sr-only" id="p-cv" onChange={(e) => { const f = e.target.files?.[0]; if (f) read.mutate(f); e.target.value = '' }} />
                  <div className="flex flex-wrap gap-2">
                    <label htmlFor="p-cv" className="btn cursor-pointer" onClick={() => { keep.current = false }}><FileUp className="h-4 w-4" aria-hidden />{read.isPending && !keep.current ? 'Reading' : 'Read only'}</label>
                    <label htmlFor="p-cv" className="btn btn-primary cursor-pointer" onClick={() => { keep.current = true }}><Save className="h-4 w-4" aria-hidden />{read.isPending && keep.current ? 'Saving' : 'Save as my resume'}</label>
                  </div>
                  {suggest && (
                    <div className="pop mt-3 rounded-lg bg-bg p-3">
                      {suggest.suggested.length === 0 ? <p className="text-sm text-ink-soft">We found nothing new. {suggest.already.length ? `You already have ${suggest.already.length} of the skills in it.` : 'Try a resume that lists skills in words.'}</p> : (
                        <>
                          <p className="mb-2 text-sm font-medium">We found these. Untick any that are not right.</p>
                          <div className="flex flex-wrap gap-1.5">{suggest.suggested.map((s) => <Chip key={s} on={chosen.includes(s)} onClick={() => setChosen(toggle(chosen, s))}>{s}</Chip>)}</div>
                          <button type="button" className="btn btn-primary mt-3" disabled={chosen.length === 0 || save.isPending} onClick={() => { addSkills(chosen); setSuggest(null) }}>Add {chosen.length} skill{chosen.length === 1 ? '' : 's'}</button>
                        </>)}
                    </div>)}
                </div>
              </div>
            </Section>

            <Section title="Your resume">
              <AtsReport r={myCv.data} forStudent />
              {myCv.data && <a className="btn btn-quiet mt-2" href="/api/me/resume.pdf" target="_blank" rel="noreferrer">Open my resume</a>}
            </Section>

            <Section title="Your mobile number">
              <MobileNumber />
            </Section>

            <Section title="WhatsApp updates">
              <div className="card flex flex-wrap items-center justify-between gap-3 p-4 text-sm">
                <p className="flex items-start gap-2 text-ink-soft"><MessageCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />{consent.data?.whatsapp ? 'You get WhatsApp messages about new matches, listings and interviews.' : 'Get WhatsApp messages about new matches, listings that fit you, and interviews.'}{consent.data && !consent.data.reachable && ' We do not have a mobile number for you yet. Add one above.'}</p>
                <button type="button" className={consent.data?.whatsapp ? 'btn' : 'btn btn-primary'} disabled={agree.isPending || !consent.data} onClick={() => agree.mutate(!consent.data?.whatsapp)}>{consent.data?.whatsapp ? 'Turn off' : 'Turn on'}</button>
              </div>
            </Section>

            <Section title="Your data">
              <p className="mb-3 max-w-[75ch] text-sm text-ink-soft">To change your CGPA, branch or college, message your placement officer. Those come from your college records.</p>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                <a className="btn" href="/api/me/export?format=html" download><Download className="h-4 w-4" aria-hidden />Download my data</a>
                <a className="text-sm text-ink-soft underline" href="/api/me/export" download>Download as JSON (for other apps)</a>
              </div>
              <p className="mt-2 max-w-[75ch] text-xs text-ink-faint">A page you can open in any browser. To keep it as a PDF, choose Print, then Save as PDF.</p>
            </Section>
          </>
        )}
      </div>
    </>
  )
}

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return <button type="button" aria-pressed={on} onClick={onClick} className={cn('rounded-full border px-2.5 py-1 text-xs font-medium transition-colors duration-150', on ? 'border-accent bg-accent-soft text-accent' : 'border-line-strong bg-surface text-ink-soft hover:bg-sunk')}>{children}</button>
}

/** The student's number, shown masked, and a way to ask for a new one. It is used only after the NGO confirms it. */
function MobileNumber() {
  const qc = useQueryClient()
  const toast = useToast()
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState('')
  const [err, setErr] = useState('')
  const me = useQuery({ queryKey: ['me-contact'], queryFn: () => get<MyContact>('/api/me/contact') })
  const ask = useMutation({
    mutationFn: () => post<MyContact>('/api/me/contact-change', { phone: value }),
    onSuccess: () => {
      toast('Sent. The NGO will confirm your new number.')
      setEditing(false); setValue(''); setErr('')
      qc.invalidateQueries({ queryKey: ['me-contact'] }); qc.invalidateQueries({ queryKey: ['me-consent'] })
    },
    onError: (e) => setErr((e as Error).message),
  })
  if (me.error) return <ErrorState error={me.error} onRetry={() => me.refetch()} />
  const c = me.data
  return (
    <div className="card max-w-[75ch] space-y-3 p-4 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="flex items-center gap-2"><Phone className="h-4 w-4 text-ink-soft" aria-hidden />
          {c?.phone ? <span>Ending in <strong className="font-medium tabular-nums">{c.phone.slice(-4)}</strong></span> : <span className="text-ink-soft">No number on file</span>}
        </p>
        {!editing && <button type="button" className="btn" onClick={() => setEditing(true)} disabled={!c}>{c?.phone ? 'Change number' : 'Add a number'}</button>}
      </div>
      {c?.pending && (
        <p className="flex items-start gap-2 rounded-md bg-amber-soft px-3 py-2 text-amber" role="status">
          <Clock className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          A new number ending in {c.pending.phone?.slice(-4)} is waiting for the NGO to confirm. Until then we use your old one.
        </p>)}
      {!c?.pending && c?.last?.status === 'rejected' && (
        <p className="text-ink-soft">The NGO did not change your number last time.{c.last.note ? ` ${c.last.note}` : ''}</p>)}
      {editing && (
        <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); ask.mutate() }}>
          <label className="label" htmlFor="new-phone">New mobile number</label>
          <input id="new-phone" className="input max-w-xs" inputMode="tel" autoComplete="tel" placeholder="98765 43210" value={value} maxLength={20}
            onChange={(e) => { setValue(e.target.value); setErr('') }} aria-invalid={!!err} aria-describedby="new-phone-help" autoFocus />
          <p id="new-phone-help" className={err ? 'text-fail' : 'text-xs text-ink-faint'}>{err || 'A 10-digit Indian mobile. The NGO checks it before we send anything to it.'}</p>
          <div className="flex gap-2">
            <button type="submit" className="btn btn-primary" disabled={!value.trim() || ask.isPending}>{ask.isPending ? 'Sending' : 'Send to the NGO'}</button>
            <button type="button" className="btn btn-quiet" onClick={() => { setEditing(false); setValue(''); setErr('') }}>Cancel</button>
          </div>
        </form>)}
    </div>
  )
}
