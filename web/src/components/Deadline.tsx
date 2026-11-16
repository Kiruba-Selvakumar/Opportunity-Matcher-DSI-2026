import { CalendarClock } from 'lucide-react'
import { dateWords, daysLeft } from '../lib/format'
import { Badge } from './ui'

/** "Apply by 20 Oct 2026", amber when a week or less is left, and "Closed" once it has passed. */
export function ApplyBy({ date }: { date?: string | null }) {
  if (!date) return null
  const left = daysLeft(date)
  if (left < 0) return <Badge tone="neutral"><CalendarClock className="h-3 w-3" aria-hidden />Closed {dateWords(date)}</Badge>
  const soon = left <= 7
  return (
    <Badge tone={soon ? 'amber' : 'neutral'}>
      <CalendarClock className="h-3 w-3" aria-hidden />Apply by {dateWords(date)}{soon ? ` (${left === 0 ? 'today' : `${left} day${left === 1 ? '' : 's'} left`})` : ''}
    </Badge>
  )
}
