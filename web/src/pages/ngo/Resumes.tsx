import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, CircleCheck, CircleX, FileUp, Files } from 'lucide-react'
import { get, post, upload } from '../../lib/api'
import { useApp } from '../../lib/app-context'
import type { StudentRef } from '../../lib/types'
import { Badge, Banner, PageHeader, Section, Tabs } from '../../components/ui'
import { useToast } from '../../components/Toast'
import Intake from './Intake'

interface Proposal { file: string; student_id: string | null; how: 'id' | 'code' | 'name' | 'ambiguous' | null; options?: string[]; replaces?: boolean }
interface Result { file: string; student_id: string | null; ok: boolean; message: string; score?: number }
const HOW: Record<string, [string, 'pass' | 'amber' | 'neutral']> = {
  id: ['Student ID in the file name', 'pass'], code: ['Candidate code in the file name', 'pass'],
  name: ['Looks like this student by name: choose to confirm', 'amber'], ambiguous: ['More than one student has this name', 'amber'],
}
const MAX = 25

/** Upload many resumes at once. Each file is matched to a student by its name; staff check the list, then save. */
export default function Resumes() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') === 'check' ? 'check' : 'bulk'
  return (
    <>
      <PageHeader title="Resumes" sub="Upload many resumes at once and each one is scored and attached to its student. Or check a single resume without saving anything."
        actions={<Link to="/ngo/students" className="btn"><ArrowLeft className="h-4 w-4" aria-hidden />Students</Link>} />
      <div className="px-4 pb-16 sm:px-8">
        <div className="pt-5"><Tabs tabs={[{ id: 'bulk', label: 'Upload many' }, { id: 'check', label: 'Quick check (not saved)' }]} value={tab} onChange={(t) => setParams({ tab: t })} /></div>
        {tab === 'bulk' ? <Bulk /> : <Intake embedded />}
      </div>
    </>
  )
}

function Bulk() {
  const qc = useQueryClient()
  const toast = useToast()
  const { showNames } = useApp()
  const [files, setFiles] = useState<File[]>([])
  const [plan, setPlan] = useState<Record<string, string>>({})
  const [proposals, setProposals] = useState<Proposal[]>([])
  const [results, setResults] = useState<Result[] | null>(null)
  const students = useQuery({ queryKey: ['students'], queryFn: () => get<StudentRef[]>('/api/students') })
  const names = useQuery({ queryKey: ['contacts'], queryFn: () => get<Record<string, string>>('/api/contacts'), enabled: showNames })

  const match = useMutation({
    mutationFn: (list: File[]) => post<Proposal[]>('/api/resumes/match', { filenames: list.map((f) => f.name) }),
    // an ID or a candidate code is certain; a name is only a suggestion, so staff pick it themselves
    onSuccess: (ps) => { setProposals(ps); setPlan(Object.fromEntries(ps.map((x) => [x.file, x.how === 'id' || x.how === 'code' ? x.student_id ?? '' : '']))) },
    onError: (e) => toast((e as Error).message, 'fail'),
  })
  const save = useMutation({
    mutationFn: () => {
      const d = new FormData()
      files.forEach((f) => d.append('files', f, f.name))
      d.append('mapping', JSON.stringify(plan))
      return upload<{ saved: number; results: Result[] }>('/api/resumes/bulk', d)
    },
    onSuccess: (r) => { setResults(r.results); toast(`${r.saved} resume${r.saved === 1 ? '' : 's'} saved.`); qc.invalidateQueries({ queryKey: ['students'] }) },
    onError: (e) => toast((e as Error).message, 'fail'),
  })

  const pick = (list: FileList | null) => {
    const pdfs = [...(list ?? [])].filter((f) => /\.pdf$/i.test(f.name)).slice(0, MAX)
    if (!pdfs.length) return
    setFiles(pdfs); setResults(null); match.mutate(pdfs)
  }
  const label = (s: StudentRef) => `${s.id} · ${s.branch} · ${s.town}${showNames && names.data?.[s.id] ? ` · ${names.data[s.id]}` : ''}`
  const chosen = Object.values(plan).filter(Boolean).length

  return (
    <>
      <Section title="1. Choose the files">
        <label htmlFor="bulk-files" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); pick(e.dataTransfer.files) }}
          className="card flex cursor-pointer flex-col items-center gap-2 border-dashed p-8 text-center hover:bg-[#f6f0e3]">
          <Files className="h-6 w-6 text-ink-soft" aria-hidden />
          <span className="font-medium">Drop up to {MAX} resume PDFs here, or click to choose</span>
          <span className="max-w-[60ch] text-sm text-ink-soft">Name each file with the student ID (for example <span className="font-mono">S014_resume.pdf</span>) or the candidate code, and it is matched for you. Files named after the student are matched by name, and you check them.</span>
        </label>
        <input id="bulk-files" type="file" multiple accept="application/pdf,.pdf" className="sr-only" onChange={(e) => { pick(e.target.files); e.target.value = '' }} />
      </Section>

      {proposals.length > 0 && !results && (
        <Section title="2. Check who each file belongs to">
          <div className="card overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead><tr>{['File', 'How we matched it', 'Student', ''].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
              <tbody>{proposals.map((x) => (
                <tr key={x.file}>
                  <td className="td font-mono text-xs">{x.file}</td>
                  <td className="td">{x.how ? <Badge tone={HOW[x.how][1]}>{HOW[x.how][0]}</Badge> : <Badge tone="neutral">Not found: choose the student</Badge>}</td>
                  <td className="td min-w-[260px]">
                    <label className="sr-only" htmlFor={`m-${x.file}`}>Student for {x.file}</label>
                    <select id={`m-${x.file}`} className="input" value={plan[x.file] ?? ''} onChange={(e) => setPlan({ ...plan, [x.file]: e.target.value })}>
                      <option value="">Skip this file</option>
                      {(students.data ?? []).filter((s) => (x.how === 'name' ? [x.student_id] : x.options ?? []).includes(s.id)).map((s) => <option key={`o-${s.id}`} value={s.id}>{label(s)} (suggested by name)</option>)}
                      {(students.data ?? []).map((s) => <option key={s.id} value={s.id}>{label(s)}</option>)}
                    </select>
                  </td>
                  <td className="td">{x.replaces && plan[x.file] === x.student_id && <Badge tone="sky">Replaces their resume</Badge>}</td>
                </tr>))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex items-center gap-3">
            <button type="button" className="btn btn-primary" disabled={!chosen || save.isPending} onClick={() => save.mutate()}><FileUp className="h-4 w-4" aria-hidden />{save.isPending ? 'Saving' : `Save ${chosen} resume${chosen === 1 ? '' : 's'}`}</button>
            <span className="text-xs text-ink-faint">Only NGO staff and the student can open a saved resume. Employers never get the file.</span>
          </div>
        </Section>
      )}

      {results && (
        <Section title="Done">
          {results.some((r) => !r.ok && r.student_id) && <div className="mb-3"><Banner tone="amber" lead="Some files were not saved.">Most often the PDF is a scan with no text. Ask for a PDF exported from Word or Google Docs.</Banner></div>}
          <ul className="space-y-1.5 text-sm">{results.map((r) => (
            <li key={r.file} className="flex flex-wrap items-center gap-2">
              {r.ok ? <CircleCheck className="h-4 w-4 text-pass" aria-hidden /> : <CircleX className="h-4 w-4 text-ink-faint" aria-hidden />}
              <span className="font-mono text-xs">{r.file}</span>
              {r.student_id && <Link to={`/ngo/students/${r.student_id}?tab=resume`} className="font-mono text-xs underline">{r.student_id}</Link>}
              <span className="text-ink-soft">{r.message}</span>{r.ok && r.score != null && <Badge tone="sky">score {r.score}</Badge>}
            </li>))}
          </ul>
          <button type="button" className="btn mt-4" onClick={() => { setFiles([]); setProposals([]); setResults(null) }}>Upload more</button>
        </Section>
      )}
    </>
  )
}
