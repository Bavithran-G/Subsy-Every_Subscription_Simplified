const inrFmt = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 })
const inrShort = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', notation: 'compact', maximumFractionDigits: 1 })

export const inr = (v: number | string | null | undefined) => inrFmt.format(Number(v ?? 0))
export const inrCompact = (v: number | string | null | undefined) => inrShort.format(Number(v ?? 0))
export const num = (v: number | string | null | undefined) => new Intl.NumberFormat('en-IN').format(Number(v ?? 0))

export function fdate(v?: string | null) {
  if (!v) return '—'
  const d = new Date(v.length === 10 ? `${v}T00:00:00` : v)
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}
export function fdatetime(v?: string | null) {
  if (!v) return '—'
  return new Date(v).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}
export function ago(v?: string | null) {
  if (!v) return ''
  const s = (Date.now() - new Date(v).getTime()) / 1000
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}
export const monthLabel = (m: string) => {
  const [y, mo] = m.split('-').map(Number)
  return new Date(y, mo - 1, 1).toLocaleDateString('en-IN', { month: 'short', year: '2-digit' })
}
export const titleCase = (s: string) => s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
export const periodLabel: Record<string, string> = { daily: 'Daily', weekly: 'Weekly', monthly: 'Monthly', yearly: 'Yearly' }
export const methodLabel: Record<string, string> = {
  bank_transfer: 'Bank transfer', upi: 'UPI', card: 'Card', cash: 'Cash', cheque: 'Cheque', other: 'Other',
}
export const todayISO = () => {
  const d = new Date()
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10)
}
