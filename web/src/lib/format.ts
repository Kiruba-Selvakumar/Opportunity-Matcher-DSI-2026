export function payText(min: number | null, max: number | null): string | null {
  if (min == null || max == null) return null
  return `${(((min + max) / 2) / 100000).toFixed(1)} LPA`
}

export function rupees(n: number): string {
  return `Rs ${n.toLocaleString('en-IN')}`
}

export function whereText(city: string, mode: string): string {
  return mode === 'remote' || city === 'Remote' ? 'Remote' : `${city} (${mode})`
}

/** Where a listing is, said from the student's side: do they have to move? */
export function whereForYou(city: string, mode: string, town: string): string {
  if (mode === 'remote' || city === 'Remote') return 'Remote, no need to move'
  if (city === town) return `In ${town}, no need to move`
  return `You would move to ${city}`
}

export const TYPE_WORD: Record<string, string> = { job: 'Job', training: 'Training', mentor: 'Mentor' }

/** "20 Oct 2026" from 2026-10-20. */
export function dateWords(iso: string): string {
  return new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

/** Whole days from today until a YYYY-MM-DD date (0 = today, negative = passed). */
export function daysLeft(iso: string): number {
  const today = new Date(); today.setHours(0, 0, 0, 0)
  return Math.round((new Date(`${iso.slice(0, 10)}T00:00:00`).getTime() - today.getTime()) / 86_400_000)
}
