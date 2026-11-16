import { useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Briefcase, Eye, EyeOff, Gauge, Hourglass, MessageSquare, ScrollText, Settings as SettingsIcon, ShieldCheck, Users } from 'lucide-react'
import { Shell, type NavItem } from '../../components/Shell'
import { AccountBox } from '../../components/AccountBox'
import { RequireRole, useAuth } from '../../lib/auth'
import { AppContext } from '../../lib/app-context'
import { get } from '../../lib/api'
import type { Dashboard as D } from '../../lib/types'
import Students from './Students'
import StudentPage from './StudentPage'
import Resumes from './Resumes'
import Opportunities from './Opportunities'
import OpportunityDetail from './OpportunityDetail'
import ListingEditor from './ListingEditor'
import Messages from './Messages'
import Dashboard from './Dashboard'
import Applications from './Applications'
import ApplicationReview from './ApplicationReview'
import Settings from './Settings'
import Notifications from '../Notifications'
import Help from '../Help'
import NotFound from '../NotFound'
import AdminUsers from './AdminUsers'
import Audit from './Audit'

/**
 * The NGO area. Staff do the case work (students, matches, applications, interviews, messages). The admin is the gate:
 * they approve listings, post them, share students with employers, send bulk WhatsApp and look after accounts and settings.
 */
export default function NgoApp() {
  const { user } = useAuth()
  const admin = user?.role === 'ngo_admin'
  const [studentId, setStudentId] = useState('S001')
  const [showNames, setShowNames] = useState(false)
  const unread = useQuery({ queryKey: ['unread'], queryFn: () => get<{ unread: number }>('/api/threads/unread'), refetchInterval: 5000 })
  const dash = useQuery({ queryKey: ['dashboard'], queryFn: () => get<D>('/api/dashboard'), refetchInterval: 30000 })
  const c = dash.data?.counts

  const nav: NavItem[] = [
    { to: '/ngo', label: 'Home', icon: Gauge, end: true, group: 'Work' },
    { to: '/ngo/students', label: 'Students', icon: Users, group: 'Work' },
    { to: '/ngo/opportunities', label: 'Opportunities', icon: Briefcase, badge: admin ? c?.pending_reviews || undefined : undefined, group: 'Work' },
    { to: '/ngo/applications', label: 'Applications', icon: Hourglass, badge: c?.interests_waiting || undefined, group: 'Work' },
    { to: '/ngo/messages', label: 'Messages', icon: MessageSquare, badge: ((unread.data?.unread ?? 0) + (admin ? c?.new_leads ?? 0 : 0)) || undefined, group: 'Work' },
    ...(admin ? [
      { to: '/ngo/settings', label: 'Settings', icon: SettingsIcon, group: 'Admin' },
      { to: '/ngo/admin/users', label: 'Accounts', icon: ShieldCheck, group: 'Admin' },
      { to: '/ngo/admin/audit', label: 'Audit log', icon: ScrollText, group: 'Admin' },
    ] : []),
  ]
  const footer = (
    <>
      <label className="flex cursor-pointer items-center gap-2 text-sm text-pine-ink">
        <input type="checkbox" checked={showNames} onChange={(e) => setShowNames(e.target.checked)} />
        Show names
      </label>
      <p className="flex items-start gap-1.5 text-xs text-pine-soft">
        {showNames ? <Eye className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden /> : <EyeOff className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />}
        {showNames ? 'Names are showing. Turn this off before you share your screen.' : 'Names are hidden, so this screen is safe to project.'}
      </p>
      <AccountBox />
    </>
  )

  return (
    <AppContext.Provider value={{ studentId, setStudentId, showNames, setShowNames }}>
      <Routes>
        <Route element={<Shell area={admin ? 'NGO admin' : 'NGO staff'} base="/ngo" nav={nav} footer={footer} />}>
          <Route index element={<Dashboard />} />
          <Route path="students" element={<Students />} />
          <Route path="students/resumes" element={<Resumes />} />
          <Route path="students/:sid" element={<StudentPage />} />
          <Route path="opportunities" element={<Opportunities />} />
          <Route path="opportunities/new" element={<RequireRole roles={['ngo_admin']}><ListingEditor /></RequireRole>} />
          <Route path="opportunities/:oid" element={<OpportunityDetail />} />
          <Route path="opportunities/:oid/edit" element={<RequireRole roles={['ngo_admin']}><ListingEditor /></RequireRole>} />
          <Route path="applications" element={<Applications />} />
          <Route path="applications/:id/review" element={<ApplicationReview />} />
          <Route path="messages" element={<Messages />} />
          <Route path="settings" element={<RequireRole roles={['ngo_admin']}><Settings /></RequireRole>} />
          <Route path="admin/users" element={<RequireRole roles={['ngo_admin']}><AdminUsers /></RequireRole>} />
          <Route path="admin/audit" element={<RequireRole roles={['ngo_admin']}><Audit /></RequireRole>} />
          <Route path="notifications" element={<Notifications />} />
          <Route path="help" element={<Help area="ngo" />} />
          {/* old addresses, kept so bookmarks and older notifications still land somewhere sensible */}
          <Route path="match" element={<Navigate to={`/ngo/students/${studentId}`} replace />} />
          <Route path="new-student" element={<Navigate to="/ngo/students/resumes" replace />} />
          <Route path="reviews" element={<Navigate to="/ngo/opportunities?tab=review" replace />} />
          <Route path="decisions" element={<Navigate to={admin ? '/ngo/settings?tab=scoring' : '/ngo'} replace />} />
          <Route path="*" element={<NotFound home="/ngo" label="Back to the dashboard" />} />
        </Route>
      </Routes>
    </AppContext.Provider>
  )
}
