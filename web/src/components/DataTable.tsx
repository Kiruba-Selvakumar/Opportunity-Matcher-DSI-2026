import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Download } from 'lucide-react'
import { cn } from '../lib/utils'

export interface Column<T> {
  key: string
  header: string
  render: (row: T) => ReactNode
  /** Makes the column sortable. Return a number or a string. */
  sort?: (row: T) => number | string | null
  className?: string
  csv?: (row: T) => string | number | null
}

interface Props<T> {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string | number
  onRowClick?: (row: T) => void
  selectedKey?: string | number
  pageSize?: number
  initialSort?: { key: string; dir: 'asc' | 'desc' }
  csvName?: string
  className?: string
}

const cmp = (a: number | string | null, b: number | string | null) => {
  if (a === b) return 0
  if (a === null) return 1          // blanks always last
  if (b === null) return -1
  return typeof a === 'number' && typeof b === 'number' ? a - b : String(a).localeCompare(String(b), undefined, { numeric: true })
}

/** One table for every long list: sortable headers, pages of 25, keyboard rows, and a CSV of what is on screen. */
export function DataTable<T>({ columns, rows, rowKey, onRowClick, selectedKey, pageSize = 25, initialSort, csvName, className }: Props<T>) {
  const [sort, setSort] = useState(initialSort ?? null)
  const [page, setPage] = useState(0)

  const sorted = useMemo(() => {
    const col = columns.find((c) => c.key === sort?.key)
    if (!col?.sort || !sort) return rows
    const f = col.sort
    return [...rows].sort((a, b) => (sort.dir === 'asc' ? 1 : -1) * cmp(f(a), f(b)))
  }, [rows, columns, sort])

  const pages = Math.max(1, Math.ceil(sorted.length / pageSize))
  useEffect(() => { setPage(0) }, [rows.length, sort?.key, sort?.dir])
  const shown = sorted.slice(page * pageSize, page * pageSize + pageSize)

  const toggle = (key: string) => setSort((cur) => (cur?.key === key ? { key, dir: cur.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'asc' }))

  const exportCsv = () => {
    const cols = columns.filter((c) => c.csv)
    const esc = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`
    const text = [cols.map((c) => esc(c.header)).join(','), ...sorted.map((r) => cols.map((c) => esc(c.csv!(r))).join(','))].join('\n')
    const url = URL.createObjectURL(new Blob([text], { type: 'text/csv' }))
    const a = Object.assign(document.createElement('a'), { href: url, download: `${csvName ?? 'export'}.csv` })
    a.click(); URL.revokeObjectURL(url)
  }

  return (
    <div className={className}>
      <div className="card pop overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c.key} className="th" aria-sort={sort?.key === c.key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : undefined}>
                  {c.sort ? (
                    <button type="button" onClick={() => toggle(c.key)} className="inline-flex items-center gap-1 uppercase tracking-[0.06em] hover:text-ink">
                      {c.header}
                      {sort?.key === c.key && (sort.dir === 'asc' ? <ArrowUp className="h-3 w-3" aria-hidden /> : <ArrowDown className="h-3 w-3" aria-hidden />)}
                    </button>
                  ) : c.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => {
              const k = rowKey(r)
              return (
                <tr key={k} tabIndex={onRowClick ? 0 : undefined} aria-selected={selectedKey !== undefined ? k === selectedKey : undefined}
                  onClick={onRowClick ? () => onRowClick(r) : undefined}
                  onKeyDown={onRowClick ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onRowClick(r) } } : undefined}
                  className={cn('transition-colors hover:bg-[#f6f0e3]', onRowClick && 'cursor-pointer', selectedKey !== undefined && k === selectedKey && 'bg-accent-soft hover:bg-accent-soft')}>
                  {columns.map((c) => <td key={c.key} className={cn('td', c.className)}>{c.render(r)}</td>)}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-sm text-ink-soft">
        <span aria-live="polite">
          {sorted.length === 0 ? 'Nothing to show' : `Showing ${page * pageSize + 1} to ${Math.min(sorted.length, (page + 1) * pageSize)} of ${sorted.length}`}
        </span>
        <div className="flex items-center gap-1">
          {csvName && columns.some((c) => c.csv) && <button type="button" className="btn btn-quiet" onClick={exportCsv}><Download className="h-4 w-4" aria-hidden />Download CSV</button>}
          {pages > 1 && (
            <>
              <button type="button" className="btn btn-quiet" disabled={page === 0} onClick={() => setPage(page - 1)} aria-label="Previous page"><ChevronLeft className="h-4 w-4" aria-hidden /></button>
              <span>Page {page + 1} of {pages}</span>
              <button type="button" className="btn btn-quiet" disabled={page >= pages - 1} onClick={() => setPage(page + 1)} aria-label="Next page"><ChevronRight className="h-4 w-4" aria-hidden /></button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
