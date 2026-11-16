export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

let csrfToken = ''
let onUnauthorized: (() => void) | null = null
export const setCsrf = (t: string) => { csrfToken = t }
export const setUnauthorizedHandler = (fn: (() => void) | null) => { onUnauthorized = fn }

export function errorTitle(status: number): string {
  switch (status) {
    case 401: return 'Please sign in (401)'
    case 403: return 'You do not have access to this (403)'
    case 413: return 'That is too large (413)'
    case 429: return 'Too many tries (429)'
    case 404: return 'Not found (404)'
    case 422: return 'That input was not accepted (422)'
    case 503: return 'Not published yet (503)'
    case 0: return 'API unreachable'
    default: return `Something went wrong (${status})`
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    const unsafe = init?.method && init.method !== 'GET'
    const headers = new Headers(init?.headers)
    if (unsafe && csrfToken) headers.set('X-CSRF-Token', csrfToken)
    res = await fetch(path, { ...init, headers, credentials: 'same-origin' })
  } catch {
    throw new ApiError(0, 'The API is not running. Start it with make app, then try again.')
  }
  if (res.status === 401 && !path.startsWith('/api/auth/login') && !path.startsWith('/api/auth/me')) onUnauthorized?.()
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail ?? detail } catch { /* keep status text */ }
    throw new ApiError(res.status, typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return res.json() as Promise<T>
}

export const get = <T,>(path: string) => request<T>(path)
export const post = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const put = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const del = <T,>(path: string) => request<T>(path, { method: 'DELETE' })

export const patch = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const upload = <T,>(path: string, form: FormData) => request<T>(path, { method: 'POST', body: form })
