import { Children, cloneElement, isValidElement, useId, useState, type ReactElement, type ReactNode } from 'react'
import { motion, type Transition } from 'motion/react'
import { cn } from '../../lib/utils'

interface Props {
  children: ReactNode
  /** Controlled active id. If omitted the component keeps its own. */
  value?: string
  defaultValue?: string
  onValueChange?: (id: string) => void
  /** Style of the moving background (the pill or underline). */
  className?: string
  transition?: Transition
}

/** One shared background that slides to the active child. Each child needs a data-id. */
export function AnimatedBackground({ children, value, defaultValue, onValueChange, className, transition }: Props) {
  const uid = useId()
  const [inner, setInner] = useState(defaultValue)
  const active = value ?? inner
  return (
    <>
      {Children.map(children, (child) => {
        if (!isValidElement(child)) return child
        const el = child as ReactElement<Record<string, unknown>>
        const id = el.props['data-id'] as string
        const oldClick = el.props.onClick as ((e: unknown) => void) | undefined
        return cloneElement(
          el,
          {
            className: cn('relative', el.props.className as string | undefined),
            onClick: (e: unknown) => {
              setInner(id)
              onValueChange?.(id)
              oldClick?.(e)
            },
          },
          <>
            {active === id && (
              <motion.span
                layoutId={`bg-${uid}`}
                className={cn('absolute inset-0 -z-0', className)}
                transition={transition ?? { type: 'spring', bounce: 0.15, duration: 0.4 }}
              />
            )}
            <span className="relative z-10 flex w-full items-center gap-2.5">{el.props.children as ReactNode}</span>
          </>,
        )
      })}
    </>
  )
}
