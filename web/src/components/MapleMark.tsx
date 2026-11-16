export function Mark({ className = 'h-7 w-7' }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <rect width="32" height="32" rx="7" fill="#1c4535" />
      <path d="M9 22V10h6.2a4.2 4.2 0 0 1 0 8.4H9m10 3.6-3.6-5" stroke="#e9e4d4" strokeWidth="2.4" fill="none" strokeLinecap="round" />
      <circle cx="23" cy="10" r="2.6" fill="#c0392b" />
    </svg>
  )
}
