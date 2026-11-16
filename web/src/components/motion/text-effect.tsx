import { motion, useReducedMotion } from 'motion/react'
import { cn } from '../../lib/utils'

interface Props {
  children: string
  className?: string
  /** Seconds between words. */
  stagger?: number
}

/** Reveals text word by word, fading up out of a blur (the fade-in-blur preset). */
export function TextEffect({ children, className, stagger = 0.045 }: Props) {
  const reduce = useReducedMotion()
  if (reduce) return <span className={className}>{children}</span>
  return (
    <span className={cn('inline', className)} aria-label={children}>
      {children.split(' ').map((w, i) => (
        <motion.span
          key={i}
          aria-hidden
          className="inline-block whitespace-pre"
          initial={{ opacity: 0, filter: 'blur(12px)', y: 6 }}
          animate={{ opacity: 1, filter: 'blur(0px)', y: 0 }}
          transition={{ duration: 0.4, delay: 0.1 + i * stagger, ease: [0.16, 1, 0.3, 1] }}
        >
          {w + ' '}
        </motion.span>
      ))}
    </span>
  )
}
