import { AlertTriangle, CalendarClock, CreditCard, Receipt, Repeat, Wallet } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button, Card, Empty, Field, Kpi, PageHeader, Pagination, Skeleton, Status, TableSkeleton } from '../components/ui'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { fdate, inr, inrCompact, methodLabel, periodLabel } from '../lib/format'
import { useApi, useRunner } from '../lib/hooks'
import type { Customer, InvRow, Page, Payment, SubRow } from '../lib/types'

interface Summary { customer: { name: string; company: string | null }; active_subscriptions: number; paused_subscriptions: number; pending_quotations: number; open_invoices: number; outstanding: number; overdue_invoices: number; total_paid: number; next_renewal: { number: string; end_date: string } | null }

function SubCards({ subs }: { subs: SubRow[] }) {
  const nav = useNavigate()
  if (!subs.length) return <Card><Empty icon={<Repeat className="h-5 w-5" />} title="No subscriptions yet" body="When Brightloop sends you a quotation or activates a plan, it appears here." /></Card>
  return (
    <div className="grid gap-4 md:grid-cols-2">{subs.map((s) => (
      <button key={s.id} onClick={() => nav(`/portal/subscriptions/${s.id}`)} className="card p-5 text-left transition hover:-translate-y-px hover:shadow-pop">
        <div className="flex items-start justify-between"><div><p className="font-display text-[16px] font-bold">{s.plan_name}</p><p className="text-[12px] text-ink-soft">{s.number} · {periodLabel[s.billing_period]}</p></div><Status state={s.state} /></div>
        <p className="mt-3 font-display text-[22px] font-bold">{inr(s.total)}<span className="ml-1 text-[12px] font-normal text-ink-soft">per {s.billing_period.replace('ly', '').replace('dai', 'day')} incl. tax</span></p>
        <div className="mt-3 grid grid-cols-3 gap-2 border-t border-line pt-3 text-[12px]">
          <div><p className="text-ink-faint">Started</p><p>{fdate(s.start_date)}</p></div>
          <div><p className="text-ink-faint">Renews / expires</p><p>{fdate(s.end_date)}</p></div>
          <div><p className="text-ink-faint">Next invoice</p><p>{s.state === 'active' ? fdate(s.next_invoice_date) : '—'}</p></div>
        </div>
      </button>))}</div>
  )
}

export function PortalHome() {
  const { user } = useAuth()
  const { data: s } = useApi<Summary>('/portal/summary')
  const { data: subs } = useApi<SubRow[]>('/portal/subscriptions')
  const { data: invs } = useApi<Page<InvRow>>('/portal/invoices', { page_size: 5 })
  return (
    <>
      <PageHeader title={`Hello, ${user?.full_name.split(' ')[0]}`} subtitle={s?.customer.company ?? 'Your Brightloop subscriptions and billing'} />
      {s && s.overdue_invoices > 0 && <div className="mb-5 flex items-center gap-3 rounded-xl border border-brand-200 bg-brand-50 px-4 py-3 text-brand-900"><AlertTriangle className="h-5 w-5" /><p>You have <b>{s.overdue_invoices} overdue invoice{s.overdue_invoices > 1 ? 's' : ''}</b>. <Link className="link" to="/portal/invoices">View invoices</Link></p></div>}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {!s ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-[104px] rounded-xl" />) : <>
          <Kpi label="Active subscriptions" value={s.active_subscriptions} sub={s.paused_subscriptions ? `${s.paused_subscriptions} paused` : undefined} tone="good" icon={<Repeat className="h-4 w-4" />} to="/portal/subscriptions" />
          <Kpi label="Outstanding" value={s.outstanding} format={inrCompact} sub={`${s.open_invoices} open invoice(s)`} tone={s.overdue_invoices ? 'bad' : 'warn'} icon={<Receipt className="h-4 w-4" />} to="/portal/invoices" />
          <Kpi label="Paid to date" value={s.total_paid} format={inrCompact} icon={<Wallet className="h-4 w-4" />} to="/portal/payments" />
          <div className="card p-4"><p className="flex items-center justify-between text-[12px] font-semibold uppercase tracking-wide text-ink-soft">Next renewal<CalendarClock className="h-4 w-4 text-brand-600" /></p>
            {s.next_renewal ? <><p className="mt-2 font-display text-[20px] font-bold">{fdate(s.next_renewal.end_date)}</p><p className="text-[12px] text-ink-soft">{s.next_renewal.number}</p></> : <p className="mt-2 text-ink-soft">No upcoming expiry</p>}</div>
        </>}
      </div>
      <h2 className="mb-3 mt-8 text-[16px] font-bold">Your subscriptions</h2>
      {subs ? <SubCards subs={subs.filter((x) => x.state !== 'closed')} /> : <Skeleton className="h-40" />}
      <Card title="Recent invoices" className="mt-8" pad={false} actions={<Link to="/portal/invoices" className="link text-[13px]">All invoices</Link>}>
        <InvoiceTable rows={invs?.items} />
      </Card>
    </>
  )
}

function InvoiceTable({ rows }: { rows?: InvRow[] }) {
  const nav = useNavigate()
  if (!rows) return <TableSkeleton rows={3} />
  if (!rows.length) return <Empty icon={<Receipt className="h-5 w-5" />} title="No invoices yet" />
  return (
    <div className="overflow-x-auto"><table className="w-full min-w-[560px]">
      <thead><tr><th className="th">Invoice</th><th className="th">Period</th><th className="th">Due</th><th className="th">Status</th><th className="th text-right">Total</th><th className="th text-right">To pay</th></tr></thead>
      <tbody>{rows.map((i) => (
        <tr key={i.id} className="cursor-pointer hover:bg-canvas" onClick={() => nav(`/portal/invoices/${i.id}`)}>
          <td className="td font-semibold">{i.number}<span className="block text-[12px] font-normal text-ink-soft">{i.subscription_number}</span></td>
          <td className="td text-[13px]">{fdate(i.period_start)} – {fdate(i.period_end)}</td><td className={`td ${i.is_overdue ? 'font-semibold text-bad' : ''}`}>{fdate(i.due_date)}</td>
          <td className="td"><Status state={i.is_overdue ? 'overdue' : i.state} /></td><td className="td text-right num">{inr(i.total)}</td><td className="td text-right num font-semibold">{inr(i.amount_due)}</td>
        </tr>))}</tbody></table></div>
  )
}

export function PortalSubscriptions() {
  const { data } = useApi<SubRow[]>('/portal/subscriptions')
  return (
    <>
      <PageHeader title="My subscriptions" subtitle="Plans, renewal dates and what you can change yourself." />
      {data ? <SubCards subs={data} /> : <Skeleton className="h-60" />}
    </>
  )
}

export function PortalInvoices() {
  const [page, setPage] = useState(1)
  const { data } = useApi<Page<InvRow>>('/portal/invoices', { page })
  return (
    <>
      <PageHeader title="Invoices" subtitle="Download any invoice as PDF. Payments you make are recorded by our team." />
      <Card pad={false}><InvoiceTable rows={data?.items} />{data && <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} />}</Card>
    </>
  )
}

export function PortalPayments() {
  const { data } = useApi<Payment[]>('/portal/payments')
  return (
    <>
      <PageHeader title="Payment history" subtitle="Every payment received against your invoices." />
      <Card pad={false}>
        {!data ? <TableSkeleton /> : !data.length ? <Empty icon={<CreditCard className="h-5 w-5" />} title="No payments yet" /> : (
          <div className="overflow-x-auto"><table className="w-full min-w-[560px]"><thead><tr><th className="th">Date</th><th className="th">Reference</th><th className="th">Invoice</th><th className="th">Method</th><th className="th">Status</th><th className="th text-right">Amount</th></tr></thead>
            <tbody>{data.map((p) => <tr key={p.id}><td className="td">{fdate(p.payment_date)}</td><td className="td font-mono text-[12px]">{p.reference}</td><td className="td"><Link className="link" to={`/portal/invoices/${p.invoice_id}`}>{p.invoice_number}</Link></td><td className="td">{methodLabel[p.method]}</td><td className="td"><Status state={p.status} /></td><td className="td text-right num font-semibold">{inr(p.amount)}</td></tr>)}</tbody></table></div>
        )}
      </Card>
    </>
  )
}

export function PortalProfile() {
  const { data } = useApi<Customer>('/portal/profile')
  const [f, setF] = useState<Partial<Customer> | null>(null)
  const { run, busy } = useRunner()
  const v = f ?? data
  if (!v) return <Skeleton className="h-60" />
  const s = (k: keyof Customer) => (e: { target: { value: string } }) => setF({ ...v, [k]: e.target.value })
  return (
    <>
      <PageHeader title="Profile" subtitle="Your billing details appear on every invoice." />
      <Card className="max-w-2xl">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Name"><input className="input" value={v.name ?? ''} onChange={s('name')} /></Field>
          <Field label="Email" hint="Contact Brightloop to change your login email"><input className="input" value={v.email ?? ''} disabled /></Field>
          <Field label="Company"><input className="input" value={v.company ?? ''} onChange={s('company')} /></Field>
          <Field label="Phone"><input className="input" value={v.phone ?? ''} onChange={s('phone')} /></Field>
          <Field label="GSTIN"><input className="input" value={v.gstin ?? ''} onChange={s('gstin')} /></Field>
          <Field label="Billing address" className="sm:col-span-2"><textarea className="input" rows={3} value={v.address ?? ''} onChange={s('address')} /></Field>
        </div>
        <Button className="mt-5" variant="primary" disabled={!f} loading={busy === 'p'} onClick={async () => { if (await run('p', () => api('/portal/profile', { method: 'PATCH', body: { name: v.name, company: v.company || null, phone: v.phone || null, gstin: v.gstin || null, address: v.address || null } }), 'Profile saved')) setF(null) }}>Save changes</Button>
      </Card>
    </>
  )
}
