const TOKEN_KEY = 'subsy.token'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export const tokenStore = {
  get: () => { try { return localStorage.getItem(TOKEN_KEY) } catch { return null } },
  set: (t: string) => { try { localStorage.setItem(TOKEN_KEY, t) } catch { /* storage unavailable */ } },
  clear: () => { try { localStorage.removeItem(TOKEN_KEY) } catch { /* ignore */ } },
}

let onUnauthorized: () => void = () => {}
export const setUnauthorizedHandler = (fn: () => void) => { onUnauthorized = fn }

function errorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const d = (body as { detail: unknown }).detail
    if (typeof d === 'string') return d
    if (Array.isArray(d)) {
      return d.map((e: { loc?: unknown[]; msg?: string }) => {
        const field = e.loc?.filter((x) => x !== 'body').join('.')
        return field ? `${field}: ${e.msg?.replace('Value error, ', '')}` : e.msg
      }).join('; ')
    }
  }
  return fallback
}

export async function api<T = unknown>(path: string, opts: { method?: string; body?: unknown; params?: Record<string, unknown> } = {}): Promise<T> {
  const url = new URL(`/api${path}`, window.location.origin)
  Object.entries(opts.params ?? {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v))
  })
  const headers: Record<string, string> = {}
  const token = tokenStore.get()
  if (token) headers.Authorization = `Bearer ${token}`
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json'
  let res: Response
  try {
    res = await fetch(url.toString().replace(window.location.origin, ''), {
      method: opts.method ?? (opts.body !== undefined ? 'POST' : 'GET'),
      headers, body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    })
  } catch {
    throw new ApiError(0, 'Cannot reach the Subsy server. Check that the backend is running.')
  }
  const text = await res.text()
  const body = text ? (() => { try { return JSON.parse(text) } catch { return text } })() : null
  if (!res.ok) {
    if (res.status === 401 && token) onUnauthorized()
    throw new ApiError(res.status, errorMessage(body, `Request failed (${res.status})`))
  }
  return body as T
}

/** Download a protected file (PDF/CSV) with the auth header and hand it to the browser. */
export async function download(path: string, params: Record<string, unknown> = {}) {
  const url = new URL(`/api${path}`, window.location.origin)
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v)) })
  const res = await fetch(url, { headers: { Authorization: `Bearer ${tokenStore.get() ?? ''}` } })
  if (!res.ok) throw new ApiError(res.status, 'Download failed')
  const blob = await res.blob()
  const name = res.headers.get('Content-Disposition')?.match(/filename="(.+)"/)?.[1] ?? 'download'
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 2000)
}
