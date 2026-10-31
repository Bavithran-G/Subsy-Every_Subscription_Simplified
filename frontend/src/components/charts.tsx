import type { ReactNode } from 'react'
import { inr, inrCompact } from '../lib/format'

export const C = { brand: '#C62828', brandDark: '#8E1B1B', brandSoft: '#F29B9B', ink: '#202124', ok: '#16845B', warn: '#D97706', grey: '#9CA3AF', line: '#E5E7EB', info: '#2563EB' }
export const stateColor: Record<string, string> = {
  draft: '#9CA3AF', quotation: '#2563EB', confirmed: '#8E1B1B', active: '#16845B', paused: '#D97706', closed: '#6B7280', cancelled: '#D1D5DB',
  paid: '#16845B',
}
export const axis = { stroke: C.grey, fontSize: 11, tickLine: false, axisLine: false }

export function ChartTip({ active, payload, label, money = true, labelFmt }: {
  active?: boolean; payload?: { name: string; value: number; color: string }[]; label?: string; money?: boolean; labelFmt?: (l: string) => string
}): ReactNode {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-line bg-white px-3 py-2 text-[12px] shadow-pop">
      <p className="mb-1 font-semibold">{labelFmt ? labelFmt(String(label)) : label}</p>
      {payload.map((p) => (
        <p key={p.name} className="flex items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ background: p.color }} />
          <span className="text-ink-soft">{p.name}</span><span className="ml-auto pl-3 font-mono font-semibold">{money ? inr(p.value) : p.value.toLocaleString('en-IN')}</span></p>
      ))}
    </div>
  )
}
export const moneyTick = (v: number) => inrCompact(v).replace('₹', '₹')
