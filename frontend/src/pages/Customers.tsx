import { Building2, Mail, Phone, Plus, UserPlus, Users } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Button, Card, DemoTag, Empty, ErrorBox, Field, Modal, PageHeader, Pagination, Skeleton, Status, TableSkeleton, Tabs } from '../components/ui'
import { api } from '../lib/api'
import { fdate, inr, periodLabel } from '../lib/format'
import { useApi, useDebounced, useRunner, useUrlFilters } from '../lib/hooks'
import type { Customer, InvRow, Page, Payment, SubRow } from '../lib/types'

const blank = { name: '', email: '', phone: '', company: '', segment: 'small_business', address: '', gstin: '' }

export function CustomerForm({ open, onClose, initial, onSaved }: { open: boolean; onClose: () => void; initial?: Customer; onSaved?: (c: Customer) => void }) {
  const [f, setF] = useState(() => initial ? { ...blank, ...Object.fromEntries(Object.entries(initial).map(([k, v]) => [k, v ?? ''])) } as typeof blank : blank)
  const { run, busy } = useRunner()
  const save = async () => {
    const body = { ...f, phone: f.phone || null, company: f.company || null, address: f.address || null, gstin: f.gstin || null }
    const r = await run('save', () => initial ? api<Customer>(`/customers/${initial.id}`, { method: 'PATCH', body }) : api<Customer>('/customers', { body }), initial ? 'Customer updated' : 'Customer created')
    if (r) { onSaved?.(r); onClose() }
  }
  const s = (k: keyof typeof blank) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  return (
    <Modal open={open} onClose={onClose} title={initial ? 'Edit customer' : 'New customer'} footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy === 'save'} onClick={save} disabled={!f.name || !f.email}>Save</Button></>}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Contact name" className="sm:col-span-2"><input className="input" value={f.name} onChange={s('name')} /></Field>
        <Field label="Email" hint={initial ? 'Email is the customer\'s identity and cannot be changed' : 'They can register with this email to access the portal'}><input className="input" type="email" value={f.email} onChange={s('email')} disabled={!!initial} /></Field>
        <Field label="Phone"><input className="input" value={f.phone} onChange={s('phone')} /></Field>
        <Field label="Company"><input className="input" value={f.company} onChange={s('company')} /></Field>
        <Field label="Segment"><select className="input" value={f.segment} onChange={s('segment')}><option value="small_business">Small business</option><option value="enterprise">Enterprise</option></select></Field>
        <Field label="GSTIN"><input className="input" value={f.gstin} onChange={s('gstin')} /></Field>
        <Field label="Billing address" className="sm:col-span-2"><textarea className="input" rows={2} value={f.address} onChange={s('address')} /></Field>
      </div>
    </Modal>
  )
}

export default function Customers() {
  const [f, set] = useUrlFilters({ q: '', segment: '', page: '1' })
  const [q, setQ] = useState(f.q)
  const dq = useDebounced(q)
  const [open, setOpen] = useState(false)
  const nav = useNavigate()
  const params = { ...f, q: dq }
  const { data, isLoading, error, refetch } = useApi<Page<Customer>>('/customers', params)
  return (
    <>
      <PageHeader title="Customers" subtitle="Everyone Brightloop bills — small shops to enterprise accounts." actions={<Button variant="primary" icon={<UserPlus className="h-4 w-4" />} onClick={() => setOpen(true)}>New customer</Button>} />
      <Card pad={false}>
        <div className="flex flex-wrap gap-2 border-b border-line p-3">
          <input className="input max-w-xs" placeholder="Search name, email or company" value={q} onChange={(e) => { setQ(e.target.value); set({ q: e.target.value }) }} />
          <select className="input w-44" value={f.segment} onChange={(e) => set({ segment: e.target.value })}><option value="">All segments</option><option value="small_business">Small business</option><option value="enterprise">Enterprise</option></select>
        </div>
        {error ? <div className="p-4"><ErrorBox error={error} onRetry={refetch} /></div> : isLoading ? <TableSkeleton /> : !data?.items.length ? (
          <Empty icon={<Users className="h-5 w-5" />} title="No customers found" body={dq ? 'Try a different search.' : 'Add your first customer or let them register.'} />
        ) : (
          <div className="overflow-x-auto"><table className="w-full min-w-[720px]">
            <thead><tr><th className="th">Customer</th><th className="th">Company</th><th className="th">Segment</th><th className="th">Portal</th><th className="th text-right">Active subs</th><th className="th text-right">Outstanding</th></tr></thead>
            <tbody>{data.items.map((c) => (
              <tr key={c.id} className="cursor-pointer hover:bg-canvas" onClick={() => nav(`/customers/${c.id}`)}>
                <td className="td"><span className="font-semibold">{c.name}</span>{c.is_demo && <DemoTag />}<span className="block text-[12px] text-ink-soft">{c.email}</span></td>
                <td className="td">{c.company ?? '—'}</td>
                <td className="td"><Status state={c.segment === 'enterprise' ? 'confirmed' : 'draft'} label={c.segment === 'enterprise' ? 'Enterprise' : 'Small business'} /></td>
                <td className="td text-[12px]">{c.user_id ? <span className="text-ok">Registered</span> : <span className="text-ink-faint">Not registered</span>}</td>
                <td className="td text-right num">{c.active_subscriptions}</td>
                <td className={`td text-right num ${Number(c.outstanding) > 0 ? 'font-semibold text-warn' : ''}`}>{inr(c.outstanding)}</td>
              </tr>))}</tbody></table></div>
        )}
        {data && <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={(p) => set({ page: String(p) })} />}
      </Card>
      {open && <CustomerForm open onClose={() => setOpen(false)} onSaved={(c) => nav(`/customers/${c.id}`)} />}
    </>
  )
}

export function CustomerDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const [tab, setTab] = useState<'subs' | 'invoices' | 'payments'>('subs')
  const [edit, setEdit] = useState(false)
  const { data: c, error } = useApi<Customer>(`/customers/${id}`)
  const { data: subs } = useApi<Page<SubRow>>('/subscriptions', { customer_id: id, page_size: 100 })
  const { data: invs } = useApi<Page<InvRow>>('/invoices', { customer_id: id, page_size: 100 })
  const { data: pays } = useApi<Page<Payment>>('/payments', { customer_id: id, page_size: 100 })
  if (error) return <ErrorBox error={error} />
  if (!c) return <Skeleton className="h-64" />
  const due = invs?.items.filter((i) => i.state === 'confirmed').reduce((s, i) => s + Number(i.amount_due), 0) ?? 0
  return (
    <>
      <PageHeader crumbs={[{ label: 'Customers', to: '/customers' }, { label: c.name }]} title={<>{c.name}{c.is_demo && <DemoTag />}</>}
        subtitle={c.company} actions={<><Button onClick={() => setEdit(true)}>Edit</Button><Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => nav(`/quotations/new?customer_id=${c.id}`)}>New quotation</Button></>} />
      <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
        <Card title="Profile">
          <dl className="space-y-3 text-[13px]">
            <div className="flex gap-2"><Mail className="h-4 w-4 text-ink-faint" />{c.email}</div>
            <div className="flex gap-2"><Phone className="h-4 w-4 text-ink-faint" />{c.phone ?? '—'}</div>
            <div className="flex gap-2"><Building2 className="h-4 w-4 text-ink-faint" /><span className="whitespace-pre-line">{c.address ?? '—'}</span></div>
            <div><span className="label">GSTIN</span>{c.gstin ?? '—'}</div>
            <div><span className="label">Segment</span>{c.segment === 'enterprise' ? 'Enterprise' : 'Small business'}</div>
            <div><span className="label">Portal access</span>{c.user_id ? 'Registered' : 'Not registered yet'}</div>
            <div><span className="label">Customer since</span>{fdate(c.created_at)}</div>
            <div className="rounded-lg bg-canvas p-3"><span className="label">Outstanding</span><span className="num text-[18px] font-bold">{inr(due)}</span></div>
          </dl>
        </Card>
        <Card pad={false}>
          <div className="px-4"><Tabs value={tab} onChange={setTab} tabs={[{ id: 'subs', label: 'Subscriptions', count: subs?.total }, { id: 'invoices', label: 'Invoices', count: invs?.total }, { id: 'payments', label: 'Payments', count: pays?.total }]} /></div>
          <div className="overflow-x-auto">
            {tab === 'subs' && (subs?.items.length ? <table className="w-full min-w-[600px]"><thead><tr><th className="th">Number</th><th className="th">Plan</th><th className="th">Status</th><th className="th">Start</th><th className="th">Expiry</th><th className="th text-right">Per period</th></tr></thead>
              <tbody>{subs.items.map((s) => <tr key={s.id} className="cursor-pointer hover:bg-canvas" onClick={() => nav(`/subscriptions/${s.id}`)}><td className="td font-semibold">{s.number}</td><td className="td">{s.plan_name}<span className="block text-[12px] text-ink-soft">{periodLabel[s.billing_period]}</span></td><td className="td"><Status state={s.state} /></td><td className="td">{fdate(s.start_date)}</td><td className="td">{fdate(s.end_date)}</td><td className="td text-right num">{inr(s.total)}</td></tr>)}</tbody></table>
              : <Empty title="No subscriptions yet" action={<Link className="link" to={`/quotations/new?customer_id=${c.id}`}>Create a quotation</Link>} />)}
            {tab === 'invoices' && (invs?.items.length ? <table className="w-full min-w-[600px]"><thead><tr><th className="th">Invoice</th><th className="th">Date</th><th className="th">Due</th><th className="th">Status</th><th className="th text-right">Total</th><th className="th text-right">Due</th></tr></thead>
              <tbody>{invs.items.map((i) => <tr key={i.id} className="cursor-pointer hover:bg-canvas" onClick={() => nav(`/invoices/${i.id}`)}><td className="td font-semibold">{i.number}</td><td className="td">{fdate(i.invoice_date)}</td><td className="td">{fdate(i.due_date)}</td><td className="td"><Status state={i.is_overdue ? 'overdue' : i.state} /></td><td className="td text-right num">{inr(i.total)}</td><td className="td text-right num">{inr(i.amount_due)}</td></tr>)}</tbody></table>
              : <Empty title="No invoices yet" />)}
            {tab === 'payments' && (pays?.items.length ? <table className="w-full min-w-[600px]"><thead><tr><th className="th">Reference</th><th className="th">Date</th><th className="th">Invoice</th><th className="th">Method</th><th className="th">Status</th><th className="th text-right">Amount</th></tr></thead>
              <tbody>{pays.items.map((p) => <tr key={p.id}><td className="td font-mono text-[12px]">{p.reference}</td><td className="td">{fdate(p.payment_date)}</td><td className="td"><Link className="link" to={`/invoices/${p.invoice_id}`}>{p.invoice_number}</Link></td><td className="td">{p.method.replace('_', ' ')}</td><td className="td"><Status state={p.status} /></td><td className="td text-right num">{inr(p.amount)}</td></tr>)}</tbody></table>
              : <Empty title="No payments yet" />)}
          </div>
        </Card>
      </div>
      {edit && <CustomerForm open initial={c} onClose={() => setEdit(false)} />}
    </>
  )
}
