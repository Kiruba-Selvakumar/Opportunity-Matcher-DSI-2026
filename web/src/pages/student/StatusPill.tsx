import { Badge, type Tone } from '../../components/ui'

export const STATUS: Record<string, [string, Tone]> = {
  interested: ['Interested', 'sky'], shared: ['Shared with employer', 'accent'], shortlisted: ['Shortlisted', 'accent'],
  interview: ['Interview', 'accent'], offered: ['Offer', 'pass'], hired: ['Hired', 'pass'],
  declined: ['Not shared', 'neutral'], not_a_fit: ['Not a fit', 'neutral'], withdrawn: ['Withdrawn', 'neutral'],
}

export function StatusPill({ status }: { status: string }) {
  const [label, tone] = STATUS[status] ?? [status, 'neutral' as const]
  return <Badge tone={tone}>{label}</Badge>
}
