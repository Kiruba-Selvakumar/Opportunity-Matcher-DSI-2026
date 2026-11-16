import { Component, type ReactNode } from 'react'

/** If a screen crashes, show a plain message and a way back, never a blank page. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidCatch(error: unknown) { console.error(error) }
  render() {
    if (!this.state.failed) return this.props.children
    return (
      <div className="mx-auto max-w-md px-8 py-24 text-center" role="alert">
        <h1>Something went wrong</h1>
        <p className="mt-3 text-base text-ink-soft">This screen hit a problem. Your work on other screens is safe.</p>
        <button type="button" className="btn btn-primary mt-6" onClick={() => location.reload()}>Reload</button>
      </div>
    )
  }
}
