import { useMutation, useQueryClient } from '@tanstack/react-query'
import { del, post, put } from '../../lib/api'
import { useToast } from '../../components/Toast'

/** "I'm interested" and Save, shared by My matches, Browse and the listing page so they behave the same. */
export function useListingActions() {
  const qc = useQueryClient()
  const toast = useToast()
  const refresh = () => {
    for (const k of ['browse', 'listing', 'me-student', 'my-applications', 'my-saved']) qc.invalidateQueries({ queryKey: [k] })
  }
  const interest = useMutation({
    mutationFn: ({ oppId, note }: { oppId: string; note: string }) => post('/api/me/applications', { opp_id: oppId, note }),
    onSuccess: () => { toast('Sent. The NGO will look at it next.'); refresh() },
    onError: (e) => toast((e as Error).message, 'fail'),
  })
  const save = useMutation({
    mutationFn: ({ oppId, saved }: { oppId: string; saved: boolean }) => (saved ? del(`/api/me/saved/${oppId}`) : put(`/api/me/saved/${oppId}`, {})),
    onSuccess: (_, v) => { toast(v.saved ? 'Removed from saved.' : 'Saved for later.'); refresh() },
    onError: (e) => toast((e as Error).message, 'fail'),
  })
  return { interest, save }
}

/** Statuses where the student's interest is still open, so there is nothing to ask for again. */
export const LIVE_STATUSES = ['interested', 'shared', 'shortlisted', 'interview', 'offered', 'hired']
