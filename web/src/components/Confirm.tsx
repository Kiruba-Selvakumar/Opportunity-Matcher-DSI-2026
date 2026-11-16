import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'

interface Options { title: string; body?: string; confirmLabel?: string; danger?: boolean }
type Ask = (o: Options) => Promise<boolean>
const Ctx = createContext<Ask>(async () => true)

/** Ask before anything that cannot be undone. Esc or clicking outside means no. */
export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [opts, setOpts] = useState<Options | null>(null)
  const resolve = useRef<((v: boolean) => void) | null>(null)
  const cancel = useRef<HTMLButtonElement>(null)

  const ask = useCallback<Ask>((o) => new Promise((res) => { resolve.current = res; setOpts(o) }), [])
  const done = (v: boolean) => { resolve.current?.(v); resolve.current = null; setOpts(null) }

  useEffect(() => {
    if (!opts) return
    cancel.current?.focus()
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') done(false) }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [opts])

  return (
    <Ctx.Provider value={ask}>
      {children}
      {opts && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 p-4 backdrop-blur-sm" onClick={() => done(false)}>
          <div role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby="confirm-body"
            className="slide-in w-full max-w-sm rounded-xl border border-line bg-surface p-5 shadow-lift" onClick={(e) => e.stopPropagation()}>
            <h2 id="confirm-title">{opts.title}</h2>
            {opts.body && <p id="confirm-body" className="mt-2 text-sm text-ink-soft">{opts.body}</p>}
            <div className="mt-5 flex justify-end gap-2">
              <button ref={cancel} type="button" className="btn" onClick={() => done(false)}>Cancel</button>
              <button type="button" className={opts.danger ? 'btn btn-danger' : 'btn btn-primary'} onClick={() => done(true)}>{opts.confirmLabel ?? 'Yes'}</button>
            </div>
          </div>
        </div>
      )}
    </Ctx.Provider>
  )
}

export const useConfirm = () => useContext(Ctx)
