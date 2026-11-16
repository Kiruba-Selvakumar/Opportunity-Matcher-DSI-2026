import { Route, Routes } from 'react-router-dom'
import { Briefcase, MessageSquare } from 'lucide-react'
import { Shell, type NavItem } from '../../components/Shell'
import { AccountBox } from '../../components/AccountBox'
import Notifications from '../Notifications'
import Help from '../Help'
import NotFound from '../NotFound'
import Listings from './Listings'
import Listing from './Listing'
import ListingFormPage from './ListingFormPage'
import Messages from './Messages'

const NAV: NavItem[] = [
  { to: '/employer', label: 'My listings', icon: Briefcase, end: true },
  { to: '/employer/messages', label: 'Messages', icon: MessageSquare },
]

export default function EmployerApp() {
  return (
    <Routes>
      <Route element={<Shell area="Employer" base="/employer" nav={NAV} footer={<AccountBox />} />}>
        <Route index element={<Listings />} />
        <Route path="new" element={<ListingFormPage />} />
        <Route path="messages" element={<Messages />} />
        <Route path="notifications" element={<Notifications />} />
        <Route path="help" element={<Help area="employer" />} />
        <Route path=":oid" element={<Listing />} />
        <Route path=":oid/edit" element={<ListingFormPage />} />
        <Route path="*" element={<NotFound home="/employer" label="Back to my listings" />} />
      </Route>
    </Routes>
  )
}
