import { Download } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { C, ChartTip, axis, moneyTick } from '../components/charts'
import { Button, Card, ErrorBox, PageHeader, Skeleton, Status, Tabs, useUi } from '../components/ui'
import { download } from '../lib/api'
import { fdate, inr, methodLabel, monthLabel, num, periodLabel, titleCase } from '../lib/format'
import { useApi, useUrlFilters } from '../lib/hooks'
import { DashFilters } from './Overview'

type R = Record<string, unknown> & { summary: Record<string, number> }
type Tab = 'subscriptions' | 'revenue' | 'invoices' | 'payments' | 'discounts'

function Stat({ label, value, money = false, tone }: { label: string; value: number; money?: boolean; tone?: string }) {
  return <div className="card p-4"><p className="text-[12px] font-semibold uppercase tracking-wide text-ink-soft">{label}</p><p className={`mt-1 font-display text-[22px] font-bold num ${tone ?? ''}`}>{money ? inr(value) : num(value)}</p></div>
}
function Table<T extends Record<string, unknown>>({ rows, cols }: { rows: T[]; cols: [keyof T, string, ((v: unknown, r: T) => React.ReactNode)?][] }) {
  if (!rows.length) return <p className="p-5 text-ink-soft">No data for this range.</p>
  return (
    <div className="overflow-x-auto"><table className="w-full min-w-[520px] text-[13px]">
      <thead><tr>{cols.map(([k, l]) => <th key={String(k)} className="th">{l}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i} className="hover:bg-canvas">{cols.map(([k, , fmt]) => <td key={String(k)} className="td">{fmt ? fmt(r[k], r) : String(r[k] ?? '—')}</td>)}</tr>)}</tbody>
    </table></div>
  )
}
const money = (v: unknown) => <span className="num">{inr(v as number)}</span>

export default function Reports() {
  const [f, set] = useUrlFilters({ tab: 'revenue', date_from: '', date_to: '', plan_id: '' })
  const tab = f.tab as Tab
  const { data, isLoading, error, refetch } = useApi<R>(`/reports/${tab}`, { date_from: f.date_from, date_to: f.date_to, plan_id: f.plan_id })
  const { toast } = useUi()
  const csv = (table?: string) => download(`/reports/${tab}/csv`, { table, date_from: f.date_from, date_to: f.date_to, plan_id: f.plan_id }).catch((e) => toast('error', e.message))
  const s = data?.summary
  const d = data as Record<string, never> | undefined
  return (
    <>
      <PageHeader title="Reports & analytics" subtitle="Every figure is aggregated from the live invoice, payment and subscription records."
        actions={<><DashFilters f={f} set={set} /><Button icon={<Download className="h-4 w-4" />} onClick={() => csv()}>Export CSV</Button></>} />
      <div className="mb-5"><Tabs value={tab} onChange={(t) => set({ tab: t })} tabs={[{ id: 'revenue', label: 'Revenue' }, { id: 'subscriptions', label: 'Subscriptions' }, { id: 'invoices', label: 'Invoices' }, { id: 'payments', label: 'Payments' }, { id: 'discounts', label: 'Discounts' }]} /></div>
      {error && <ErrorBox error={error} onRetry={refetch} />}
      {isLoading || !s || !d ? <div className="grid gap-4 md:grid-cols-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)}</div> : (
        <div className="space-y-5">
          {tab === 'revenue' && <>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
              <Stat label="Invoiced" value={s.revenue_invoiced} money /><Stat label="Collected" value={s.revenue_collected} money tone="text-ok" />
              <Stat label="Outstanding" value={s.outstanding_amount} money tone="text-warn" /><Stat label="Overdue" value={s.overdue_amount} money tone="text-bad" />
              <Stat label="MRR" value={s.mrr} money /><Stat label="Discounts given" value={s.discount_amount} money />
            </div>
            <Card title="Revenue by month" actions={<Button size="sm" variant="ghost" icon={<Download className="h-3.5 w-3.5" />} onClick={() => csv('monthly')}>CSV</Button>}>
              <div className="h-[300px]"><ResponsiveContainer><ComposedChart data={d.monthly} margin={{ left: 4, right: 8 }}>
                <CartesianGrid vertical={false} stroke={C.line} /><XAxis dataKey="month" tickFormatter={monthLabel} {...axis} /><YAxis tickFormatter={moneyTick} {...axis} width={56} />
                <Tooltip content={<ChartTip labelFmt={monthLabel} />} /><Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="invoiced" name="Invoiced" fill={C.brand} radius={[4, 4, 0, 0]} maxBarSize={32} /><Line dataKey="collected" name="Collected" stroke={C.ok} strokeWidth={2.5} />
              </ComposedChart></ResponsiveContainer></div>
            </Card>
            <div className="grid gap-5 xl:grid-cols-3">
              <Card title="By plan" pad={false} actions={<Button size="sm" variant="ghost" onClick={() => csv('by_plan')}>CSV</Button>}><Table rows={d.by_plan} cols={[['plan', 'Plan'], ['invoiced', 'Invoiced', money], ['collected_on_these', 'Paid', money]]} /></Card>
              <Card title="By product (net of discounts)" pad={false} actions={<Button size="sm" variant="ghost" onClick={() => csv('by_product')}>CSV</Button>}><Table rows={d.by_product} cols={[['product', 'Product'], ['units', 'Units'], ['net_revenue', 'Net revenue', money]]} /></Card>
              <Card title="Top customers" pad={false} actions={<Button size="sm" variant="ghost" onClick={() => csv('by_customer')}>CSV</Button>}><Table rows={d.by_customer} cols={[['customer', 'Customer'], ['invoiced', 'Invoiced', money], ['paid', 'Paid', money]]} /></Card>
            </div>
          </>}

          {tab === 'subscriptions' && <>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
              <Stat label="Total" value={s.total_subscriptions} /><Stat label="Active" value={s.active_subscriptions} tone="text-ok" /><Stat label="Paused" value={s.paused_subscriptions} tone="text-warn" />
              <Stat label="Closed" value={s.closed_subscriptions} /><Stat label="Renewing · 30d" value={s.upcoming_renewals} /><Stat label="Awaiting confirm" value={s.awaiting_confirmation} />
            </div>
            <div className="grid gap-5 xl:grid-cols-2">
              <Card title="Distribution by plan" pad={false} actions={<Button size="sm" variant="ghost" onClick={() => csv('by_plan')}>CSV</Button>}>
                <Table rows={d.by_plan} cols={[['plan', 'Plan'], ['billing_period', 'Billing', (v) => periodLabel[v as string]], ['total', 'All-time'], ['active', 'Active']]} /></Card>
              <Card title="Live subscriptions by billing frequency">
                <div className="h-[240px]"><ResponsiveContainer><BarChart data={d.by_frequency}>
                  <CartesianGrid vertical={false} stroke={C.line} /><XAxis dataKey="billing_period" tickFormatter={(v) => periodLabel[v]} {...axis} /><YAxis allowDecimals={false} {...axis} />
                  <Tooltip content={<ChartTip money={false} labelFmt={(l) => periodLabel[l]} />} /><Bar dataKey="count" name="Subscriptions" fill={C.brand} radius={[4, 4, 0, 0]} maxBarSize={56} />
                </BarChart></ResponsiveContainer></div></Card>
            </div>
            <Card title="Renewal overview" pad={false}><Table rows={d.renewals} cols={[['label', 'Window'], ['count', 'Subscriptions'], ['view', '', (v) => v ? <Link className="link" to={`/subscriptions?view=${v}`}>View</Link> : null]]} /></Card>
          </>}

          {tab === 'invoices' && <>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
              <Stat label="Total" value={s.total_invoices} /><Stat label="Draft" value={s.draft_invoices} /><Stat label="Confirmed" value={s.confirmed_invoices} />
              <Stat label="Paid" value={s.paid_invoices} tone="text-ok" /><Stat label="Cancelled" value={s.cancelled_invoices} />
              <Stat label="Outstanding" value={s.outstanding_invoices} tone="text-warn" /><Stat label="Overdue" value={s.overdue_invoices} tone="text-bad" />
              <Stat label="Outstanding ₹" value={s.outstanding_amount} money /><Stat label="Overdue ₹" value={s.overdue_amount} money tone="text-bad" />
            </div>
            <div className="grid gap-5 xl:grid-cols-2">
              <Card title="Invoice aging">
                <div className="h-[240px]"><ResponsiveContainer><BarChart data={d.aging}>
                  <CartesianGrid vertical={false} stroke={C.line} /><XAxis dataKey="bucket" {...axis} /><YAxis tickFormatter={moneyTick} {...axis} />
                  <Tooltip content={<ChartTip />} /><Bar dataKey="amount" name="Amount due" radius={[4, 4, 0, 0]}>{(d.aging as { bucket: string }[]).map((a, i) => <Cell key={a.bucket} fill={i === 0 ? C.warn : C.brand} />)}</Bar>
                </BarChart></ResponsiveContainer></div></Card>
              <Card title="Overdue invoices" pad={false} actions={<Button size="sm" variant="ghost" onClick={() => csv('top_overdue')}>CSV</Button>}>
                <Table rows={d.top_overdue} cols={[['number', 'Invoice', (v, r) => <Link className="link" to={`/invoices/${r.id}`}>{v as string}</Link>], ['customer', 'Customer'], ['due_date', 'Due', (v) => fdate(v as string)], ['days_overdue', 'Days late'], ['amount_due', 'Due', money]]} /></Card>
            </div>
          </>}

          {tab === 'payments' && <>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Stat label="Payments" value={s.payments} /><Stat label="Collected" value={s.amount} money tone="text-ok" /><Stat label="Part-paid invoices" value={s.partially_paid_invoices} tone="text-warn" /><Stat label="Voided" value={s.voided} />
            </div>
            <div className="grid gap-5 xl:grid-cols-2">
              <Card title="By payment method" pad={false} actions={<Button size="sm" variant="ghost" onClick={() => csv('by_method')}>CSV</Button>}><Table rows={d.by_method} cols={[['method', 'Method', (v) => methodLabel[v as string]], ['count', 'Payments'], ['amount', 'Amount', money]]} /></Card>
              <Card title="Payments by month"><div className="h-[220px]"><ResponsiveContainer><BarChart data={d.by_month}>
                <CartesianGrid vertical={false} stroke={C.line} /><XAxis dataKey="month" tickFormatter={monthLabel} {...axis} /><YAxis tickFormatter={moneyTick} {...axis} />
                <Tooltip content={<ChartTip labelFmt={monthLabel} />} /><Bar dataKey="amount" name="Collected" fill={C.ok} radius={[4, 4, 0, 0]} maxBarSize={32} />
              </BarChart></ResponsiveContainer></div></Card>
              <Card title="By customer" pad={false} actions={<Button size="sm" variant="ghost" onClick={() => csv('by_customer')}>CSV</Button>}><Table rows={d.by_customer} cols={[['customer', 'Customer'], ['count', 'Payments'], ['amount', 'Amount', money]]} /></Card>
              <Card title="Allocation status" pad={false}><Table rows={d.allocation} cols={[['state', 'Invoice state', (v) => <Status state={v as string} />], ['invoices', 'Invoices'], ['invoiced', 'Invoiced', money], ['allocated', 'Payments allocated', money]]} /></Card>
            </div>
          </>}

          {tab === 'discounts' && <>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Stat label="Active rules" value={s.active} tone="text-ok" /><Stat label="Expired rules" value={s.expired} /><Stat label="Times applied" value={s.applications} /><Stat label="Total discounted" value={s.total_discounted} money />
            </div>
            <Card title="Utilisation" pad={false} actions={<Button size="sm" variant="ghost" onClick={() => csv('rules')}>CSV</Button>}>
              <Table rows={d.rules} cols={[['name', 'Rule'], ['type', 'Type', (v, r) => v === 'percentage' ? `${r.value}%` : inr(r.value as number)], ['status', 'Status', (v) => <Status state={v as string} />],
                ['used', 'Used'], ['max_usage', 'Limit', (v) => String(v ?? 'None')], ['remaining', 'Remaining', (v) => String(v ?? '∞')], ['total_discounted', 'Discounted', money]]} />
            </Card>
          </>}
          <p className="text-[12px] text-ink-soft">{titleCase(tab)} report · invoiced revenue counts confirmed and paid invoices by invoice date; collected revenue counts posted payments by payment date.</p>
        </div>
      )}
    </>
  )
}
