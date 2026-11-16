import { useEffect, useRef } from 'react'
import { Search, X } from 'lucide-react'

export function SearchBox({ value, onChange, placeholder, label }: { value: string; onChange: (v: string) => void; placeholder: string; label: string }) {
  const ref = useRef<HTMLInputElement>(null)
  // press / anywhere on the page to jump to the search box
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (e.key === '/' && !(t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable))) {
        e.preventDefault(); ref.current?.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])
  return (
    <div className="relative">
      <label htmlFor="search" className="sr-only">{label}</label>
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" aria-hidden />
      <input id="search" ref={ref} type="search" className="input !rounded-lg !py-2.5 !pl-9 !pr-9 !text-base" value={value}
        onChange={(e) => onChange(e.target.value)} placeholder={placeholder} autoComplete="off" />
      {value && (
        <button type="button" aria-label="Clear search" onClick={() => onChange('')}
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-ink-faint hover:bg-sunk hover:text-ink">
          <X className="h-4 w-4" aria-hidden />
        </button>
      )}
    </div>
  )
}
