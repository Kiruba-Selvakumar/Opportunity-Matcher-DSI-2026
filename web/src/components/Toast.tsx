import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react'
import { CheckCircle2, OctagonAlert, X } from 'lucide-react'
import { cn } from '../lib/utils'

type Tone = 'pass' | 'fail'
interface T { id: number; text: string; tone: Tone }
const Ctx = createContext<(text: string, tone?: Tone) => void>(() => {})

/** Short messages in the corner: "Saved", "Sent", or what went wrong. Success fades after 4 seconds, errors stay for 8. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<T[]>([])
  const next = useRef(1)
  const dismiss = useCallback((id: number) => setItems((cur) => cur.filter((t) => t.id !== id)), [])
  const toast = useCallback((text: string, tone: Tone = 'pass') => {
    const id = next.current++
    setItems((cur) => [...cur.slice(-3), { id, text, tone }])
    setTimeout(() => dismiss(id), tone === 'pass' ? 4000 : 8000)
  }, [dismiss])
  return (
    <Ctx.Provider value={toast}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} role={t.tone === 'fail' ? 'alert' : 'status'}
            className={cn('pop pointer-events-auto flex items-start gap-2 rounded-lg border px-3 py-2.5 text-sm shadow-lift',
              t.tone === 'pass' ? 'border-pass-line bg-pass-soft text-pass' : 'border-fail-line bg-fail-soft text-fail')}>
            {t.tone === 'pass' ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> : <OctagonAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />}
            <span className="flex-1">{t.text}</span>
            <button type="button" aria-label="Dismiss" onClick={() => dismiss(t.id)} className="rounded p-0.5 hover:bg-black/5"><X className="h-3.5 w-3.5" aria-hidden /></button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  )
}

export const useToast = () => useContext(Ctx)
