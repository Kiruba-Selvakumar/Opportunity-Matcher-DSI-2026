import { useEffect, useState, type ReactNode } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Bell, CircleHelp, Menu, X, type LucideIcon } from 'lucide-react'
import { AnimatedBackground } from './motion/animated-background'
import { Mark } from './MapleMark'
import { get } from '../lib/api'
import type { Notification } from '../lib/types'

export interface NavItem { to: string; label: string; icon: LucideIcon; badge?: number; end?: boolean; group?: string }

/**
 * The pine sidebar and the page area. Each area (NGO, student, employer) passes its own menu.
 * Notifications and Help are added to every menu. Below 1024 px the sidebar becomes a slide-in menu with a top bar.
 */
export function Shell({ area, base, nav, footer }: { area: string; base: string; nav: NavItem[]; footer: ReactNode }) {
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  const notes = useQuery({ queryKey: ['notifications'], queryFn: () => get<{ unread: number; items: Notification[] }>('/api/notifications'), refetchInterval: 15000 })
  const unread = notes.data?.unread ?? 0
  const tail = nav.some((n) => n.group) ? 'You' : undefined
  const items: NavItem[] = [...nav,
    { to: `${base}/notifications`, label: 'Notifications', icon: Bell, badge: unread || undefined, group: tail },
    { to: `${base}/help`, label: 'Help', icon: CircleHelp, group: tail }]

  useEffect(() => { setOpen(false) }, [pathname])
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  const active = [...items].sort((a, b) => b.to.length - a.to.length)
    .find((n) => pathname === n.to || pathname.startsWith(n.to + '/'))?.to ?? items[0]?.to

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 flex items-center gap-3 bg-pine px-4 py-3 text-pine-ink lg:hidden">
        <button type="button" aria-label="Open the menu" aria-expanded={open} aria-controls="sidebar" onClick={() => setOpen(true)}
          className="-ml-1 rounded-md p-2 hover:bg-white/10"><Menu className="h-5 w-5" aria-hidden /></button>
        <Mark className="h-6 w-6" />
        <span className="font-serif text-lg">Opportunity Matcher</span>
        <span className="ml-auto rounded-full bg-white/10 px-2 py-0.5 text-xs uppercase tracking-[0.08em] text-pine-ink">{area}</span>
        {unread > 0 && <NavLink to={`${base}/notifications`} aria-label={`${unread} unread notifications`} className="rounded-full bg-maple px-2 py-0.5 text-xs font-semibold text-surface">{unread}</NavLink>}
      </header>
      {open && <div className="fixed inset-0 z-40 bg-ink/40 backdrop-blur-sm lg:hidden" onClick={() => setOpen(false)} aria-hidden />}
      <aside id="sidebar"
        className={`fixed inset-y-0 left-0 z-50 flex w-[260px] flex-col overflow-y-auto overflow-x-hidden bg-pine text-pine-ink transition-transform duration-300 ease-out lg:w-[232px] lg:translate-x-0 ${open ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="pointer-events-none absolute -left-16 -top-16 h-56 w-56 rounded-full bg-accent/40 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-20 -right-16 h-56 w-56 rounded-full bg-maple/25 blur-3xl" />
        <div className="relative px-5 pb-6 pt-6">
          <div className="flex items-center gap-2.5">
            <Mark />
            <div className="font-serif text-lg font-medium leading-tight">Opportunity<br />Matcher</div>
            <button type="button" aria-label="Close the menu" onClick={() => setOpen(false)} className="ml-auto rounded-md p-1.5 hover:bg-white/10 lg:hidden"><X className="h-4 w-4" aria-hidden /></button>
          </div>
          <div className="mt-3 inline-block rounded-full bg-white/10 px-2.5 py-0.5 text-xs font-medium uppercase tracking-[0.08em] text-pine-ink">{area}</div>
        </div>
        <nav className="relative flex flex-col gap-1 px-3" aria-label={`${area} menu`}>
          <AnimatedBackground value={active} className="rounded-md bg-white/10">
            {items.flatMap((n, i) => [
              ...(n.group && n.group !== items[i - 1]?.group
                ? [<div key={`g-${n.group}`} data-id={`group:${n.group}`} className="mt-3 px-3 pb-0.5 text-[11px] font-medium uppercase tracking-[0.1em] text-pine-soft">{n.group}</div>]
                : []),
              <NavLink key={n.to} to={n.to} data-id={n.to} end={n.end}
                className={`rounded-md px-3 py-2.5 text-sm font-medium transition-colors hover:text-pine-ink lg:py-2 ${active === n.to ? 'text-pine-ink' : 'text-pine-soft'}`}>
                <n.icon className="h-4 w-4" aria-hidden />{n.label}
                {n.badge ? <span className="ml-auto rounded-full bg-maple px-1.5 py-px text-xs font-semibold text-surface" aria-label={`${n.badge} new`}>{n.badge}</span> : null}
              </NavLink>,
            ])}
          </AnimatedBackground>
        </nav>
        <div className="relative mt-auto space-y-3 border-t border-white/10 px-5 py-5">{footer}</div>
      </aside>
      <main className="min-w-0 lg:ml-[232px]"><Outlet /></main>
    </div>
  )
}
