import { Link, useNavigate } from 'react-router-dom'
import { LogOut, UserRound } from 'lucide-react'
import { ROLE_WORD, useAuth, useDemoMode } from '../lib/auth'

/** Who is signed in, a link to the account page, and sign out. Shown at the bottom of every sidebar. */
export function AccountBox() {
  const { user, signOut } = useAuth()
  const nav = useNavigate()
  const demo = useDemoMode()
  if (!user) return null
  return (
    <div>
      <div className="flex items-center gap-2 rounded-md bg-pine-700 px-3 py-2">
        <UserRound className="h-4 w-4 shrink-0 text-pine-soft" aria-hidden />
        <div className="min-w-0">
          <div className="truncate text-sm font-medium">{user.display_name}</div>
          <div className="truncate text-xs text-pine-soft">{ROLE_WORD[user.role]}</div>
        </div>
      </div>
      {demo && <p className="mt-1.5 text-xs text-amber-line">Demo mode: no passwords</p>}
      <div className="mt-1.5 flex items-center justify-between text-xs text-pine-soft">
        <Link to="/account" className="underline-offset-2 hover:text-pine-ink hover:underline">Account</Link>
        <button type="button" onClick={async () => { await signOut(); nav('/login', { replace: true }) }}
          className="inline-flex items-center gap-1 underline-offset-2 hover:text-pine-ink hover:underline"><LogOut className="h-3 w-3" aria-hidden />Sign out</button>
      </div>
    </div>
  )
}
