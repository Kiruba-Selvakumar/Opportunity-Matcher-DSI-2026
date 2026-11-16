import { cn } from '../lib/utils'
import type { ListingForm } from '../lib/types'

export const EMPTY_LISTING: ListingForm = {
  title: '', type: 'job', org_name: '', description: '', required_skills_text: '', city: '', mode: 'onsite', pay_text: '',
  upfront_cost_text: '0', hours_per_week: 40, night_shift: false, languages: ['English'], openings: 1,
  apply_by: null, starts_on: null, duration_weeks: null, batch_every_weeks: 0,
}

export function previewSkills(text: string): { name: string; nice: boolean }[] {
  return text.split(/[,;]/).map((c) => c.trim()).filter(Boolean).map((c) => {
    const nice = /is a plus|nice to have|optional|preferred|bonus/i.test(c)
    return { name: c.replace(/is a plus|nice to have|\(?optional\)?|preferred|bonus/gi, '').trim(), nice }
  }).filter((s) => s.name)
}

/** The body to send: the city follows the mode, and empty dates are null. */
export function listingBody(f: ListingForm): ListingForm {
  return { ...f, city: f.mode === 'remote' ? 'Remote' : f.city, apply_by: f.apply_by || null, starts_on: f.type === 'job' ? null : f.starts_on || null,
           duration_weeks: f.type === 'job' ? null : f.duration_weeks || null, batch_every_weeks: f.type === 'job' ? 0 : f.batch_every_weeks || 0 }
}

const pill = (on: boolean) => cn('rounded-full border px-3 py-1 text-sm font-medium transition-colors',
  on ? 'border-accent bg-accent-soft text-accent' : 'border-line-strong bg-surface text-ink-soft hover:bg-sunk')

/** Every field of a listing. Employers and NGO admins fill the same form; only admins may add mentors. */
export function ListingFields({ f, set, allowMentor = false }: {
  f: ListingForm; set: <K extends keyof ListingForm>(k: K, v: ListingForm[K]) => void; allowMentor?: boolean
}) {
  const today = new Date().toISOString().slice(0, 10)
  const toggleLang = (l: ListingForm['languages'][number]) => set('languages', f.languages.includes(l) ? f.languages.filter((x) => x !== l) : [...f.languages, l])
  return (
    <>
      <div className="card grid gap-4 p-5 sm:grid-cols-2">
        <div className="sm:col-span-2"><label className="label" htmlFor="l-title">Title</label>
          <input id="l-title" className="input" value={f.title} maxLength={80} onChange={(e) => set('title', e.target.value)} placeholder="Junior Data Analyst" /></div>
        <div><label className="label" htmlFor="l-type">Kind</label>
          <select id="l-type" className="input" value={f.type} onChange={(e) => set('type', e.target.value as ListingForm['type'])}>
            <option value="job">Job</option><option value="training">Training</option>{allowMentor && <option value="mentor">Mentor</option>}</select></div>
        <div><label className="label" htmlFor="l-org">Company or provider</label>
          <input id="l-org" className="input" value={f.org_name} maxLength={80} onChange={(e) => set('org_name', e.target.value)} /></div>
        <div className="sm:col-span-2"><label className="label" htmlFor="l-desc">What the role involves (optional)</label>
          <textarea id="l-desc" className="input min-h-[90px]" value={f.description} maxLength={1000} onChange={(e) => set('description', e.target.value)} />
          <p className="mt-1 text-xs text-ink-faint">{f.description.length}/1000. Do not put phone numbers or emails here. They are removed.</p></div>
        <div className="sm:col-span-2"><label className="label" htmlFor="l-skills">Skills asked for</label>
          <input id="l-skills" className="input" value={f.required_skills_text} maxLength={300} onChange={(e) => set('required_skills_text', e.target.value)} placeholder="Python, SQL, Git is a plus" aria-describedby="l-skills-h" />
          <p id="l-skills-h" className="mt-1 text-xs text-ink-faint">Separate with commas. Add "is a plus" to a skill that is nice to have. Use common names such as Python, SQL, Excel, React.</p></div>
      </div>
      <div className="card grid gap-4 p-5 sm:grid-cols-2">
        <fieldset className="sm:col-span-2"><legend className="label">Where</legend>
          <div className="flex flex-wrap gap-1.5">{(['onsite', 'hybrid', 'remote'] as const).map((m) => (
            <button key={m} type="button" aria-pressed={f.mode === m} onClick={() => set('mode', m)} className={pill(f.mode === m)}>{m === 'onsite' ? 'On site' : m === 'hybrid' ? 'Hybrid' : 'Remote'}</button>))}</div></fieldset>
        {f.mode !== 'remote' && <div><label className="label" htmlFor="l-city">City</label>
          <input id="l-city" className="input" value={f.city} maxLength={40} onChange={(e) => set('city', e.target.value)} placeholder="Hyderabad" /></div>}
        <div><label className="label" htmlFor="l-pay">Pay</label>
          <input id="l-pay" className="input" value={f.pay_text} maxLength={60} onChange={(e) => set('pay_text', e.target.value)} placeholder="3.6 LPA, or 25k/month" /></div>
        <div><label className="label" htmlFor="l-cost">Cost to the student</label>
          <input id="l-cost" className="input" value={f.upfront_cost_text} maxLength={40} onChange={(e) => set('upfront_cost_text', e.target.value)} placeholder="0" />
          <p className="mt-1 text-xs text-ink-faint">For a job this should be 0. Jobs that ask for money are rejected.</p></div>
        <div><label className="label" htmlFor="l-hours">Hours a week</label>
          <input id="l-hours" type="number" min={1} max={80} className="input" value={f.hours_per_week} onChange={(e) => set('hours_per_week', Number(e.target.value))} /></div>
        <div><label className="label" htmlFor="l-open">Openings</label>
          <input id="l-open" type="number" min={1} max={50} className="input" value={f.openings} onChange={(e) => set('openings', Number(e.target.value))} />
          <p className="mt-1 text-xs text-ink-faint">The listing closes when this many students are hired.</p></div>
        <div><label className="label" htmlFor="l-apply">Last day to apply (optional)</label>
          <input id="l-apply" type="date" className="input" min={today} value={f.apply_by ?? ''} onChange={(e) => set('apply_by', e.target.value || null)} />
          <p className="mt-1 text-xs text-ink-faint">After this day students cannot show interest, and the listing closes on its own.</p></div>
        <fieldset><legend className="label">Languages needed</legend>
          <div className="flex flex-wrap gap-1.5">{(['English', 'Telugu', 'Hindi'] as const).map((l) => (
            <button key={l} type="button" aria-pressed={f.languages.includes(l)} onClick={() => toggleLang(l)}
              className={cn('rounded-full border px-2.5 py-1 text-xs font-medium transition-colors', f.languages.includes(l) ? 'border-accent bg-accent-soft text-accent' : 'border-line-strong bg-surface text-ink-soft hover:bg-sunk')}>{l}</button>))}</div></fieldset>
        <label className="flex items-center gap-2 self-end text-sm"><input type="checkbox" checked={f.night_shift} onChange={(e) => set('night_shift', e.target.checked)} />Includes night shifts</label>
      </div>
      {f.type === 'training' && (
        <div className="card grid gap-4 p-5 sm:grid-cols-3">
          <p className="text-sm text-ink-soft sm:col-span-3">When does it run? Students see the next batch in their learning plan, with the jobs it helps them reach.</p>
          <div><label className="label" htmlFor="l-start">First batch starts</label>
            <input id="l-start" type="date" className="input" value={f.starts_on ?? ''} onChange={(e) => set('starts_on', e.target.value || null)} /></div>
          <div><label className="label" htmlFor="l-weeks">Weeks per batch</label>
            <input id="l-weeks" type="number" min={1} max={104} className="input" value={f.duration_weeks ?? ''} onChange={(e) => set('duration_weeks', e.target.value ? Number(e.target.value) : null)} /></div>
          <div><label className="label" htmlFor="l-every">A new batch every (weeks)</label>
            <input id="l-every" type="number" min={0} max={52} className="input" value={f.batch_every_weeks ?? 0} onChange={(e) => set('batch_every_weeks', Number(e.target.value) || 0)} />
            <p className="mt-1 text-xs text-ink-faint">0 means one batch only.</p></div>
        </div>
      )}
    </>
  )
}
