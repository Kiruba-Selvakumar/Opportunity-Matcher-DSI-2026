import { Navigate, Route, Routes } from 'react-router-dom'
import { HOME, RequireRole, useAuth } from './lib/auth'
import { Spinner } from './components/ui'
import Login from './pages/Login'
import Account from './pages/Account'
import NgoApp from './pages/ngo/NgoApp'
import StudentApp from './pages/student/StudentApp'
import EmployerApp from './pages/employer/EmployerApp'

function Home() {
  const { user, loading } = useAuth()
  if (loading) return <div className="p-8"><Spinner /></div>
  return <Navigate to={user ? (user.must_change_password ? '/account' : HOME[user.role]) : '/login'} replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/account" element={<Account />} />
      <Route path="/ngo/*" element={<RequireRole roles={['ngo_admin', 'ngo_staff']}><NgoApp /></RequireRole>} />
      <Route path="/student/*" element={<RequireRole roles={['student']}><StudentApp /></RequireRole>} />
      <Route path="/employer/*" element={<RequireRole roles={['employer']}><EmployerApp /></RequireRole>} />
      <Route path="*" element={<Home />} />
    </Routes>
  )
}
