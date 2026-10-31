import { Search, X } from 'lucide-react'
import { useState } from 'react'
import { useApi, useDebounced } from '../lib/hooks'
import type { Customer, Page } from '../lib/types'

/** Server-side search so it stays fast with thousands of customers (a plain <select> cannot). */
export function CustomerPicker({ value, onChange }: { value: string; onChange: (id: string) => void }) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const dq = useDebounced(q, 200)
  const { data: selected } = useApi<Customer>(value ? `/customers/${value}` : null)
  const { data } = useApi<Page<Customer>>(open ? '/customers' : null, { q: dq, page_size: 8 })
  if (value && selected) {
    return (
      <div className="flex h-9 items-center justify-between rounded-lg border border-brand-200 bg-brand-50/40 px-3">
        <span className="truncate"><b>{selected.name}</b>{selected.company && <span className="text-ink-soft"> — {selected.company}</span>}</span>
        <button type="button" onClick={() => { onChange(''); setQ(''); setOpen(true) }} className="text-ink-soft hover:text-bad" aria-label="Change customer"><X className="h-4 w-4" /></button>
      </div>
    )
  }
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
      <input className="input pl-9" placeholder="Search customer by name, email or company…" value={q} aria-label="Customer"
        onChange={(e) => { setQ(e.target.value); setOpen(true) }} onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)} />
      {open && (
        <ul className="absolute left-0 right-0 top-10 z-20 max-h-72 overflow-y-auto rounded-xl border border-line bg-white p-1 shadow-pop" role="listbox">
          {!data?.items.length && <li className="px-3 py-2 text-[13px] text-ink-soft">{data ? 'No matching customers' : 'Searching…'}</li>}
          {data?.items.map((c) => (
            <li key={c.id}><button type="button" role="option" onMouseDown={() => { onChange(String(c.id)); setOpen(false) }} className="flex w-full flex-col rounded-lg px-3 py-1.5 text-left hover:bg-brand-50">
              <span className="font-semibold">{c.name}{c.company && <span className="font-normal text-ink-soft"> — {c.company}</span>}</span><span className="text-[12px] text-ink-soft">{c.email}</span>
            </button></li>))}
          {data && data.total > data.items.length && <li className="px-3 py-1.5 text-[11px] text-ink-faint">{data.total - data.items.length} more — keep typing to narrow</li>}
        </ul>
      )}
    </div>
  )
}
