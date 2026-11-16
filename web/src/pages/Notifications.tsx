import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, CheckCheck } from 'lucide-react'
import { get, post } from '../lib/api'
import { cn } from '../lib/utils'
import type { Notification } from '../lib/types'
import { Empty, ErrorState, PageHeader } from '../components/ui'
import { CardsSkeleton } from '../components/Skeleton'

function ago(ts: string): string {
  const mins = Math.max(0, Math.round((Date.now() - new Date(ts).getTime()) / 60000))
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const h = Math.round(mins / 60)
  if (h < 24) return `${h} hour${h === 1 ? '' : 's'} ago`
  const d = Math.round(h / 24)
  return `${d} day${d === 1 ? '' : 's'} ago`
}

export default function Notifications() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['notifications'], queryFn: () => get<{ unread: number; items: Notification[] }>('/api/notifications'), refetchInterval: 15000 })
  const refresh = () => qc.invalidateQueries({ queryKey: ['notifications'] })
  const readAll = useMutation({ mutationFn: () => post('/api/notifications/read-all', {}), onSuccess: refresh })
  const readOne = useMutation({ mutationFn: (id: number) => post(`/api/notifications/${id}/read`, {}), onSuccess: refresh })
  const open = (n: Notification) => { if (!n.read_at) readOne.mutate(n.id); if (n.link) nav(n.link) }

  return (
    <>
      <PageHeader title="Notifications" sub="What changed since you last looked. Open one to go straight to it."
        actions={q.data && q.data.unread > 0 ? <button type="button" className="btn" onClick={() => readAll.mutate()}><CheckCheck className="h-4 w-4" aria-hidden />Mark all as read</button> : undefined} />
      <div className="max-w-3xl px-4 py-6 sm:px-8">
        {q.isLoading && <CardsSkeleton n={4} />}
        {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
        {q.data?.items.length === 0 && <Empty icon={Bell} title="Nothing new">When something changes, it shows up here.</Empty>}
        <ul className="space-y-2">
          {q.data?.items.map((n) => (
            <li key={n.id}>
              <button type="button" onClick={() => open(n)}
                className={cn('card flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-[#f6f0e3]', !n.read_at && 'border-accent/40')}>
                <span className={cn('mt-1.5 h-2 w-2 shrink-0 rounded-full', n.read_at ? 'bg-transparent' : 'bg-maple')} aria-label={n.read_at ? undefined : 'Unread'} />
                <span className="flex-1"><span className={cn('block text-sm', !n.read_at && 'font-medium')}>{n.text}</span><span className="text-xs text-ink-faint">{ago(n.created_at)}</span></span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </>
  )
}
