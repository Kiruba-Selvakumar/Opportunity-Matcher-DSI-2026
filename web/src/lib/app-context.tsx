import { createContext, useContext } from 'react'

export interface AppCtx {
  studentId: string
  setStudentId: (id: string) => void
  showNames: boolean
  setShowNames: (v: boolean) => void
}

export const AppContext = createContext<AppCtx | null>(null)

export function useApp(): AppCtx {
  const c = useContext(AppContext)
  if (!c) throw new Error('useApp must be used inside AppContext')
  return c
}
