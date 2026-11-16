import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, CalendarDays, CircleCheck, CircleDashed, Mail, MessageCircle, Sparkles } from 'lucide-react'
import { get, post } from '../../lib/api'
import type { IntegrationStatus, OutboxItem, ScoringInfo } from '../../lib/types'
import { Badge, Banner, ErrorState, Meter, PageHeader, Section, Spinner, Tabs } from '../../components/ui'
import { DataTable, type Column } from '../../components/DataTable'
import { useConfirm } from '../../components/Confirm'
import { useToast } from '../../components/Toast'
import Decisions from './Decisions'

/** Admin settings: connected services, what the score is made of and learns from, and every message the app sent. */
export default function Settings() {
  const [params, setParams] = useSearchParams()
  const tab = ['connections', 'scoring', 'sent'].includes(params.get('tab') ?? '') ? params.get('tab')! : 'connections'
  return (
    <>
      <PageHeader title="Settings" sub="Connect email, WhatsApp, Google Calendar and the notetaker; see how matching learns from your decisions; and check every message the app has sent. Only admins see this page." />
      <div className="space-y-4 px-4 py-6 sm:px-8">
        <Tabs value={tab} onChange={(t) => setParams({ tab: t })} tabs={[{ id: 'connections', label: 'Connections' }, { id: 'scoring', label: 'Scoring and decisions' }, { id: 'sent', label: 'Sent messages' }]} />
        {tab === 'connections' && <Connections />}
        {tab === 'scoring' && <Scoring />}
        {tab === 'sent' && <Sent batch={params.get('batch')} />}
      </div>
    </>
  )
}

function Live({ on, yes = 'Live', no = 'Not set up: dry run' }: { on: boolean; yes?: string; no?: string }) {
  return on ? <Badge tone="pass"><CircleCheck className="h-3 w-3" aria-hidden />{yes}</Badge> : <Badge tone="neutral"><CircleDashed className="h-3 w-3" aria-hidden />{no}</Badge>
}

function Card({ icon: Icon, title, status, children }: { icon: typeof Mail; title: string; status: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="card space-y-2 p-5 text-sm" aria-label={title}>
      <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="flex items-center gap-2 text-base text-ink"><Icon className="h-4 w-4 text-ink-soft" aria-hidden />{title}</h3>{status}</div>
      {children}
    </section>
  )
}

const Code = ({ children }: { children: React.ReactNode }) => <code className="rounded bg-sunk px-1.5 py-0.5 font-mono text-xs">{children}</code>

function Connections() {
  const [params] = useSearchParams()
  const qc = useQueryClient()
  const toast = useToast()
  const confirm = useConfirm()
  const q = useQuery({ queryKey: ['integrations'], queryFn: () => get<IntegrationStatus>('/api/integrations') })
  const off = useMutation({ mutationFn: () => post('/api/integrations/google/disconnect', {}), onSuccess: () => { toast('Google disconnected.'); qc.invalidateQueries({ queryKey: ['integrations'] }) } })
  if (q.isLoading) return <Spinner />
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const s = q.data!
  const hook = (path: string) => `${s.app_url}${path}`
  return (
    <div className="space-y-4">
      {params.get('google') === 'connected' && <Banner tone="pass" lead="Google Calendar is connected.">Interviews now get a Meet link and Google sends the invites{params.get('account') ? ` from ${params.get('account')}` : ''}.</Banner>}
      {params.get('google_error') && <Banner tone="fail" lead="Google was not connected.">{params.get('google_error')}</Banner>}
      <p className="max-w-[80ch] text-sm text-ink-soft">Each service is set in the server's <Code>.env</Code> file (see the README). Until one is set, the app still works: messages are recorded as dry runs under Sent messages, and interviews get a calendar file by email.</p>
      {s.test_mode.active && <Banner tone="amber" lead="Test mode.">Real messages go only to the people in <Code>STANDIN_WHATSAPP</Code> and <Code>STANDIN_EMAIL</Code>. Anyone else gets a dry run. Delete both settings to go live.</Banner>}
      <div className="grid gap-4 xl:grid-cols-2">
        <Card icon={Mail} title="Email" status={<Live on={s.email.live} />}>
          <p className="text-ink-soft">Tells employers when a listing is approved or rejected and when a candidate is shared, and sends interview invites. {s.email.from && <>Sends from <Code>{s.email.from}</Code>.</>}</p>
          {!s.email.live && <p className="text-ink-soft">Set <Code>SMTP_HOST</Code>, <Code>SMTP_USER</Code>, <Code>SMTP_PASSWORD</Code> and <Code>SMTP_FROM</Code>. A Gmail app password works.</p>}
          <p className="text-xs text-ink-faint">Employers' emails are on their accounts (Accounts page). Each person can also set their own on the Account page.</p>
        </Card>
        <Card icon={MessageCircle} title="WhatsApp (Meta Cloud API)" status={<Live on={s.whatsapp.live} />}>
          <p className="text-ink-soft">Bulk messages to students who agreed, interview reminders, and messages from employers (they show up under Messages).</p>
          {s.whatsapp.only_to > 0 && <Banner tone="amber" lead="Test mode.">Real messages go only to the {s.whatsapp.only_to} number{s.whatsapp.only_to === 1 ? '' : 's'} in <Code>WHATSAPP_ONLY_TO</Code>. Everyone else gets a dry run.</Banner>}
          <p>Webhook for Meta: <Code>{hook('/api/whatsapp/webhook')}</Code> {s.whatsapp.webhook_ready ? <Badge tone="pass">ready</Badge> : <Badge tone="amber">set WHATSAPP_VERIFY_TOKEN and WHATSAPP_APP_SECRET</Badge>}</p>
          <p className="text-ink-soft">Approved templates it uses: {Object.entries(s.whatsapp.templates).map(([k, v]) => <Code key={k}>{v}</Code>).reduce((a, b) => <>{a} {b}</>)}</p>
        </Card>
        <Card icon={CalendarDays} title="Google Calendar and Meet" status={<Live on={s.google.connected} yes={`Connected${s.google.account ? `: ${s.google.account}` : ''}`} no={s.google.configured ? 'Not connected' : 'Not set up'} />}>
          <p className="text-ink-soft">Every interview goes on the NGO calendar with a Meet link, and Google sends the invites. Guests cannot see each other, so an employer never sees a student's email.</p>
          {!s.google.configured && <p className="text-ink-soft">Set <Code>GOOGLE_CLIENT_ID</Code> and <Code>GOOGLE_CLIENT_SECRET</Code> (a Google Cloud OAuth client with the Calendar API on), then come back here to connect.</p>}
          {s.google.configured && !s.google.connected && <a href="/api/integrations/google/start" className="btn btn-primary">Connect a Google account</a>}
          {s.google.connected && <div className="flex flex-wrap items-center gap-2"><span className="text-xs text-ink-faint">Connected by {s.google.connected_by} on {s.google.connected_at?.slice(0, 10)}.</span>
            <button type="button" className="btn btn-quiet" onClick={async () => { if (await confirm({ title: 'Disconnect Google?', body: 'New interviews will get a calendar file by email instead of a Meet link.', confirmLabel: 'Disconnect', danger: true })) off.mutate() }}>Disconnect</button></div>}
        </Card>
        <Card icon={Bot} title="Fireflies notetaker" status={<Live on={s.fireflies.live} />}>
          <p className="text-ink-soft">When an interview asks for notes, {s.fireflies.bot_email ? <Code>{s.fireflies.bot_email}</Code> : 'the Fireflies bot'} is invited. It joins and records even if nobody from the NGO can, and the summary and action points come back to the interview.</p>
          <p>Webhook for Fireflies: <Code>{hook('/api/fireflies/webhook')}</Code> {s.fireflies.webhook_ready ? <Badge tone="pass">ready</Badge> : <Badge tone="amber">set FIREFLIES_WEBHOOK_SECRET</Badge>}</p>
          {!s.fireflies.live && <p className="text-ink-soft">Set <Code>FIREFLIES_API_KEY</Code>. Without it, paste the Meet transcript into the interview and the action points are pulled out for you.</p>}
        </Card>
      </div>
    </div>
  )
}

function Scoring() {
  const q = useQuery({ queryKey: ['scoring'], queryFn: () => get<ScoringInfo>('/api/scoring') })
  if (q.isLoading) return <Spinner />
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const s = q.data!
  const ml = s.ml
  return (
    <div className="space-y-2">
      <Section title="Learning from outcomes">
        <div className="card max-w-3xl space-y-3 p-5 text-sm">
          <div className="flex flex-wrap items-center gap-2"><Sparkles className="h-4 w-4 text-ink-soft" aria-hidden /><strong className="font-medium">{ml.trained ? 'Learning' : 'Waiting for enough outcomes'}</strong>
            <Badge tone="neutral">{ml.labels} outcomes: {ml.yes} yes, {ml.no} no</Badge>{ml.trained && ml.weight != null && <Badge tone="sky">at {Math.round(ml.weight * 100)}% strength</Badge>}</div>
          <p className="text-ink-soft">Each staff accept or reject, and what employers do with a shared student (shortlist, interview, offer, hire, or not a fit), teaches the score which kinds of match work. It is a small nudge of at most ±{ml.max_nudge}, shown on every match under "How this score was made".</p>
          {!ml.trained && <><div className="w-64"><Meter value={Math.min(1, ml.labels / ml.needed)} label="Outcomes collected" /></div>
            <p className="text-xs text-ink-faint">It starts at {ml.needed} outcomes with at least {ml.needed_each} yes and {ml.needed_each} no.</p></>}
          {ml.learned && <><h3 className="text-ink-soft">What it has learned so far</h3><ul className="space-y-0.5">{ml.learned.map((l) => <li key={l.what}><Badge tone={l.effect === 'helps' ? 'pass' : 'amber'}>{l.effect}</Badge> {l.what} <span className="text-xs text-ink-faint">({l.strength})</span></li>)}</ul></>}
        </div>
      </Section>
      <Section title="Also in the score">
        <ul className="card max-w-3xl space-y-1.5 p-5 text-sm text-ink-soft">
          <li><strong className="font-medium text-ink">Easy to close the gap</strong> (up to +{s.caps.upskill}): a job whose missing skills the student nearly has (MySQL for SQL) or that an open training teaches is preferred over one with the same fit and a harder gap.</li>
          <li><strong className="font-medium text-ink">Rank among students</strong> (up to ±{s.caps.standing}, once {s.caps.standing_min_field} or more students fit): a student is steered a little toward jobs where they stand out among everyone the job fits.</li>
        </ul>
      </Section>
      <Section title="Decisions staff have saved"><Decisions embedded /></Section>
    </div>
  )
}

const STATUS_TONE = { queued: 'sky', sent: 'pass', delivered: 'pass', read: 'pass', failed: 'fail', dry_run: 'neutral' } as const

function Sent({ batch }: { batch: string | null }) {
  const [channel, setChannel] = useState('all')
  const q = useQuery({ queryKey: ['outbox', channel, batch], queryFn: () => get<OutboxItem[]>(`/api/outbox?limit=500${channel === 'all' ? '' : `&channel=${channel}`}${batch ? `&batch=${batch}` : ''}`), refetchInterval: 10000 })
  const cols: Column<OutboxItem>[] = [
    { key: 'at', header: 'When', sort: (m) => m.created_at, csv: (m) => m.created_at, className: 'whitespace-nowrap text-ink-soft', render: (m) => m.created_at.replace('T', ' ').slice(0, 16) },
    { key: 'channel', header: 'How', sort: (m) => m.channel, csv: (m) => m.channel, render: (m) => <Badge tone={m.channel === 'email' ? 'navy' : 'plum'}>{m.channel === 'email' ? 'Email' : 'WhatsApp'}</Badge> },
    { key: 'to', header: 'To', sort: (m) => m.recipient, csv: (m) => m.recipient, render: (m) => <><div className="font-mono text-xs">{m.address}</div><div className="text-xs text-ink-faint">{m.recipient}</div></> },
    { key: 'what', header: 'What', csv: (m) => m.subject ?? m.body, className: 'max-w-[48ch]', render: (m) => <><div className="font-medium">{m.subject ?? m.kind.replace('_', ' ')}</div><div className="line-clamp-2 text-xs text-ink-soft">{m.body}</div></> },
    { key: 'status', header: 'Status', sort: (m) => m.status, csv: (m) => m.status, render: (m) => <><Badge tone={STATUS_TONE[m.status]}>{m.status === 'dry_run' ? 'dry run' : m.status}</Badge>{m.error && <div className="mt-1 max-w-[24ch] text-xs text-fail">{m.error}</div>}</> },
  ]
  return (
    <div className="space-y-3">
      <Tabs value={channel} onChange={setChannel} tabs={[{ id: 'all', label: 'All' }, { id: 'email', label: 'Email' }, { id: 'whatsapp', label: 'WhatsApp' }]} />
      {batch && <p className="text-sm text-ink-soft">Showing one bulk send. <a href="/ngo/settings?tab=sent" className="underline">Show everything</a>.</p>}
      {q.isLoading && <Spinner />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data && <DataTable columns={cols} rows={q.data} rowKey={(m) => m.id} csvName="sent-messages" initialSort={{ key: 'at', dir: 'desc' }} />}
      <p className="text-xs text-ink-faint">Student phone numbers and emails are shown masked. "Dry run" means the service is not connected, so the message was recorded but not sent.</p>
    </div>
  )
}
