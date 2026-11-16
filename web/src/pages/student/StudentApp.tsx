import { Route, Routes } from 'react-router-dom'
import { ClipboardList, MessageSquare, Search, Target, UserRound } from 'lucide-react'
import { Shell, type NavItem } from '../../components/Shell'
import { AccountBox } from '../../components/AccountBox'
import Notifications from '../Notifications'
import Help from '../Help'
import NotFound from '../NotFound'
import Matches from './Matches'
import Applications from './Applications'
import Browse from './Browse'
import ListingDetail from './ListingDetail'
import Profile from './Profile'
import Messages from './Messages'

const NAV: NavItem[] = [
  { to: '/student', label: 'My matches', icon: Target, end: true },
  { to: '/student/browse', label: 'Browse', icon: Search },
  { to: '/student/applications', label: 'Applications', icon: ClipboardList },
  { to: '/student/profile', label: 'Profile', icon: UserRound },
  { to: '/student/messages', label: 'Messages', icon: MessageSquare },
]

export default function StudentApp() {
  return (
    <Routes>
      <Route element={<Shell area="Student" base="/student" nav={NAV} footer={<AccountBox />} />}>
        <Route index element={<Matches />} />
        <Route path="browse" element={<Browse />} />
        <Route path="browse/:oppId" element={<ListingDetail />} />
        <Route path="applications" element={<Applications />} />
        <Route path="profile" element={<Profile />} />
        <Route path="messages" element={<Messages />} />
        <Route path="notifications" element={<Notifications />} />
        <Route path="help" element={<Help area="student" />} />
        <Route path="*" element={<NotFound home="/student" label="Back to my matches" />} />
      </Route>
    </Routes>
  )
}
