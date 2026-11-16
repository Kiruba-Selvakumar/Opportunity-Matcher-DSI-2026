import { Badge, type Tone } from '../../components/ui'
import type { ListingStatus } from '../../lib/types'

const T: Record<ListingStatus, [string, Tone]> = {
  draft: ['Draft', 'neutral'], pending: ['Waiting for review', 'amber'], active: ['Live', 'pass'], rejected: ['Not approved', 'fail'], closed: ['Closed', 'neutral'],
}

export function ListingStatusBadge({ status }: { status: ListingStatus }) {
  const [label, tone] = T[status]
  return <Badge tone={tone}>{label}</Badge>
}

export const APPLICANT_LABEL: Record<string, [string, Tone]> = {
  shared: ['New', 'sky'], shortlisted: ['Shortlisted', 'accent'], interview: ['Interview', 'accent'],
  offered: ['Offered', 'pass'], hired: ['Hired', 'pass'], not_a_fit: ['Not a fit', 'neutral'],
}
