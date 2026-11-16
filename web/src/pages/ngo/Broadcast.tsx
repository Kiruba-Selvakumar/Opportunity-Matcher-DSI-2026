import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Megaphone, Send } from 'lucide-react'
import { get, post } from '../../lib/api'
import { PROGRAM_WORD, type BroadcastPlan, type OpportunityRow, type Program } from '../../lib/types'
import { Badge, Banner, Section } from '../../components/ui'
import { useConfirm } from '../../components/Confirm'
import { useToast } from '../../components/Toast'

const KINDS = [
  { id: 'opportunity', label: 'A new opportunity', help: 'Send one listing to the students it fits best.' },
  { id: 'matches', label: 'Your matches are ready', help: 'Tell students how many matches they have and the best one.' },
  { id: 'update', label: 'An update from the NGO', help: 'A short note, for example a mock interview day.' },
] as const
const BRANCHES = ['CSE', 'CSE (AI and ML)', 'CSE (Data Science)', 'IT', 'ECE', 'EEE']

/** Bulk WhatsApp. Plan first (who it reaches, who has not agreed), then send. Only students who agreed get a message. */
export default function Broadcast() {
  const [params] = useSearchParams()
  const toast = useToast()
  const confirm = useConfirm()
  const [f, setF] = useState({ kind: params.get('opp') ? 'opportunity' : 'matches', opp_id: params.get('opp') ?? '', program: '', branch: '', text: '', min_score: 0.4, limit: 100 })
  const [sent, setSent] = useState<{ batch_id: string; queued: number; live: boolean } | null>(null)
  const set = (k: keyof typeof f, v: string | number) => { setF((c) => ({ ...c, [k]: v })); setSent(null) }
  const opps = useQuery({ queryKey: ['opportunities'], queryFn: () => get<OpportunityRow[]>('/api/opportunities') })
  const body = { ...f, opp_id: f.opp_id || null, program: f.program || null, branch: f.branch || null }
  const plan = useMutation({ mutationFn: () => post<BroadcastPlan>('/api/broadcasts/preview', body), onError: (e) => toast((e as Error).message, 'fail') })
  const send = useMutation({
    mutationFn: () => post<{ batch_id: string; queued: number; live: boolean }>('/api/broadcasts', body),
    onSuccess: (r) => { setSent(r); toast(`${r.queued} message${r.queued === 1 ? '' : 's'} on the way.`) }, onError: (e) => toast((e as Error).message, 'fail'),
  })
  const go = async () => {
    if (!plan.data) return
    if (await confirm({ title: `Send to ${plan.data.reachable} student${plan.data.reachable === 1 ? '' : 's'}?`, body: plan.data.live ? 'This sends real WhatsApp messages now. It cannot be taken back.' : 'WhatsApp is not connected, so this is a dry run: the messages are recorded but not sent.', confirmLabel: 'Send' })) send.mutate()
  }
  const p = plan.data
  return (
    <div className="max-w-3xl">
      <Section title="What to send">
        <div className="card grid gap-4 p-5 sm:grid-cols-2">
          <fieldset className="sm:col-span-2"><legend className="label">Message</legend>
            <div className="grid gap-2 sm:grid-cols-3">{KINDS.map((k) => (
              <label key={k.id} className={`cursor-pointer rounded-lg border p-3 text-sm ${f.kind === k.id ? 'border-accent bg-accent-soft' : 'border-line hover:bg-sunk'}`}>
                <input type="radio" name="kind" className="sr-only" checked={f.kind === k.id} onChange={() => set('kind', k.id)} />
                <span className="font-medium">{k.label}</span><span className="mt-0.5 block text-xs text-ink-soft">{k.help}</span></label>))}</div></fieldset>
          {f.kind === 'opportunity' && <div className="sm:col-span-2"><label className="label" htmlFor="b-opp">Listing</label>
            <select id="b-opp" className="input" value={f.opp_id} onChange={(e) => set('opp_id', e.target.value)}><option value="">Choose a listing</option>
              {(opps.data ?? []).map((o) => <option key={o.opp_id} value={o.opp_id}>{o.title} · {o.org_name} ({o.eligible_count} fit)</option>)}</select></div>}
          {f.kind === 'update' && <div className="sm:col-span-2"><label className="label" htmlFor="b-text">Update</label>
            <textarea id="b-text" className="input min-h-[80px]" maxLength={300} value={f.text} onChange={(e) => set('text', e.target.value)} placeholder="Mock interviews this Saturday, 10 am, at the NGO office." />
            <p className="mt-1 text-xs text-ink-faint">{f.text.length}/300. Phone numbers, emails and names are taken out.</p></div>}
          <div><label className="label" htmlFor="b-prog">Program</label>
            <select id="b-prog" className="input" value={f.program} onChange={(e) => set('program', e.target.value)}><option value="">Everyone</option>{(Object.keys(PROGRAM_WORD) as Program[]).map((pg) => <option key={pg} value={pg}>{PROGRAM_WORD[pg]}</option>)}</select></div>
          <div><label className="label" htmlFor="b-branch">Branch</label>
            <select id="b-branch" className="input" value={f.branch} onChange={(e) => set('branch', e.target.value)}><option value="">Every branch</option>{BRANCHES.map((b) => <option key={b}>{b}</option>)}</select></div>
          {f.kind === 'opportunity' && <div><label className="label" htmlFor="b-min">Only students who fit at least</label>
            <select id="b-min" className="input" value={f.min_score} onChange={(e) => set('min_score', Number(e.target.value))}><option value={0.6}>0.60 (strong fit)</option><option value={0.4}>0.40 (good fit)</option><option value={0.2}>0.20 (any real fit)</option></select></div>}
          <div><label className="label" htmlFor="b-limit">At most</label>
            <input id="b-limit" type="number" min={1} max={1000} className="input" value={f.limit} onChange={(e) => set('limit', Number(e.target.value))} /></div>
          <div className="sm:col-span-2"><button type="button" className="btn" disabled={plan.isPending || (f.kind === 'opportunity' && !f.opp_id)} onClick={() => { setSent(null); plan.mutate() }}><Megaphone className="h-4 w-4" aria-hidden />See who it reaches</button></div>
        </div>
      </Section>

      {p && !sent && (
        <Section title="Who it reaches">
          <div className="card space-y-3 p-5 text-sm">
            {!p.live && <Banner tone="sky" lead="Dry run.">WhatsApp is not connected yet, so messages are recorded in Settings, Sent messages, not delivered.</Banner>}
            {p.stand_ins !== null && <Banner tone="amber" lead="Test mode.">{p.stand_ins} of these {p.stand_ins === 1 ? 'has' : 'have'} a stand-in and would get a real message. The others are dry runs.</Banner>}
            <div className="flex flex-wrap gap-2"><Badge tone="pass">{p.reachable} will get it</Badge><Badge tone="neutral">{p.not_agreed} have not agreed to WhatsApp</Badge>{p.no_phone > 0 && <Badge tone="amber">{p.no_phone} have no usable number</Badge>}</div>
            {p.preview && <blockquote className="rounded-lg border border-line bg-bg px-3 py-2">{p.preview}</blockquote>}
            {p.not_agreed > 0 && <p className="text-xs text-ink-faint">WhatsApp only allows messages to people who agreed. Record a student's answer on their Resume tab, or they can turn it on in their profile.</p>}
            <button type="button" className="btn btn-primary" disabled={!p.reachable || send.isPending} onClick={go}><Send className="h-4 w-4" aria-hidden />Send to {p.reachable}</button>
          </div>
        </Section>)}
      {sent && <Section title="Sent"><Banner tone="pass" lead={`${sent.queued} message${sent.queued === 1 ? '' : 's'} ${sent.live ? 'on the way' : 'recorded (dry run)'}.`}>See each one in <Link to={`/ngo/settings?tab=sent&batch=${sent.batch_id}`} className="underline">Settings, Sent messages</Link>.</Banner></Section>}
    </div>
  )
}
