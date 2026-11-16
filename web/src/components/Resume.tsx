import { CircleCheck, CircleDashed, ExternalLink, FileText, Lightbulb } from 'lucide-react'
import type { AtsResult, ResumeSummary } from '../lib/types'
import { Badge, Empty, Meter } from './ui'

const GRADE_TONE = { Strong: 'pass', Fair: 'sky', Weak: 'amber' } as const
const PART_WORD: Record<string, [string, number]> = {
  sections: ['Clear sections', 40], contact: ['Email and phone', 10], skills: ['Skills named', 20],
  length: ['Length', 10], impact: ['Results with numbers', 15], links: ['GitHub or LinkedIn', 5],
}
const SECTION_WORD: Record<string, string> = { education: 'Education', skills: 'Skills', projects: 'Projects', experience: 'Experience', certifications: 'Certifications', summary: 'Summary' }

/** The PDF inside the page. The server lets only this app frame it. */
export function ResumeViewer({ src, height = 720 }: { src: string; height?: number }) {
  return (
    <div className="card overflow-hidden">
      <div className="flex items-center justify-between border-b border-line px-3 py-2 text-sm">
        <span className="inline-flex items-center gap-1.5 text-ink-soft"><FileText className="h-4 w-4" aria-hidden />Resume</span>
        <a href={src} target="_blank" rel="noreferrer" className="btn btn-quiet !py-0.5"><ExternalLink className="h-3.5 w-3.5" aria-hidden />Open in a new tab</a>
      </div>
      <iframe title="Resume" src={src} className="block w-full bg-sunk" style={{ height }} />
    </div>
  )
}

export function AtsScore({ score, grade }: { score: number; grade: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="font-serif text-3xl leading-none">{score}</span>
      <div className="w-32"><Meter value={score / 100} label="Resume score" /></div>
      <Badge tone={GRADE_TONE[grade as keyof typeof GRADE_TONE] ?? 'neutral'}>{grade}</Badge>
    </div>
  )
}

/** How the resume reads to a hiring screen, what it is made of, and what to fix. */
export function AtsReport({ r, forStudent = false }: { r: ResumeSummary | null | undefined; forStudent?: boolean }) {
  if (!r) return <Empty icon={FileText} title="No resume yet">{forStudent ? 'Save your resume below and you will see how a hiring screen reads it.' : 'Upload one to see the resume, its score and what to improve.'}</Empty>
  return (
    <div className="card space-y-4 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <AtsScore score={r.score} grade={r.grade} />
        <span className="text-xs text-ink-faint">{r.pages} page{r.pages === 1 ? '' : 's'} · added {r.uploaded_at.slice(0, 10)} {r.source === 'student' ? 'by the student' : 'by the NGO'}</span>
      </div>
      <table className="w-full max-w-[52ch] text-sm"><tbody>
        {Object.entries(PART_WORD).map(([k, [label, max]]) => (
          <tr key={k}><td className="py-0.5 text-ink-soft">{label}</td><td className="w-24 py-0.5"><Meter value={(r.parts[k] ?? 0) / max} label={label} /></td><td className="w-14 py-0.5 text-right tabular-nums">{r.parts[k] ?? 0}/{max}</td></tr>))}
      </tbody></table>
      <div className="flex flex-wrap gap-1.5 text-xs">
        {Object.entries(SECTION_WORD).map(([k, w]) => r.sections.includes(k)
          ? <Badge key={k} tone="pass"><CircleCheck className="h-3 w-3" aria-hidden />{w}</Badge>
          : <Badge key={k} tone="neutral"><CircleDashed className="h-3 w-3" aria-hidden />{w}</Badge>)}
      </div>
      {r.not_in_profile.length > 0 && (
        <p className="text-sm text-ink-soft">The resume names skills that are not in the {forStudent ? 'profile yet' : 'student’s profile'}: {r.not_in_profile.map((s) => <Badge key={s} tone="sky" className="mr-1">{s}</Badge>)}</p>)}
      {r.tips.length > 0 && <Tips tips={r.tips} />}
    </div>
  )
}

/** The resume read against one listing: which of its skills the resume names. */
export function AtsForListing({ a }: { a: AtsResult | null | undefined }) {
  if (!a) return <p className="text-sm text-ink-faint">No resume on file, so there is no resume score for this listing.</p>
  return (
    <div className="space-y-3">
      <AtsScore score={a.score} grade={a.grade} />
      <div className="flex flex-wrap gap-1.5 text-xs">
        {a.keywords_found.map((k) => <Badge key={k} tone="accent"><CircleCheck className="h-3 w-3" aria-hidden />{k}</Badge>)}
        {a.keywords_missing.map((k) => <Badge key={k} tone="neutral">Not in resume: {k}</Badge>)}
      </div>
      <p className="text-xs text-ink-faint">70% is how many of the listing's skills the resume names, 30% is the resume's overall score ({a.quality}).</p>
      {a.tips.length > 0 && <Tips tips={a.tips.slice(0, 3)} />}
    </div>
  )
}

function Tips({ tips }: { tips: string[] }) {
  return (
    <div className="rounded-lg border border-pear-line bg-pear-soft px-3 py-2 text-sm">
      <div className="flex items-center gap-1.5 font-medium"><Lightbulb className="h-4 w-4" aria-hidden />To make it stronger</div>
      <ul className="mt-1 list-disc space-y-0.5 pl-5 text-ink-soft">{tips.map((t) => <li key={t}>{t}</li>)}</ul>
    </div>
  )
}
