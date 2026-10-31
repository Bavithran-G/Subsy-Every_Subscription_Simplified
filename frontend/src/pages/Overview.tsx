import {
  AlertTriangle, ArrowRight, BadgeIndianRupee, CalendarClock, FileClock, FileText, Hourglass, Play, Receipt, Repeat,
  TrendingUp, Users, Wallet,
} from 'lucide-react'
import { useNavigate, Link } from 'react-router-dom'
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { C, ChartTip, axis, moneyTick, stateColor } from '../components/charts'
import { Button, Card, ErrorBox, Kpi, PageHeader, Skeleton } from '../components/ui'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { ago, fdate, inr, inrCompact, monthLabel, titleCase } from '../lib/format'
import { useApi, useRunner, useUrlFilters } from '../lib/hooks'
import type { Msg, Plan } from '../lib/types'

export interface Dashboard {
  range: { from: string; to: string }
  kpis: Record<string, number>
  monthly: { month: string; invoiced: number; collected: number; new_subscriptions: number; active_subscriptions: number }[]
  subscription_status: { state: string; count: number }[]
  invoice_status: { state: string; count: number }[]
  aging: { bucket: string; count: number; amount: number }[]
  renewals: { label: string; count: number; view: string | null }[]
  billing_activity: { date: string; invoiced: number; failed: number; pending: number }[]
  top_overdue: { id: number; number: string; customer: string; due_date: string; days_overdue: number; amount_due: number }[]
  recent_activity: { id: number; action: string; entity: string; entity_id: number; user: string; at: string }[]
}

export function DashFilters({ f, set }: { f: Record<string, string>; set: (p: Record<string, string>) => void }) {
  const { data: plans } = useApi<Plan[]>('/plans')
  return (
    <div className="flex flex-wrap items-end gap-2">
      <label><span className="label">From</span><input type="date" className="input h-8 w-[150px]" value={f.date_from} onChange={(e) => set({ date_from: e.target.value })} /></label>
      <label><span className="label">To</span><input type="date" className="input h-8 w-[150px]" value={f.date_to} onChange={(e) => set({ date_to: e.target.value })} /></label>
      <label><span className="label">Plan</span>
        <select className="input h-8 w-[180px]" value={f.plan_id} onChange={(e) => set({ plan_id: e.target.value })}>
          <option value="">All plans</option>{plans?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select></label>
      {(f.date_from || f.date_to || f.plan_id) && <Button size="sm" variant="ghost" onClick={() => set({ date_from: '', date_to: '', plan_id: '' })}>Reset</Button>}
    </div>
  )
}

export default function Overview() {
  const { user } = useAuth()
  const nav = useNavigate()
  const [f, set] = useUrlFilters({ date_from: '', date_to: '', plan_id: '' })
  const { data: d, isLoading, error, refetch } = useApi<Dashboard>('/reports/dashboard', f)
  const { run, busy } = useRunner()
  const k = d?.kpis
  const planQ = f.plan_id ? `&plan_id=${f.plan_id}` : ''

  return (
    <>
      <PageHeader title={`Good ${new Date().getHours() < 12 ? 'morning' : new Date().getHours() < 17 ? 'afternoon' : 'evening'}, ${user?.full_name.split(' ')[0]}`}
        subtitle={d ? <>Brightloop's subscription business · {fdate(d.range.from)} – {fdate(d.range.to)}</> : 'Loading your business overview…'}
        actions={<>
          <DashFilters f={f} set={set} />
          <Button variant="primary" icon={<Play className="h-4 w-4" />} loading={busy === 'bill'}
            onClick={() => run('bill', () => api<Msg>('/billing/run', { method: 'POST' }), (r) => r.message)}>Run billing now</Button>
        </>} />
      {error && <ErrorBox error={error} onRetry={refetch} />}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {isLoading || !k ? Array.from({ length: 12 }).map((_, i) => <Skeleton key={i} className="h-[104px] rounded-xl" />) : <>
          <Kpi label="MRR" value={k.mrr} format={inrCompact} sub="Active subs, monthly-normalised" icon={<TrendingUp className="h-4 w-4" />} to={`/subscriptions?state=active${planQ}`} />
          <Kpi label="Collected" value={k.revenue_collected} format={inrCompact} sub="Payments received in range" tone="good" icon={<Wallet className="h-4 w-4" />} to="/payments" />
          <Kpi label="Invoiced" value={k.revenue_invoiced} format={inrCompact} sub="Confirmed + paid in range" icon={<BadgeIndianRupee className="h-4 w-4" />} to="/invoices?state=confirmed,paid" />
          <Kpi label="Outstanding" value={k.outstanding_amount} format={inrCompact} sub={`${k.outstanding_invoices} open invoices`} tone="warn" icon={<Hourglass className="h-4 w-4" />} to="/invoices?outstanding=true" />
          <Kpi label="Overdue" value={k.overdue_amount} format={inrCompact} sub={`${k.overdue_invoices} invoices past due`} tone="bad" icon={<AlertTriangle className="h-4 w-4" />} to="/invoices?overdue=true" />
          <Kpi label="Customers" value={k.total_customers} icon={<Users className="h-4 w-4" />} to="/customers" />
          <Kpi label="Active subs" value={k.active_subscriptions} sub={`${k.total_subscriptions} total · ${k.paused_subscriptions} paused`} tone="good" icon={<Repeat className="h-4 w-4" />} to={`/subscriptions?state=active${planQ}`} />
          <Kpi label="Awaiting confirm" value={k.awaiting_confirmation + k.draft_subscriptions} sub={`${k.draft_subscriptions} draft · ${k.awaiting_confirmation} sent`} icon={<FileClock className="h-4 w-4" />} to="/quotations" />
          <Kpi label="Renewals · 30d" value={k.upcoming_renewals} sub={`${k.expiring_subscriptions} expiring in 7 days`} tone="warn" icon={<CalendarClock className="h-4 w-4" />} to="/subscriptions?view=renewals" />
          <Kpi label="Closed subs" value={k.closed_subscriptions} icon={<Repeat className="h-4 w-4" />} to="/subscriptions?state=closed" />
          <Kpi label="Invoices" value={k.total_invoices} sub={`${k.paid_invoices} paid · ${k.confirmed_invoices} confirmed · ${k.draft_invoices} draft`} icon={<Receipt className="h-4 w-4" />} to="/invoices" />
          <Kpi label="Discounts given" value={k.discount_amount} format={inrCompact} sub={`${k.discount_applications} applications`} icon={<FileText className="h-4 w-4" />} to="/discounts" />
        </>}
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-3">
        <Card title="Revenue: invoiced vs collected" className="xl:col-span-2" actions={<Link to="/reports?tab=revenue" className="link text-[13px]">Revenue report</Link>}>
          {d ? (
            <div className="h-[280px]">
              <ResponsiveContainer>
                <ComposedChart data={d.monthly} margin={{ left: 4, right: 8, top: 8 }} onClick={(e) => {
                  const m = (e as { activeLabel?: string })?.activeLabel; if (m) { const [y, mo] = m.split('-'); nav(`/invoices?date_from=${m}-01&date_to=${y}-${mo}-${new Date(+y, +mo, 0).getDate()}`) }
                }}>
                  <CartesianGrid vertical={false} stroke={C.line} />
                  <XAxis dataKey="month" tickFormatter={monthLabel} {...axis} />
                  <YAxis tickFormatter={moneyTick} {...axis} width={56} />
                  <Tooltip content={<ChartTip labelFmt={monthLabel} />} cursor={{ fill: '#FDECEC', opacity: 0.6 }} />
                  <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="invoiced" name="Invoiced" fill={C.brand} radius={[4, 4, 0, 0]} maxBarSize={28} className="cursor-pointer" animationDuration={500} />
                  <Line dataKey="collected" name="Collected" stroke={C.ok} strokeWidth={2.5} dot={{ r: 3 }} animationDuration={500} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          ) : <Skeleton className="h-[280px]" />}
        </Card>
        <Card title="Outstanding vs collected">
          {k ? (() => {
            const total = k.revenue_collected + k.outstanding_amount || 1
            const rows = [
              { label: 'Collected (in range)', v: k.revenue_collected, c: C.ok, to: '/payments' },
              { label: 'Outstanding, not yet due', v: k.outstanding_amount - k.overdue_amount, c: C.warn, to: '/invoices?outstanding=true' },
              { label: 'Overdue', v: k.overdue_amount, c: C.brand, to: '/invoices?overdue=true' },
            ]
            return (
              <div>
                <div className="flex h-3 overflow-hidden rounded-full bg-gray-100">{rows.map((r) => <div key={r.label} style={{ width: `${(r.v / total) * 100}%`, background: r.c }} className="transition-all duration-700" />)}</div>
                <div className="mt-4 space-y-3">{rows.map((r) => (
                  <Link key={r.label} to={r.to} className="flex items-center gap-3 rounded-lg p-2 hover:bg-canvas">
                    <span className="h-2.5 w-2.5 rounded-full" style={{ background: r.c }} /><span className="flex-1 text-ink-soft">{r.label}</span><span className="num font-semibold">{inr(r.v)}</span>
                  </Link>
                ))}</div>
                <p className="mt-3 border-t border-line pt-3 text-[12px] text-ink-soft">Collected money and invoiced-but-unpaid money are tracked separately — outstanding invoices are never counted as revenue received.</p>
              </div>
            )
          })() : <Skeleton className="h-40" />}
        </Card>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2 xl:grid-cols-3">
        <Card title="Active subscriptions">
          {d ? <div className="h-[220px]"><ResponsiveContainer>
            <AreaChart data={d.monthly} margin={{ left: -16, right: 8, top: 8 }}>
              <defs><linearGradient id="g1" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor={C.brand} stopOpacity={0.25} /><stop offset="1" stopColor={C.brand} stopOpacity={0} /></linearGradient></defs>
              <CartesianGrid vertical={false} stroke={C.line} /><XAxis dataKey="month" tickFormatter={monthLabel} {...axis} /><YAxis allowDecimals={false} {...axis} />
              <Tooltip content={<ChartTip money={false} labelFmt={monthLabel} />} />
              <Area dataKey="active_subscriptions" name="Active at month end" stroke={C.brand} strokeWidth={2} fill="url(#g1)" />
              <Bar dataKey="new_subscriptions" name="New" fill={C.brandDark} />
            </AreaChart></ResponsiveContainer></div> : <Skeleton className="h-[220px]" />}
        </Card>
        <Card title="Subscription status">
          {d ? <div className="h-[220px]"><ResponsiveContainer>
            <BarChart data={d.subscription_status} layout="vertical" margin={{ left: 8, right: 16 }}>
              <XAxis type="number" hide /><YAxis type="category" dataKey="state" tickFormatter={titleCase} {...axis} width={80} />
              <Tooltip content={<ChartTip money={false} labelFmt={titleCase} />} cursor={{ fill: '#F8F9FB' }} />
              <Bar dataKey="count" name="Subscriptions" radius={[0, 4, 4, 0]} className="cursor-pointer" onClick={(e) => {
                const s = (e as unknown as { state: string }).state; nav(s === 'draft' || s === 'quotation' ? `/quotations?state=${s}` : `/subscriptions?state=${s}`)
              }}>{d.subscription_status.map((s) => <Cell key={s.state} fill={stateColor[s.state] ?? C.grey} />)}</Bar>
            </BarChart></ResponsiveContainer></div> : <Skeleton className="h-[220px]" />}
        </Card>
        <Card title="Invoice status">
          {d ? <div className="h-[220px]"><ResponsiveContainer>
            <BarChart data={d.invoice_status} layout="vertical" margin={{ left: 8, right: 16 }}>
              <XAxis type="number" hide /><YAxis type="category" dataKey="state" tickFormatter={titleCase} {...axis} width={80} />
              <Tooltip content={<ChartTip money={false} labelFmt={titleCase} />} cursor={{ fill: '#F8F9FB' }} />
              <Bar dataKey="count" name="Invoices" radius={[0, 4, 4, 0]} className="cursor-pointer" onClick={(e) => nav(`/invoices?state=${(e as unknown as { state: string }).state}`)}>
                {d.invoice_status.map((s) => <Cell key={s.state} fill={stateColor[s.state] ?? C.grey} />)}
              </Bar>
            </BarChart></ResponsiveContainer></div> : <Skeleton className="h-[220px]" />}
        </Card>
        <Card title="Overdue & aging" actions={<Link to="/invoices?overdue=true" className="link text-[13px]">All overdue</Link>}>
          {d ? <div className="h-[200px]"><ResponsiveContainer>
            <BarChart data={d.aging} margin={{ left: -8, right: 8, top: 8 }}>
              <CartesianGrid vertical={false} stroke={C.line} /><XAxis dataKey="bucket" {...axis} interval={0} tickFormatter={(v: string) => v.replace('Not yet due', 'Current').replace(' days', 'd')} /><YAxis tickFormatter={moneyTick} {...axis} />
              <Tooltip content={<ChartTip />} cursor={{ fill: '#FDECEC', opacity: 0.5 }} />
              <Bar dataKey="amount" name="Amount due" radius={[4, 4, 0, 0]} className="cursor-pointer" onClick={(e) => nav((e as unknown as { bucket: string }).bucket === 'Not yet due' ? '/invoices?outstanding=true' : '/invoices?overdue=true')}>
                {d.aging.map((a, i) => <Cell key={a.bucket} fill={i === 0 ? C.warn : [C.brandSoft, C.brand, C.brandDark, '#5E1212'][i - 1]} />)}
              </Bar>
            </BarChart></ResponsiveContainer></div> : <Skeleton className="h-[200px]" />}
        </Card>
        <Card title="Renewals">
          {d ? <div className="divide-y divide-line">{d.renewals.map((r) => {
            const row = <><span className="flex-1 text-ink-soft">{r.label}</span><span className="num font-bold">{r.count}</span>{r.view && <ArrowRight className="h-4 w-4 text-ink-faint" />}</>
            return r.view ? <Link key={r.label} to={`/subscriptions?view=${r.view}`} className="flex items-center gap-3 py-2.5 hover:text-brand-700">{row}</Link> : <div key={r.label} className="flex items-center gap-3 py-2.5">{row}</div>
          })}</div> : <Skeleton className="h-40" />}
        </Card>
        <Card title="Billing activity · 30 days" actions={<Link to="/invoices?tab=billing" className="link text-[13px]">Billing log</Link>}>
          {d ? <div className="h-[200px]"><ResponsiveContainer>
            <BarChart data={d.billing_activity} margin={{ left: -24, right: 4, top: 8 }}>
              <XAxis dataKey="date" tickFormatter={(v) => v.slice(8)} {...axis} interval={4} /><YAxis allowDecimals={false} {...axis} />
              <Tooltip content={<ChartTip money={false} labelFmt={fdate} />} cursor={{ fill: '#F8F9FB' }} />
              <Bar dataKey="invoiced" name="Invoiced" stackId="a" fill={C.ok} /><Bar dataKey="failed" name="Failed" stackId="a" fill={C.brand} /><Bar dataKey="pending" name="Pending" stackId="a" fill={C.warn} radius={[3, 3, 0, 0]} />
            </BarChart></ResponsiveContainer></div> : <Skeleton className="h-[200px]" />}
        </Card>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Card title="Chase these first" pad={false}>
          {d && !d.top_overdue.length && <p className="p-5 text-ink-soft">No overdue invoices right now.</p>}
          <table className="w-full"><tbody>{d?.top_overdue.map((i) => (
            <tr key={i.id} className="cursor-pointer hover:bg-canvas" onClick={() => nav(`/invoices/${i.id}`)}>
              <td className="td"><span className="font-semibold">{i.number}</span><span className="block text-[12px] text-ink-soft">{i.customer}</span></td>
              <td className="td text-[12px] text-bad">{i.days_overdue} days late</td>
              <td className="td text-right num font-semibold">{inr(i.amount_due)}</td>
            </tr>))}</tbody></table>
        </Card>
        <Card title="Recent activity" pad={false}>
          <ul className="divide-y divide-line">{d?.recent_activity.map((a) => (
            <li key={a.id} className="flex items-center gap-3 px-5 py-2.5 text-[13px]">
              <span className="h-1.5 w-1.5 rounded-full bg-brand-400" />
              <span className="flex-1"><b>{a.user}</b> <span className="text-ink-soft">{a.action.replace('.', ' · ').replace(/_/g, ' ')}</span> {a.entity} #{a.entity_id}</span>
              <span className="text-[12px] text-ink-faint">{ago(a.at)}</span>
            </li>))}</ul>
        </Card>
      </div>
    </>
  )
}
