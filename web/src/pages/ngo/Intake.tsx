import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { FileText, Upload, X } from 'lucide-react'
import { upload } from '../../lib/api'
import { cn } from '../../lib/utils'
import type { IntakeInput, IntakeResult } from '../../lib/types'
import { Badge, Banner, Empty, ErrorState, PageHeader, Section, Spinner } from '../../components/ui'
import { BreakdownFold } from './Match'
import { payText, rupees, whereText } from '../../lib/format'

const BRANCHES = ['CSE', 'CSE (AI and ML)', 'CSE (Data Science)', 'IT', 'ECE', 'EEE']
const TOWNS = ['Warangal', 'Khammam', 'Karimnagar', 'Nizamabad', 'Nalgonda', 'Mahabubnagar', 'Guntur', 'Vijayawada', 'Tirupati', 'Visakhapatnam']
const LIMITS = [['near_home_only', 'Near home only'], ['no_night_shift', 'No night shifts'], ['safe_workplace_required', 'Safe workplace required']]
const EMPTY: IntakeInput = {
  branch: 'CSE', college_town: 'Khammam', grad_year: 2026, cgpa: null, english_level: null,
  languages: ['Telugu', 'English'], can_relocate: 'unknown', budget: null, family_limits: [],
}

export default function Intake({ embedded = false }: { embedded?: boolean }) {
  const [f, setF] = useState<IntakeInput>(EMPTY)
  const [file, setFile] = useState<File | null>(null)
  const run = useMutation({
    mutationFn: ({ f: body, pdf }: { f: IntakeInput; pdf: File }) => {
      const form = new FormData()
      form.append('file', pdf)
      form.append('branch', body.branch)
      form.append('college_town', body.college_town)
      form.append('grad_year', String(body.grad_year))
      if (body.cgpa != null) form.append('cgpa', String(body.cgpa))
      form.append('can_relocate', body.can_relocate)
      if (body.budget != null) form.append('budget', String(body.budget))
      form.append('languages', body.languages.join(','))
      form.append('family_limits', body.family_limits.join(','))
      return upload<IntakeResult>('/api/intake/pdf', form)
    },
  })
  const set = <K extends keyof IntakeInput>(k: K, v: IntakeInput[K]) => setF((cur) => ({ ...cur, [k]: v }))
  const toggle = (k: 'languages' | 'family_limits', v: string) =>
    set(k, f[k].includes(v) ? f[k].filter((x) => x !== v) : [...f[k], v])
  const [over, setOver] = useState(false)
  const pick = (picked: File | undefined) => { if (picked) setFile(picked) }
  const r = run.data

  return (
    <>
      {!embedded && <PageHeader title="New student" sub="Upload a resume PDF. We read the skills out of it, then match the student live. Nothing is saved, and the file never leaves this machine." />}
      <div className="grid gap-8 px-8 pb-16 pt-6 xl:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <div className="space-y-5">
          <div>
            <span className="label">Resume (PDF only)</span>
            <label htmlFor="pdf"
              onDragOver={(e) => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
              onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files?.[0]) }}
              className={cn('flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed px-4 py-8 text-center text-sm transition-colors duration-150',
                over ? 'border-accent bg-accent-soft' : 'border-line-strong bg-surface hover:bg-sunk')}>
              <Upload className="h-5 w-5 text-ink-soft" aria-hidden />
              <span className="font-medium">Drop a resume PDF here, or choose a file</span>
              <span className="text-xs text-ink-faint">Up to 5 MB. Scans and photos cannot be read. The file is not stored.</span>
              <input id="pdf" type="file" accept="application/pdf,.pdf" className="sr-only" onChange={(e) => { pick(e.target.files?.[0]); e.target.value = '' }} />
            </label>
            {file && (
              <div className="pop mt-2 flex items-center justify-between rounded-md border border-line bg-surface px-3 py-2 text-sm">
                <span className="flex min-w-0 items-center gap-2"><FileText className="h-4 w-4 shrink-0 text-ink-soft" aria-hidden /><span className="truncate">{file.name}</span><span className="shrink-0 text-xs text-ink-faint">{Math.max(1, Math.round(file.size / 1024))} KB</span></span>
                <button type="button" className="btn btn-quiet !px-1.5" aria-label="Remove the file" onClick={() => setFile(null)}><X className="h-4 w-4" aria-hidden /></button>
              </div>
            )}
          </div>

          <div className="card grid gap-4 p-4 sm:grid-cols-2">
            <div><label className="label" htmlFor="br">Branch</label>
              <select id="br" className="input" value={f.branch} onChange={(e) => set('branch', e.target.value)}>{BRANCHES.map((b) => <option key={b}>{b}</option>)}</select></div>
            <div><label className="label" htmlFor="tn">College town</label>
              <select id="tn" className="input" value={f.college_town} onChange={(e) => set('college_town', e.target.value)}>{TOWNS.map((b) => <option key={b}>{b}</option>)}</select></div>
            <div><label className="label" htmlFor="cg">CGPA (blank to read it from the PDF)</label>
              <input id="cg" type="number" min={0} max={10} step={0.1} className="input" value={f.cgpa ?? ''} onChange={(e) => set('cgpa', e.target.value === '' ? null : Number(e.target.value))} /></div>
            <div><label className="label" htmlFor="rl">Can relocate</label>
              <select id="rl" className="input" value={f.can_relocate} onChange={(e) => set('can_relocate', e.target.value as IntakeInput['can_relocate'])}>
                <option value="yes">Yes</option><option value="no">No</option><option value="unknown">Not known</option></select></div>
            <div><label className="label" htmlFor="bd">Budget (Rs)</label>
              <input id="bd" type="number" min={0} step={500} placeholder="Not known" className="input" value={f.budget ?? ''} onChange={(e) => set('budget', e.target.value === '' ? null : Math.max(0, Number(e.target.value)))} /></div>
            <fieldset><legend className="label">Languages</legend>
              <div className="flex flex-wrap gap-1.5">{['Telugu', 'English', 'Hindi'].map((l) => <Chip key={l} on={f.languages.includes(l)} onClick={() => toggle('languages', l)}>{l}</Chip>)}</div></fieldset>
            <fieldset className="sm:col-span-2"><legend className="label">Family limits</legend>
              <div className="flex flex-wrap gap-1.5">{LIMITS.map(([id, label]) => <Chip key={id} on={f.family_limits.includes(id)} onClick={() => toggle('family_limits', id)}>{label}</Chip>)}</div></fieldset>
          </div>
          <button type="button" className="btn btn-primary" disabled={run.isPending || !file} onClick={() => file && run.mutate({ f, pdf: file })}>
            {run.isPending ? 'Reading and matching' : 'Read and match'}
          </button>
        </div>

        <div className="min-w-0 space-y-5">
          {run.isPending && <Spinner text="Reading the text" />}
          {run.error && <ErrorState error={run.error} onRetry={() => file && run.mutate({ f, pdf: file })} />}
          {!r && !run.isPending && !run.error && <Empty icon={FileText} title="Nothing read yet">Upload a resume PDF on the left, set what you know about the student, then choose Read and match.</Empty>}
          {r && (
            <div className="pop space-y-5">
              <Section title="What we read">
                <div className="card space-y-3 p-4 text-sm">
                  <div className="flex flex-wrap gap-x-6 gap-y-1">
                    <span>CGPA <strong>{r.student.cgpa ?? 'not found'}</strong></span>
                    <span>Projects <strong>{r.extracted.projects}</strong></span>
                    <span>English <strong>{r.student.english_level ?? 'not found'}</strong></span>
                  </div>
                  <div><h3 className="mb-1.5 text-ink-soft">Skills found</h3>
                    <div className="flex flex-wrap gap-1.5">
                      {r.skills.map((s) => <Badge key={s} tone="accent">{s}</Badge>)}
                      {r.skills.length === 0 && <span className="text-ink-faint">No skills from the skill list were found in this PDF.</span>}
                    </div></div>
                  {r.unmatched.length > 0 && <div className="flex flex-wrap gap-1.5">{r.unmatched.map((s) => <Badge key={s} tone="neutral" className="italic">{s}</Badge>)}</div>}
                  {r.student.missing_fields.length > 0 && <Banner tone="amber" lead="Not known.">{r.student.missing_fields.join(', ')}. Matches that depend on these show a check warning.</Banner>}
                </div>
              </Section>
              <Section title="Top matches">
                {r.matches?.length === 0 && <Empty title="No eligible matches">Every option was removed by a hard check.</Empty>}
                <div className="space-y-3">
                  {r.matches?.map((m) => (
                    <article key={m.opp_id} className="card p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div><div className="text-xs text-ink-soft">#{m.rank} · {m.type} · {whereText(m.city, m.mode)}{m.upfront_cost > 0 ? ` · ${rupees(m.upfront_cost)}` : ''}{payText(m.pay_min, m.pay_max) ? ` · ${payText(m.pay_min, m.pay_max)}` : ''}</div>
                          <h2 className="!text-lg">{m.title}</h2><p className="text-sm text-ink-soft">{m.org_name}</p></div>
                        <div className="font-serif text-xl">{m.final_score.toFixed(2)}</div>
                      </div>
                      <p className="mt-2 text-sm">{m.reason}</p>
                      {m.breakdown && <div className="mt-2"><BreakdownFold b={m.breakdown} /></div>}
                    </article>
                  ))}
                </div>
              </Section>
            </div>
          )}
        </div>
      </div>
    </>
  )
}

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" aria-pressed={on} onClick={onClick}
      className={cn('rounded-full border px-2.5 py-1 text-xs font-medium transition-colors duration-150',
        on ? 'border-accent bg-accent-soft text-accent' : 'border-line-strong bg-surface text-ink-soft hover:bg-sunk')}>{children}</button>
  )
}
