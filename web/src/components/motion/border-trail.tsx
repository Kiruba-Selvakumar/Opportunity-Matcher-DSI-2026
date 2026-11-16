import { motion, type Transition } from 'motion/react'
import type { CSSProperties } from 'react'
import { cn } from '../../lib/utils'

interface Props {
  className?: string
  size?: number
  transition?: Transition
  style?: CSSProperties
}

/** A small light that travels round the parent's border. The parent must be position: relative. */
export function BorderTrail({ className, size = 60, transition, style }: Props) {
  return (
    <div
      className="pointer-events-none absolute inset-0 rounded-[inherit] border border-transparent"
      style={{
        WebkitMask: 'linear-gradient(transparent, transparent) padding-box, linear-gradient(#000, #000) border-box',
        WebkitMaskComposite: 'source-in',
        mask: 'linear-gradient(transparent, transparent) padding-box, linear-gradient(#000, #000) border-box',
        maskComposite: 'intersect',
      }}
    >
      <motion.div
        className={cn('absolute aspect-square bg-sky', className)}
        style={{ width: size, offsetPath: `rect(0 auto auto 0 round ${size}px)`, ...style } as CSSProperties}
        animate={{ offsetDistance: ['0%', '100%'] }}
        transition={{ repeat: Infinity, duration: 9, ease: 'linear', ...transition }}
      />
    </div>
  )
}
