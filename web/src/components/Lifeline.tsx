import { cn } from '../lib/utils'

/** The five stages an application moves through, in order. */
export const STAGES = ['Application', 'NGO review', 'With employer', 'Interview', 'Decision'] as const

const AT: Record<string, number> = { interested: 0, shared: 2, shortlisted: 2, interview: 3, offered: 4, hired: 4 }

export interface LifelineState { at: number; label: string; tone: 'accent' | 'pass' | 'fail' | 'muted' }

/** Where an application stands on the lifeline. Ended applications stop at the stage they reached. */
export function lifelineState(status: string, reviewing = false, stoppedAt?: string | null): LifelineState {
  if (status === 'interested') return reviewing ? { at: 1, label: STAGES[1], tone: 'accent' } : { at: 0, label: STAGES[0], tone: 'accent' }
  if (status === 'offered') return { at: 4, label: 'Offer', tone: 'pass' }
  if (status === 'hired') return { at: 4, label: 'Hired', tone: 'pass' }
  if (status === 'declined') return { at: 1, label: 'Not shared', tone: 'fail' }
  if (status === 'not_a_fit') return { at: 4, label: 'Not selected', tone: 'fail' }
  if (status === 'withdrawn') return { at: AT[stoppedAt ?? 'interested'] ?? 0, label: 'Withdrawn', tone: 'muted' }
  return { at: AT[status] ?? 0, label: STAGES[AT[status] ?? 0], tone: 'accent' }
}

const DOT = { accent: 'border-accent bg-accent', pass: 'border-pass bg-pass', fail: 'border-fail bg-fail', muted: 'border-ink-faint bg-ink-faint' }
const TEXT = { accent: 'text-accent', pass: 'text-pass', fail: 'text-fail', muted: 'text-ink-soft' }

/**
 * One line with a dot per stage, like a parcel tracker. Stages already passed are filled, the current one is marked and
 * named in colour, and later ones are hollow. On a phone only the current stage keeps its label under the dot.
 */
export function Lifeline({ status, reviewing, stoppedAt }: { status: string; reviewing?: boolean; stoppedAt?: string | null }) {
  const s = lifelineState(status, reviewing, stoppedAt)
  const ended = s.tone === 'fail' || s.tone === 'muted'
  const last = STAGES.length - 1
  return (
    <div className="px-1.5 pb-7 pt-2">
      <ol className="relative flex justify-between" aria-label="Where this application is">
        <span className="absolute left-0 right-0 top-[5px] h-0.5 bg-line" aria-hidden />
        <span className={cn('absolute left-0 top-[5px] h-0.5', ended ? 'bg-ink-faint' : 'bg-accent')} style={{ width: `${(s.at / last) * 100}%` }} aria-hidden />
        {STAGES.map((name, i) => {
          const current = i === s.at
          const done = i < s.at
          const label = current ? s.label : name
          return (
            <li key={name} className="relative flex w-0 flex-col items-center" aria-current={current ? 'step' : undefined}>
              <span className={cn('relative z-10 h-3 w-3 shrink-0 rounded-full border-2',
                current ? DOT[s.tone] : done ? (ended ? 'border-ink-faint bg-ink-faint' : 'border-accent bg-accent') : 'border-line-strong bg-surface')} aria-hidden />
              <span aria-hidden className={cn('absolute top-5 whitespace-nowrap text-xs sm:text-sm',
                i === 0 ? 'left-[-6px]' : i === last ? 'right-[-6px]' : 'left-1/2 -translate-x-1/2',
                current ? cn('font-medium', TEXT[s.tone]) : 'hidden text-ink-faint sm:block')}>
                {label}
              </span>
              <span className="sr-only">{label}{current ? ' (now)' : done ? ' (done)' : ' (to come)'}</span>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
