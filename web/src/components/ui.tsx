import { useState, type ReactNode } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { AlertTriangle, ChevronRight, Info, Loader2, OctagonAlert, type LucideIcon } from 'lucide-react'
import { cn } from '../lib/utils'
import { errorTitle, ApiError } from '../lib/api'
import { AnimatedBackground } from './motion/animated-background'

export function PageHeader({ title, sub, actions }: { title: string; sub: string; actions?: ReactNode }) {
  return (
    <header className="sky border-b border-line px-8 pb-6 pt-8">
      <div className="flex items-end justify-between gap-6">
        <div>
          <h1>{title}</h1>
          <p className="mt-2 max-w-[95ch] text-base text-ink-soft">{sub}</p>
        </div>
        {actions}
      </div>
    </header>
  )
}

export function Section({ title, right, children, className }: { title: string; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cn('border-t border-line py-6 first:border-t-0', className)}>
      <div className="mb-4 flex items-center justify-between gap-4">
        <h2>{title}</h2>
        {right}
      </div>
      {children}
    </section>
  )
}

export type Tone = 'neutral' | 'pass' | 'fail' | 'amber' | 'navy' | 'accent' | 'sky' | 'plum' | 'pear' | 'maple'
const TONES: Record<Tone, string> = {
  neutral: 'bg-sunk text-ink-soft border-line',
  pass: 'bg-pass-soft text-pass border-pass-line',
  fail: 'bg-fail-soft text-fail border-fail-line',
  amber: 'bg-amber-soft text-amber border-amber-line',
  navy: 'bg-navy text-surface border-navy',
  accent: 'bg-accent-soft text-accent border-accent/30',
  sky: 'bg-sky-soft text-sky border-sky-line',
  plum: 'bg-plum-soft text-plum border-plum-line',
  pear: 'bg-pear-soft text-pear border-pear-line',
  maple: 'bg-maple-soft text-[#a1291d] border-maple-line',
}

export function Badge({ tone = 'neutral', children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium', TONES[tone], className)}>
      {children}
    </span>
  )
}

export function Banner({ tone = 'amber', lead, children, icon: Icon = AlertTriangle }: { tone?: 'amber' | 'fail' | 'sky' | 'pass'; lead: string; children?: ReactNode; icon?: LucideIcon }) {
  return (
    <div className={cn('flex gap-3 rounded-lg border px-4 py-3 text-sm', TONES[tone])} role="status">
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <p><strong className="font-semibold">{lead}</strong> {children}</p>
    </div>
  )
}

export function Fold({ title, children, defaultOpen = false, right }: { title: string; children: ReactNode; defaultOpen?: boolean; right?: ReactNode }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="rounded-xl border border-line bg-surface">
      <button type="button" className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm font-medium" onClick={() => setOpen(!open)} aria-expanded={open}>
        <motion.span animate={{ rotate: open ? 90 : 0 }} transition={{ type: 'spring', bounce: 0.15, duration: 0.3 }}>
          <ChevronRight className="h-4 w-4 text-ink-soft" aria-hidden />
        </motion.span>
        {title}
        <span className="ml-auto">{right}</span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }} className="overflow-hidden">
            <div className="border-t border-line px-4 py-3">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export function Tabs({ tabs, value, onChange }: { tabs: { id: string; label: string }[]; value: string; onChange: (id: string) => void }) {
  return (
    <div role="tablist" className="flex gap-1 border-b border-line">
      <AnimatedBackground value={value} onValueChange={onChange} className="top-auto h-0.5 bg-maple" transition={{ type: 'spring', bounce: 0.2, duration: 0.35 }}>
        {tabs.map((t) => (
          <button key={t.id} data-id={t.id} role="tab" aria-selected={value === t.id} type="button"
            className={cn('px-3 py-2 text-sm font-medium transition-colors', value === t.id ? 'text-navy' : 'text-ink-soft hover:text-ink')}>
            {t.label}
          </button>
        ))}
      </AnimatedBackground>
    </div>
  )
}

export function KV({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-1 gap-x-8 sm:grid-cols-2 xl:grid-cols-3">
      {items.map(([k, v]) => (
        <div key={k} className="flex items-baseline justify-between gap-3 border-b border-dotted border-line-strong py-1.5 text-sm">
          <dt className="text-ink-soft">{k}</dt>
          <dd className="text-right font-medium">{v}</dd>
        </div>
      ))}
    </dl>
  )
}

export function Empty({ icon: Icon = Info, title, children }: { icon?: LucideIcon; title: string; children?: ReactNode }) {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center py-16 text-center">
      <Icon className="mb-3 h-6 w-6 text-ink-faint" aria-hidden />
      <h2>{title}</h2>
      {children && <p className="mt-1.5 text-sm text-ink-soft">{children}</p>}
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const status = error instanceof ApiError ? error.status : 0
  const msg = error instanceof Error ? error.message : 'Unknown problem'
  return (
    <div className="rounded-xl border border-fail-line bg-fail-soft p-5 text-fail" role="alert">
      <div className="flex items-center gap-2 font-semibold"><OctagonAlert className="h-4 w-4" aria-hidden />{errorTitle(status)}</div>
      <p className="mt-1 text-sm">{status === 503 ? 'Run make all first, then reload this page.' : msg}</p>
      {onRetry && <button type="button" className="btn mt-3" onClick={onRetry}>Try again</button>}
    </div>
  )
}

export function Spinner({ text = 'Loading' }: { text?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-ink-soft">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />{text}
    </span>
  )
}

export function Meter({ value, tone = 'accent', label = 'Score' }: { value: number; tone?: 'accent' | 'sky'; label?: string }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-sunk" role="meter" aria-label={label} aria-valuenow={Math.round(value * 100)} aria-valuemin={0} aria-valuemax={100}>
      <motion.div className={cn('h-full rounded-full', tone === 'accent' ? 'bg-accent' : 'bg-sky')} initial={false} animate={{ width: `${Math.min(1, Math.max(0, value)) * 100}%` }} transition={{ type: 'spring', bounce: 0, duration: 0.5 }} />
    </div>
  )
}
