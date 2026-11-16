import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { FileUp, UserSearch } from 'lucide-react'
import { get } from '../../lib/api'
import { useApp } from '../../lib/app-context'
import { cn } from '../../lib/utils'
import { rupees } from '../../lib/format'
import { PROGRAM_WORD, type Program, type StudentRef } from '../../lib/types'
import { Badge, Empty, ErrorState, PageHeader } from '../../components/ui'
import { DataTable, type Column } from '../../components/DataTable'
import { TableSkeleton } from '../../components/Skeleton'
import { SearchBox } from '../../components/SearchBox'

const unknown = <Badge tone="amber">not known</Badge>

export default function Students() {
  const { studentId, setStudentId, showNames } = useApp()
  const nav = useNavigate()
  const [q, setQ] = useState('')
  const [branches, setBranches] = useState<string[]>([])
  const [onlyMissing, setOnlyMissing] = useState(false)
  const [onlyEdited, setOnlyEdited] = useState(false)
  const [program, setProgram] = useState<Program | null>(null)
  const [noResume, setNoResume] = useState(false)
  const list = useQuery({ queryKey: ['students'], queryFn: () => get<StudentRef[]>('/api/students') })
  const names = useQuery({ queryKey: ['contacts'], queryFn: () => get<Record<string, string>>('/api/contacts'), enabled: showNames })

  const allBranches = useMemo(() => [...new Set((list.data ?? []).map((s) => s.branch))].sort(), [list.data])
  const rows = useMemo(() => {
    const terms = q.toLowerCase().split(/\s+/).filter(Boolean)
    return (list.data ?? []).filter((s) => {
      if (branches.length && !branches.includes(s.branch)) return false
      if (onlyMissing && s.missing_fields.length === 0) return false
      if (onlyEdited && s.edited.length === 0) return false
      if (program && s.program !== program) return false
      if (noResume && s.has_resume) return false
      const hay = [s.id, s.candidate_code, s.branch, s.town, s.college, PROGRAM_WORD[s.program], ...s.skills, showNames ? names.data?.[s.id] ?? '' : ''].join(' ').toLowerCase()
      return terms.every((t) => hay.includes(t))
    })
  }, [list.data, q, branches, onlyMissing, onlyEdited, program, noResume, showNames, names.data])

  const open = (id: string, to: string) => { setStudentId(id); nav(to) }
  const chip = (on: boolean, tone: 'accent' | 'amber' | 'sky' = 'accent') => cn('rounded-full border px-2.5 py-1 text-xs font-medium transition-colors duration-150',
    on ? { accent: 'border-accent bg-accent-soft text-accent', amber: 'border-amber-line bg-amber-soft text-amber', sky: 'border-sky-line bg-sky-soft text-sky' }[tone] : 'border-line-strong bg-surface text-ink-soft hover:bg-sunk')

  const cols: Column<StudentRef>[] = [
    { key: 'id', header: 'Student', sort: (s) => s.id, csv: (s) => s.id,
      render: (s) => <><div className="font-mono text-xs">{s.id}</div><div className="font-mono text-[11px] text-ink-faint" title="The code an employer sees">{s.candidate_code}</div>{showNames && names.data?.[s.id] && <div className="text-sm font-medium">{names.data[s.id]}</div>}</> },
    { key: 'program', header: 'Program', sort: (s) => s.program, csv: (s) => PROGRAM_WORD[s.program], render: (s) => <Badge tone={s.program === 'get_skills' ? 'plum' : 'navy'}>{PROGRAM_WORD[s.program]}</Badge> },
    { key: 'branch', header: 'Branch', sort: (s) => s.branch, csv: (s) => s.branch, render: (s) => s.branch },
    { key: 'college', header: 'College', sort: (s) => s.college, csv: (s) => s.college, className: 'max-w-[22ch]', render: (s) => <><div>{s.college}</div><div className="text-xs text-ink-faint">{s.town}</div></> },
    { key: 'cgpa', header: 'CGPA', sort: (s) => s.cgpa, csv: (s) => s.cgpa, render: (s) => (s.cgpa != null ? s.cgpa.toFixed(1) : unknown) },
    { key: 'skills', header: 'Skills', sort: (s) => s.skills.length, csv: (s) => s.skills.join('; '), className: 'max-w-[30ch]',
      render: (s) => <div className="flex flex-wrap gap-1">{s.skills.slice(0, 4).map((k) => <Badge key={k} tone="accent">{k}</Badge>)}{s.skills.length > 4 && <span className="text-xs text-ink-faint">+{s.skills.length - 4}</span>}</div> },
    { key: 'reloc', header: 'Can relocate', sort: (s) => (s.can_relocate === null ? 2 : s.can_relocate ? 0 : 1), csv: (s) => (s.can_relocate === null ? '' : s.can_relocate ? 'yes' : 'no'), render: (s) => (s.can_relocate === true ? 'Yes' : s.can_relocate === false ? 'No' : unknown) },
    { key: 'budget', header: 'Budget', sort: (s) => s.budget, csv: (s) => s.budget, render: (s) => (s.budget != null ? rupees(s.budget) : unknown) },
    { key: 'resume', header: 'Resume', sort: (s) => s.resume_score ?? -1, csv: (s) => s.resume_score ?? '', render: (s) => (s.has_resume ? <Badge tone={(s.resume_score ?? 0) >= 75 ? 'pass' : (s.resume_score ?? 0) >= 50 ? 'sky' : 'amber'}>{s.resume_score}</Badge> : <span className="text-xs text-ink-faint">none</span>) },
    { key: 'best', header: 'Best match', sort: (s) => s.best_match ?? '', csv: (s) => s.best_match ?? '', className: 'max-w-[24ch] text-ink-soft', render: (s) => s.best_match ?? 'None eligible' },
    { key: 'edit', header: '', render: (s) => <div className="flex flex-col items-start gap-1">{s.whatsapp && <Badge tone="pass">WhatsApp</Badge>}{s.edited.length > 0 && <Badge tone="sky">edited</Badge>}<button type="button" className="btn btn-quiet" onClick={(e) => { e.stopPropagation(); open(s.id, `/ngo/messages?thread=student:${s.id}`) }}>Message</button></div> },
  ]

  return (
    <>
      <PageHeader title="Students" sub={`Find a student by ID, candidate code, program, branch, college or skill${showNames ? ', or by name' : ''}. Pick one to see their matches, resume and learning plan.`}
        actions={<Link to="/ngo/students/resumes" className="btn"><FileUp className="h-4 w-4" aria-hidden />Upload resumes</Link>} />
      <div className="space-y-4 px-4 py-6 sm:px-8">
        <SearchBox value={q} onChange={setQ} label="Search students" placeholder="Search by ID, candidate code, branch, town or skill. Try: python khammam   (press / to jump here)" />
        <div className="flex flex-wrap items-center gap-1.5">
          {allBranches.map((b) => <button key={b} type="button" aria-pressed={branches.includes(b)} className={chip(branches.includes(b))} onClick={() => setBranches((c) => (c.includes(b) ? c.filter((x) => x !== b) : [...c, b]))}>{b}</button>)}
          <span className="mx-1 h-4 w-px bg-line-strong" aria-hidden />
          {(Object.keys(PROGRAM_WORD) as Program[]).map((pg) => <button key={pg} type="button" aria-pressed={program === pg} className={chip(program === pg, 'sky')} onClick={() => setProgram(program === pg ? null : pg)}>{PROGRAM_WORD[pg]}</button>)}
          <span className="mx-1 h-4 w-px bg-line-strong" aria-hidden />
          <button type="button" aria-pressed={onlyMissing} className={chip(onlyMissing, 'amber')} onClick={() => setOnlyMissing(!onlyMissing)}>Missing info only</button>
          <button type="button" aria-pressed={noResume} className={chip(noResume, 'amber')} onClick={() => setNoResume(!noResume)}>No resume yet</button>
          <button type="button" aria-pressed={onlyEdited} className={chip(onlyEdited, 'sky')} onClick={() => setOnlyEdited(!onlyEdited)}>Edited by the student</button>
        </div>
        {list.isLoading && <TableSkeleton rows={8} />}
        {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
        {list.data && rows.length === 0 && <Empty icon={UserSearch} title="No students match">Try fewer words, or clear the filters.</Empty>}
        {rows.length > 0 && <DataTable columns={cols} rows={rows} rowKey={(s) => s.id} selectedKey={studentId} onRowClick={(s) => open(s.id, `/ngo/students/${s.id}`)} csvName="students" initialSort={{ key: 'id', dir: 'asc' }} />}
      </div>
    </>
  )
}
