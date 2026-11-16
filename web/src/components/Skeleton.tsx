import { cn } from '../lib/utils'

/** A grey placeholder while something loads, so the page does not jump when it arrives. */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-md bg-sunk', className)} aria-hidden />
}

export function CardsSkeleton({ n = 3 }: { n?: number }) {
  return (
    <div className="space-y-3" role="status" aria-label="Loading">
      {Array.from({ length: n }).map((_, i) => (
        <div key={i} className="card space-y-3 p-5"><Skeleton className="h-4 w-1/4" /><Skeleton className="h-6 w-2/3" /><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-5/6" /></div>
      ))}
    </div>
  )
}

export function TableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="card space-y-3 p-4" role="status" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => <Skeleton key={i} className="h-5 w-full" />)}
    </div>
  )
}
