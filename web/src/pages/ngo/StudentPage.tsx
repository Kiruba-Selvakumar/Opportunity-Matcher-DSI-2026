import { useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Columns2, FileUp, MessageSquare, Phone } from 'lucide-react'
import { get, post, put, upload } from '../../lib/api'
import { useApp } from '../../lib/app-context'
import { PROGRAM_WORD, type Consent, type ContactChange, type Profile, type ResumeSummary } from '../../lib/types'
import { Badge, ErrorState, PageHeader, Section, Tabs } from '../../components/ui'
import { AtsReport, ResumeViewer } from '../../components/Resume'
import { LearningPlanView } from '../../components/LearningPlan'
import { useToast } from '../../components/Toast'
import { MatchesPanel } from './Match'
import { NotesPanel, Timeline } from './CaseWork'

const TABS = [{ id: 'matches', label: 'Matches' }, { id: 'resume', label: 'Resume' }, { id: 'plan', label: 'Learning plan' }, { id: 'notes', label: 'Case notes' }]

/** One student: their matches (with the resume beside them if you like), resume and score, learning plan and case notes. */
export default function StudentPage() {
  const { sid = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const tab = TABS.some((t) => t.id === params.get('tab')) ? params.get('tab')! : 'matches'
  const { showNames, setStudentId } = useApp()
  const [beside, setBeside] = useState(false)
  useEffect(() => { setStudentId(sid) }, [sid, setStudentId])
  const profile = useQuery({ queryKey: ['profile', sid], queryFn: () => get<Profile>(`/api/students/${sid}`) })
  const name = useQuery({ queryKey: ['name', sid, showNames], queryFn: () => get<{ name: string | null }>(`/api/contacts/${sid}`), enabled: showNames })
  const p = profile.data
  const hasResume = !!p?.resume

  const title = showNames && name.data?.name ? `${name.data.name} (${sid})` : `Student ${sid}`
  const sub = p ? [p.branch, p.college || p.college_town, p.program ? `${PROGRAM_WORD[p.program]} program` : null].filter(Boolean).join(' · ') : 'Loading the student.'
  return (
    <>
      <PageHeader title={title} sub={sub}
        actions={<div className="flex flex-wrap gap-2">
          <Link to={`/ngo/messages?thread=student:${sid}`} className="btn"><MessageSquare className="h-4 w-4" aria-hidden />Message</Link>
          <Link to="/ngo/students" className="btn"><ArrowLeft className="h-4 w-4" aria-hidden />All students</Link></div>} />
      <div className="px-4 pb-16 sm:px-8">
        {profile.error && <div className="pt-6"><ErrorState error={profile.error} onRetry={() => profile.refetch()} /></div>}
        <NumberChange sid={sid} />
        <div className="flex flex-wrap items-end justify-between gap-3 pt-5">
          <Tabs tabs={TABS} value={tab} onChange={(t) => setParams({ tab: t })} />
          {tab === 'matches' && hasResume && (
            <button type="button" className="btn btn-quiet hidden xl:inline-flex" aria-pressed={beside} onClick={() => setBeside(!beside)}><Columns2 className="h-4 w-4" aria-hidden />{beside ? 'Hide the resume' : 'Show the resume beside the matches'}</button>)}
        </div>
        {tab === 'matches' && (
          <div className={beside ? 'grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]' : ''}>
            <div className="min-w-0"><MatchesPanel sid={sid} /></div>
            {beside && <div className="min-w-0 pt-6 xl:sticky xl:top-4 xl:self-start"><ResumeViewer src={`/api/students/${sid}/resume.pdf`} height={820} /></div>}
          </div>)}
        {tab === 'resume' && p && <ResumeTab sid={sid} resume={p.resume ?? null} consent={p.consent} />}
        {tab === 'plan' && (
          <Section title="Learning plan">
            <p className="mb-4 max-w-[75ch] text-sm text-ink-soft">Courses and mentors this student can take, one after another, what they do for each of their best jobs, and whether they would be ready before each last day to apply. Useful for students in the Get Skills program, and for anyone with a gap.</p>
            <LearningPlanView path={`/api/students/${sid}/plan`} />
          </Section>)}
        {tab === 'notes' && (
          <>
            <Section title="Case notes"><NotesPanel sid={sid} /></Section>
            <Section title="Timeline"><Timeline sid={sid} /></Section>
          </>)}
      </div>
    </>
  )
}

function ResumeTab({ sid, resume, consent }: { sid: string; resume: ResumeSummary | null; consent?: Consent }) {
  const qc = useQueryClient()
  const toast = useToast()
  const file = useRef<HTMLInputElement>(null)
  const refresh = () => { qc.invalidateQueries({ queryKey: ['profile', sid] }); qc.invalidateQueries({ queryKey: ['matches', sid] }); qc.invalidateQueries({ queryKey: ['students'] }) }
  const send = useMutation({
    mutationFn: (f: File) => { const d = new FormData(); d.append('file', f); return upload<ResumeSummary>(`/api/students/${sid}/resume`, d) },
    onSuccess: () => { toast('Resume saved and scored.'); refresh() }, onError: (e) => toast((e as Error).message, 'fail'),
  })
  const agree = useMutation({
    mutationFn: (on: boolean) => put<Consent>(`/api/students/${sid}/consent`, { whatsapp: on }),
    onSuccess: (c) => { toast(c.whatsapp ? 'Recorded: the student agreed to WhatsApp updates.' : 'Recorded: no WhatsApp updates.'); refresh() },
    onError: (e) => toast((e as Error).message, 'fail'),
  })
  return (
    <>
      <Section title="Resume" right={
        <>
          <input ref={file} id="cv-up" type="file" accept="application/pdf,.pdf" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; if (f) send.mutate(f); e.target.value = '' }} />
          <label htmlFor="cv-up" className="btn cursor-pointer"><FileUp className="h-4 w-4" aria-hidden />{send.isPending ? 'Reading' : resume ? 'Replace the resume' : 'Upload a resume'}</label>
        </>}>
        <div className={resume ? 'grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]' : ''}>
          <AtsReport r={resume} />
          {resume && <ResumeViewer src={`/api/students/${sid}/resume.pdf?v=${encodeURIComponent(resume.uploaded_at)}`} />}
        </div>
        <p className="mt-3 max-w-[75ch] text-xs text-ink-faint">Only NGO staff and the student can open the resume. Employers never get the file; they see the anonymous profile. Each opening is written to the audit log.</p>
      </Section>
      <Section title="WhatsApp updates">
        <div className="card flex flex-wrap items-center justify-between gap-3 p-4 text-sm">
          <div>
            {consent?.whatsapp ? <Badge tone="pass">Agreed</Badge> : <Badge tone="neutral">Not agreed</Badge>}
            <span className="ml-2 text-ink-soft">{consent?.recorded_by ? `Recorded by ${consent.recorded_by.replace('staff:', '')}${consent.updated_at ? ` on ${consent.updated_at.slice(0, 10)}` : ''}.` : 'Nobody has asked yet.'}</span>
            {!consent?.reachable && <span className="ml-2 text-amber">There is no usable mobile number on file.</span>}
          </div>
          <button type="button" className="btn" disabled={agree.isPending} onClick={() => agree.mutate(!consent?.whatsapp)}>{consent?.whatsapp ? 'Record that they said no' : 'Record that they agreed'}</button>
        </div>
      </Section>
    </>
  )
}

/** A new mobile number the student asked for. Nothing uses it until staff approve, so a typo never gets their messages. */
function NumberChange({ sid }: { sid: string }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [note, setNote] = useState('')
  const q = useQuery({ queryKey: ['number-change', sid], queryFn: () => get<ContactChange[]>(`/api/contact-changes?student_id=${sid}`) })
  const decide = useMutation({
    mutationFn: ({ id, approve }: { id: number; approve: boolean }) => post(`/api/contact-changes/${id}/decision`, { approve, note }),
    onSuccess: (_, v) => { toast(v.approve ? 'New number approved. The student was told.' : 'Request turned down. The student was told.'); setNote(''); qc.invalidateQueries({ queryKey: ['number-change', sid] }); qc.invalidateQueries({ queryKey: ['dashboard'] }) },
    onError: (e) => toast((e as Error).message, 'fail'),
  })
  const c = q.data?.[0]
  if (!c) return null
  return (
    <div className="mt-5 rounded-lg border border-amber-line bg-amber-soft p-4 text-sm" role="status">
      <p className="flex flex-wrap items-center gap-2 font-medium text-ink"><Phone className="h-4 w-4 text-amber" aria-hidden />
        This student asked to change their mobile number to <span className="font-mono tabular-nums">+{c.phone.slice(0, 2)} {c.phone.slice(2, 7)} {c.phone.slice(7)}</span>
        <span className="font-normal text-ink-soft">(now {c.current ?? 'none on file'}, asked {c.requested_at.slice(0, 10)})</span></p>
      <p className="mt-1 text-ink-soft">Check it with the student, by a call or in person, before you approve. WhatsApp and emails about interviews go to this number.</p>
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <div className="min-w-[240px] flex-1"><label className="label" htmlFor={`nc-${c.id}`}>Note to the student (optional)</label>
          <input id={`nc-${c.id}`} className="input" maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} placeholder="For example: we could not reach this number." /></div>
        <button type="button" className="btn btn-primary" disabled={decide.isPending} onClick={() => decide.mutate({ id: c.id, approve: true })}>Approve</button>
        <button type="button" className="btn" disabled={decide.isPending} onClick={() => decide.mutate({ id: c.id, approve: false })}>Turn down</button>
      </div>
    </div>
  )
}
