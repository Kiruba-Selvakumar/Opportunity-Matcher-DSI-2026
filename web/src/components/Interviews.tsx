import { useState, type FormEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Bot, CalendarClock, CalendarPlus, Download, MapPin, NotebookPen, Phone, Video } from 'lucide-react'
import { patch, post } from '../lib/api'
import type { Interview, ScheduleResult } from '../lib/types'
import { Badge, Banner } from './ui'
import { useToast } from './Toast'

type Side = 'ngo' | 'employer' | 'student'
const MODE_ICON = { meet: Video, phone: Phone, in_person: MapPin }
const MODE_WORD = { meet: 'Google Meet', phone: 'Phone', in_person: 'In person' }
const STATUS_TONE = { scheduled: 'sky', done: 'pass', cancelled: 'neutral', no_show: 'amber' } as const
const STATUS_WORD = { scheduled: 'Scheduled', done: 'Done', cancelled: 'Cancelled', no_show: 'Did not join' }

function soon(days = 2, hour = 11): string {
  const d = new Date(); d.setDate(d.getDate() + days); d.setHours(hour, 0, 0, 0)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:00`
}

/** Schedule an interview. `path` is the API route for the application; NGO staff also choose who interviews. */
export function ScheduleForm({ path, side, onDone, onCancel }: { path: string; side: 'ngo' | 'employer'; onDone: () => void; onCancel?: () => void }) {
  const toast = useToast()
  const [f, setF] = useState({ starts_at: soon(), minutes: 30, interviewer: 'employer', interviewer_email: '', mode: 'meet', location: '', meet_link: '', notetaker: true, invite_student: false })
  const [warnings, setWarnings] = useState<string[]>([])
  const set = (k: keyof typeof f, v: string | number | boolean) => setF((c) => ({ ...c, [k]: v }))
  const go = useMutation({
    mutationFn: () => post<ScheduleResult>(path, { ...f, interviewer_email: f.interviewer_email || null, location: f.location || null, meet_link: f.meet_link || null }),
    onSuccess: (r) => {
      toast(r.calendar === 'google' ? 'Scheduled. Google sent the invites with a Meet link.' : 'Scheduled. Invites went out by email with a calendar file.')
      setWarnings(r.warnings)
      if (r.warnings.length === 0) onDone()
    },
    onError: (e) => toast((e as Error).message, 'fail'),
  })
  const submit = (e: FormEvent) => { e.preventDefault(); go.mutate() }
  if (warnings.length > 0) return (
    <div className="pop space-y-2">
      {warnings.map((w) => <Banner key={w} tone="amber" lead="Note.">{w}</Banner>)}
      <button type="button" className="btn" onClick={() => { setWarnings([]); onDone() }}>OK</button>
    </div>
  )
  return (
    <form onSubmit={submit} className="pop grid gap-3 rounded-lg bg-bg p-3 sm:grid-cols-2 lg:grid-cols-3">
      <div><label className="label" htmlFor={`iv-when-${path}`}>When</label>
        <input id={`iv-when-${path}`} type="datetime-local" className="input" value={f.starts_at} onChange={(e) => set('starts_at', e.target.value)} required /></div>
      <div><label className="label" htmlFor={`iv-min-${path}`}>Minutes</label>
        <select id={`iv-min-${path}`} className="input" value={f.minutes} onChange={(e) => set('minutes', Number(e.target.value))}>{[15, 30, 45, 60, 90].map((m) => <option key={m}>{m}</option>)}</select></div>
      <div><label className="label" htmlFor={`iv-mode-${path}`}>How</label>
        <select id={`iv-mode-${path}`} className="input" value={f.mode} onChange={(e) => set('mode', e.target.value)}><option value="meet">Google Meet</option><option value="phone">Phone</option><option value="in_person">In person</option></select></div>
      {side === 'ngo' && <div><label className="label" htmlFor={`iv-who-${path}`}>Who interviews</label>
        <select id={`iv-who-${path}`} className="input" value={f.interviewer} onChange={(e) => set('interviewer', e.target.value)}><option value="employer">The employer</option><option value="ngo">The NGO</option></select></div>}
      <div><label className="label" htmlFor={`iv-email-${path}`}>Interviewer email (optional)</label>
        <input id={`iv-email-${path}`} type="email" className="input" value={f.interviewer_email} onChange={(e) => set('interviewer_email', e.target.value)} placeholder="Uses the account email if blank" /></div>
      {f.mode === 'meet' && <div><label className="label" htmlFor={`iv-link-${path}`}>Meeting link (optional)</label>
        <input id={`iv-link-${path}`} className="input" value={f.meet_link} onChange={(e) => set('meet_link', e.target.value)} placeholder="Made for you when Google is connected" /></div>}
      {f.mode === 'in_person' && <div className="sm:col-span-2"><label className="label" htmlFor={`iv-loc-${path}`}>Address</label>
        <input id={`iv-loc-${path}`} className="input" value={f.location} maxLength={200} onChange={(e) => set('location', e.target.value)} /></div>}
      <div className="flex flex-col justify-end gap-1.5 text-sm sm:col-span-2 lg:col-span-3">
        {f.mode === 'meet' && <label className="flex items-center gap-2"><input type="checkbox" checked={f.notetaker} onChange={(e) => set('notetaker', e.target.checked)} />Invite the notetaker, so there are notes even if nobody from the NGO can join</label>}
        {side === 'ngo' && <label className="flex items-center gap-2"><input type="checkbox" checked={f.invite_student} onChange={(e) => set('invite_student', e.target.checked)} />Also send the calendar invite to the student's email (other guests cannot see it)</label>}
      </div>
      <div className="flex gap-2 sm:col-span-2 lg:col-span-3">
        <button type="submit" className="btn btn-primary" disabled={go.isPending}><CalendarPlus className="h-4 w-4" aria-hidden />{go.isPending ? 'Scheduling' : 'Schedule and send invites'}</button>
        {onCancel && <button type="button" className="btn btn-quiet" onClick={onCancel}>Cancel</button>}
      </div>
    </form>
  )
}

/** Interviews for one application or many. Students see when and how; the NGO and the employer can also move, cancel and take notes. */
export function InterviewList({ items, side, onChanged, showTitle = false }: { items: Interview[]; side: Side; onChanged?: () => void; showTitle?: boolean }) {
  if (items.length === 0) return null
  return <ul className="space-y-2">{items.map((iv) => <InterviewRow key={iv.id} iv={iv} side={side} onChanged={onChanged} showTitle={showTitle} />)}</ul>
}

function InterviewRow({ iv, side, onChanged, showTitle }: { iv: Interview; side: Side; onChanged?: () => void; showTitle: boolean }) {
  const toast = useToast()
  const [open, setOpen] = useState<null | 'move' | 'notes'>(null)
  const [when, setWhen] = useState(iv.starts_at.slice(0, 16))
  const [text, setText] = useState('')
  const [due, setDue] = useState('')
  const done = (msg: string) => { toast(msg); setOpen(null); setText(''); onChanged?.() }
  const fail = (e: unknown) => toast((e as Error).message, 'fail')
  const change = useMutation({ mutationFn: (body: Record<string, unknown>) => patch(`/api/interviews/${iv.id}`, body), onSuccess: () => done('Updated. Everyone invited has been told.'), onError: fail })
  const notes = useMutation({ mutationFn: () => post(`/api/interviews/${iv.id}/notes`, { text }), onSuccess: () => done('Notes saved.'), onError: fail })
  const fetchNotes = useMutation({ mutationFn: () => post(`/api/interviews/${iv.id}/fetch-notes`, {}), onSuccess: () => done('Notes fetched from Fireflies.'), onError: fail })
  const bot = useMutation({ mutationFn: () => post(`/api/interviews/${iv.id}/notetaker`, {}), onSuccess: () => toast('The notetaker is joining the meeting.'), onError: fail })
  const toCase = useMutation({ mutationFn: () => post(`/api/interviews/${iv.id}/to-case-notes`, { follow_up_on: due || null }), onSuccess: () => done('Added to the case notes.'), onError: fail })
  const Icon = MODE_ICON[iv.mode]
  const live = iv.status === 'scheduled'
  return (
    <li className="rounded-lg border border-line bg-surface p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <CalendarClock className="h-4 w-4 text-ink-soft" aria-hidden />
        <span className="font-medium">{iv.when}</span><span className="text-ink-soft">· {iv.minutes} min</span>
        <span className="inline-flex items-center gap-1 text-ink-soft"><Icon className="h-3.5 w-3.5" aria-hidden />{MODE_WORD[iv.mode]}</span>
        <Badge tone={STATUS_TONE[iv.status]}>{STATUS_WORD[iv.status]}</Badge>
        {side !== 'student' && <Badge tone="neutral">{iv.interviewer === 'ngo' ? 'NGO interviews' : 'Employer interviews'}</Badge>}
        {iv.notetaker && side !== 'student' && <Badge tone="plum"><Bot className="h-3 w-3" aria-hidden />Notetaker</Badge>}
        {showTitle && iv.title && <span className="text-ink-soft">· {iv.title}{iv.candidate_code && <span className="font-mono text-xs"> · {iv.candidate_code}</span>}{side === 'ngo' && iv.student_id && <span className="font-mono text-xs"> · {iv.student_id}</span>}</span>}
      </div>
      {live && iv.mode === 'meet' && iv.meet_link && <a className="mt-1.5 inline-flex items-center gap-1 text-accent underline" href={iv.meet_link} target="_blank" rel="noreferrer"><Video className="h-3.5 w-3.5" aria-hidden />Join the meeting</a>}
      {iv.mode === 'in_person' && iv.location && <p className="mt-1 text-ink-soft">{iv.location}</p>}
      {side === 'student' && live && iv.mode === 'phone' && <p className="mt-1 text-ink-soft">The NGO will call you at this time.</p>}

      {side !== 'student' && (iv.summary || (iv.action_items?.length ?? 0) > 0) && (
        <div className="mt-2 rounded-md bg-bg px-3 py-2">
          {iv.summary && <p>{iv.summary}</p>}
          {(iv.action_items?.length ?? 0) > 0 && <><div className="mt-1 text-xs font-medium uppercase tracking-[0.06em] text-ink-soft">Action points</div>
            <ul className="list-disc pl-5">{iv.action_items!.map((a) => <li key={a}>{a}</li>)}</ul></>}
          {iv.notes_source && <p className="mt-1 text-xs text-ink-faint">From {iv.notes_source}.</p>}
        </div>)}

      {side !== 'student' && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {live && <button type="button" className="btn !py-0.5" onClick={() => setOpen(open === 'move' ? null : 'move')}>Move</button>}
          {live && <button type="button" className="btn btn-quiet !py-0.5" onClick={() => change.mutate({ status: 'cancelled' })}>Cancel it</button>}
          {live && <button type="button" className="btn btn-quiet !py-0.5" onClick={() => change.mutate({ status: 'done' })}>Mark done</button>}
          <button type="button" className="btn btn-quiet !py-0.5" onClick={() => setOpen(open === 'notes' ? null : 'notes')}><NotebookPen className="h-3.5 w-3.5" aria-hidden />Paste notes</button>
          {side === 'ngo' && iv.mode === 'meet' && <button type="button" className="btn btn-quiet !py-0.5" disabled={fetchNotes.isPending} onClick={() => fetchNotes.mutate()}>Fetch notes</button>}
          {side === 'ngo' && live && iv.mode === 'meet' && iv.meet_link && <button type="button" className="btn btn-quiet !py-0.5" disabled={bot.isPending} onClick={() => bot.mutate()}><Bot className="h-3.5 w-3.5" aria-hidden />Send notetaker now</button>}
          <a className="btn btn-quiet !py-0.5" href={`/api/interviews/${iv.id}/invite.ics`}><Download className="h-3.5 w-3.5" aria-hidden />Calendar file</a>
        </div>)}
      {open === 'move' && (
        <form className="pop mt-2 flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); change.mutate({ starts_at: when }) }}>
          <div><label className="label" htmlFor={`mv-${iv.id}`}>New time</label><input id={`mv-${iv.id}`} type="datetime-local" className="input" value={when} onChange={(e) => setWhen(e.target.value)} /></div>
          <button type="submit" className="btn btn-primary" disabled={change.isPending}>Move and tell everyone</button>
        </form>)}
      {open === 'notes' && (
        <form className="pop mt-2 space-y-2" onSubmit={(e) => { e.preventDefault(); notes.mutate() }}>
          <label className="label" htmlFor={`nt-${iv.id}`}>Transcript or notes</label>
          <textarea id={`nt-${iv.id}`} className="input min-h-[110px]" maxLength={30000} value={text} onChange={(e) => setText(e.target.value)}
            placeholder="Paste the Meet transcript, or type what was agreed. Names, phones and emails are taken out." />
          <button type="submit" className="btn btn-primary" disabled={!text.trim() || notes.isPending}>Pull out the action points</button>
        </form>)}
      {side === 'ngo' && (iv.action_items?.length ?? 0) > 0 && (
        <div className="mt-2 flex flex-wrap items-end gap-2 border-t border-line pt-2">
          <div><label className="label" htmlFor={`fu-${iv.id}`}>Follow up on (optional)</label><input id={`fu-${iv.id}`} type="date" className="input" value={due} onChange={(e) => setDue(e.target.value)} /></div>
          <button type="button" className="btn" disabled={toCase.isPending} onClick={() => toCase.mutate()}>Add action points to case notes</button>
        </div>)}
    </li>
  )
}
