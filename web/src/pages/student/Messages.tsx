import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { get } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import type { StudentListing, StudentSelf } from '../../lib/types'
import { Chat } from '../../components/Chat'
import { PageHeader } from '../../components/ui'

export default function Messages() {
  const { user } = useAuth()
  const me = useQuery({ queryKey: ['me-student'], queryFn: () => get<StudentSelf>('/api/me/student') })
  const about = useSearchParams()[0].get('about') ?? ''
  const options = (me.data?.matches ?? []).map((m) => ({ id: m.opp_id, label: m.title }))
  // Opened from a listing page: offer that listing too, even if it is not one of the top matches
  const asked = useQuery({ queryKey: ['listing', about], queryFn: () => get<StudentListing>(`/api/me/browse/${about}`),
    enabled: !!about && !!me.data && !options.some((o) => o.id === about), retry: false })
  if (asked.data) options.push({ id: asked.data.opp_id, label: asked.data.title })
  const ready = !about || options.some((o) => o.id === about) || asked.isError
  return (
    <>
      <PageHeader title="Messages" sub="Ask your placement officer anything about your matches, or tell them if something about you has changed." />
      <div className="max-w-3xl px-8 py-6">{user?.student_id && ready && <Chat threadType="student" threadId={user.student_id} role="student" aboutOptions={options} initialAbout={options.some((o) => o.id === about) ? about : ''} />}</div>
    </>
  )
}
