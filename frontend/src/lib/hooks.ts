import { useMutation, useQuery, useQueryClient, type UseQueryOptions } from '@tanstack/react-query'
import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from './api'
import { useUi } from '../components/ui'

export function useApi<T>(path: string | null, params?: Record<string, unknown>, opts?: Partial<UseQueryOptions<T>>) {
  return useQuery<T>({
    queryKey: [path, params ?? {}],
    queryFn: () => api<T>(path!, { params }),
    enabled: !!path,
    ...opts,
  })
}

/** Run a write, toast the result, and refresh every cached query (all modules share records). */
export function useAction() {
  const qc = useQueryClient()
  const { toast } = useUi()
  return useMutation({
    mutationFn: async (fn: () => Promise<unknown>) => fn(),
    onSuccess: () => qc.invalidateQueries(),
    onError: (e: Error) => toast('error', e.message),
  })
}

export function useRunner() {
  const qc = useQueryClient()
  const { toast } = useUi()
  const [busy, setBusy] = useState<string | null>(null)
  const run = useCallback(async <T,>(key: string, fn: () => Promise<T>, success?: string | ((r: T) => string)): Promise<T | undefined> => {
    setBusy(key)
    try {
      const r = await fn()
      if (success) toast('success', typeof success === 'function' ? success(r) : success)
      await qc.invalidateQueries()
      return r
    } catch (e) {
      toast('error', (e as Error).message)
      return undefined
    } finally {
      setBusy(null)
    }
  }, [qc, toast])
  return { run, busy }
}

/** Filters kept in the URL so KPI/chart drill-downs can link straight to a filtered list. */
export function useUrlFilters<T extends Record<string, string>>(defaults: T) {
  const [sp, setSp] = useSearchParams()
  const values = { ...defaults } as T
  Object.keys(defaults).forEach((k) => { const v = sp.get(k); if (v !== null) (values as Record<string, string>)[k] = v })
  const set = useCallback((patch: Partial<T>) => {
    setSp((prev) => {
      const next = new URLSearchParams(prev)
      Object.entries(patch).forEach(([k, v]) => { if (v === '' || v === undefined || v === null) next.delete(k); else next.set(k, String(v)) })
      if (!('page' in patch)) next.delete('page')
      return next
    }, { replace: true })
  }, [setSp])
  return [values, set] as const
}

export function useDebounced<T>(value: T, ms = 300) {
  const [v, setV] = useState(value)
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t) }, [value, ms])
  return v
}
