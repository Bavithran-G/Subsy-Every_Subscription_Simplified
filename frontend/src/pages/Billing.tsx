import { clsx } from 'clsx'
import { AlertTriangle, CheckCircle2, CreditCard, Download, Mail, Percent, Play, Plus, Printer, Receipt, RotateCcw, XCircle } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Wordmark } from '../components/Logo'
import { Badge, Button, Card, DemoTag, Empty, ErrorBox, Field, Modal, PageHeader, Pagination, Skeleton, Status, TableSkeleton, Tabs, Toggle, useUi } from '../components/ui'
import { api, download } from '../lib/api'
import { useAuth } from '../lib/auth'
import { fdate, fdatetime, inr, methodLabel, titleCase, todayISO } from '../lib/format'
import { useApi, useDebounced, useRunner, useUrlFilters } from '../lib/hooks'
import type { BillingEvent, Discount, Invoice, InvRow, Msg, Page, Payment, Product, SubRow } from '../lib/types'

/* ======================= Invoices ======================= */
export function Invoices() {
  const nav = useNavigate()
  const [f, set] = useUrlFilters({ q: '', state: '', overdue: '', outstanding: '', customer_id: '', subscription_id: '', date_from: '', date_to: '', page: '1', tab: 'list' })
  const [q, setQ] = useState(f.q)
  const dq = useDebounced(q)
  const { data, isLoading, error, refetch } = useApi<Page<InvRow>>(f.tab === 'list' ? '/invoices' : null, { ...f, q: dq, tab: undefined })
  const { run, busy } = useRunner()
  const chip = (label: string, active: boolean, patch: Record<string, string>, red = false) => (
    <button onClick={() => set({ state: '', overdue: '', outstanding: '', ...patch })} className={clsx('rounded-full px-3 py-1 text-[12px] font-semibold', active ? (red ? 'bg-bad text-white' : 'bg-brand-600 text-white') : red ? 'bg-bad-soft text-bad' : 'bg-canvas text-ink-soft hover:bg-gray-100')}>{label}</button>
  )
  const none = !f.state && !f.overdue && !f.outstanding
  return (
    <>
      <PageHeader title="Invoices" subtitle="Generated from subscriptions by the billing engine — Draft → Confirmed → Paid."
        actions={<Button variant="primary" icon={<Play className="h-4 w-4" />} loading={busy === 'bill'} onClick={() => run('bill', () => api<Msg>('/billing/run', { method: 'POST' }), (r) => r.message)}>Run billing now</Button>} />
      <div className="mb-4"><Tabs value={f.tab as 'list' | 'billing'} onChange={(t) => set({ tab: t })} tabs={[{ id: 'list', label: 'Invoices' }, { id: 'billing', label: 'Billing log' }]} /></div>
      {f.tab === 'billing' ? <BillingLog /> : (
        <Card pad={false}>
          <div className="flex flex-wrap items-center gap-2 border-b border-line p-3">
            <input className="input max-w-[240px]" placeholder="Invoice number or customer" value={q} onChange={(e) => { setQ(e.target.value); set({ q: e.target.value }) }} />
            <div className="flex flex-wrap gap-1">
              {chip('All', none, {})}{chip('Draft', f.state === 'draft', { state: 'draft' })}{chip('Confirmed', f.state === 'confirmed', { state: 'confirmed' })}
              {chip('Outstanding', !!f.outstanding, { outstanding: 'true' })}{chip('Paid', f.state === 'paid', { state: 'paid' })}{chip('Cancelled', f.state === 'cancelled', { state: 'cancelled' })}
              {chip('Overdue', !!f.overdue, { overdue: 'true' }, true)}
            </div>
            <div className="ml-auto flex items-center gap-2 text-[12px]">
              <input type="date" className="input h-8 w-[140px]" value={f.date_from} onChange={(e) => set({ date_from: e.target.value })} aria-label="From" />–
              <input type="date" className="input h-8 w-[140px]" value={f.date_to} onChange={(e) => set({ date_to: e.target.value })} aria-label="To" />
            </div>
          </div>
          {(f.customer_id || f.subscription_id) && <div className="flex items-center gap-2 border-b border-line bg-brand-50/50 px-4 py-2 text-[12px]">Filtered by {f.subscription_id ? `subscription #${f.subscription_id}` : `customer #${f.customer_id}`}<button className="link" onClick={() => set({ customer_id: '', subscription_id: '' })}>Clear</button></div>}
          {error ? <div className="p-4"><ErrorBox error={error} onRetry={refetch} /></div> : isLoading ? <TableSkeleton /> : !data?.items.length ? <Empty icon={<Receipt className="h-5 w-5" />} title="No invoices match" body="Invoices appear when active subscriptions reach a billing date." /> : (
            <div className="overflow-x-auto"><table className="w-full min-w-[880px]">
              <thead><tr><th className="th">Invoice</th><th className="th">Customer</th><th className="th">Subscription</th><th className="th">Date</th><th className="th">Due</th><th className="th">Status</th><th className="th text-right">Total</th><th className="th text-right">Amount due</th></tr></thead>
              <tbody>{data.items.map((i) => (
                <tr key={i.id} className="cursor-pointer hover:bg-canvas" onClick={() => nav(`/invoices/${i.id}`)}>
                  <td className="td font-semibold">{i.number}{i.is_demo && <DemoTag />}</td><td className="td">{i.customer_name}</td>
                  <td className="td text-[13px] text-ink-soft">{i.subscription_number ?? '—'}</td><td className="td">{fdate(i.invoice_date)}</td>
                  <td className={clsx('td', i.is_overdue && 'font-semibold text-bad')}>{fdate(i.due_date)}</td>
                  <td className="td"><Status state={i.is_overdue ? 'overdue' : i.state} /></td>
                  <td className="td text-right num">{inr(i.total)}</td>
                  <td className={clsx('td text-right num font-semibold', Number(i.amount_due) > 0 && i.state === 'confirmed' ? 'text-ink' : 'text-ink-faint')}>{inr(i.amount_due)}</td>
                </tr>))}</tbody></table></div>
          )}
          {data && <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={(p) => set({ page: String(p) })} />}
        </Card>
      )}
    </>
  )
}

function BillingLog() {
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const { data, isLoading } = useApi<Page<BillingEvent & { subscription_id?: number }>>('/billing/events', { status, page })
  const { run, busy } = useRunner()
  return (
    <Card pad={false}>
      <div className="flex flex-wrap items-center gap-2 border-b border-line p-3">
        {['', 'failed', 'pending', 'invoiced'].map((s) => <button key={s} onClick={() => { setStatus(s); setPage(1) }} className={clsx('rounded-full px-3 py-1 text-[12px] font-semibold', status === s ? 'bg-brand-600 text-white' : 'bg-canvas text-ink-soft')}>{s ? titleCase(s) : 'All'}</button>)}
        <p className="ml-auto text-[12px] text-ink-soft">One billing event per subscription period. Failed events keep the period open and can be retried safely.</p>
      </div>
      {isLoading ? <TableSkeleton /> : !data?.items.length ? <Empty title={status === 'failed' ? 'No failed billing events' : 'No billing events'} /> : (
        <div className="overflow-x-auto"><table className="w-full min-w-[760px]">
          <thead><tr><th className="th">Event</th><th className="th">Period</th><th className="th">Status</th><th className="th">Source</th><th className="th text-right">Attempts</th><th className="th">Invoice</th><th className="th">Logged</th><th className="th" /></tr></thead>
          <tbody>{data.items.map((e) => (
            <tr key={e.id}>
              <td className="td num text-ink-soft">#{e.id}</td><td className="td text-[13px]">{fdate(e.period_start)} – {fdate(e.period_end)}</td>
              <td className="td"><Status state={e.status} />{e.error && <span className="block max-w-[260px] truncate text-[11px] text-bad" title={e.error}>{e.error}</span>}</td>
              <td className="td text-[13px]">{titleCase(e.source)}</td><td className="td text-right num">{e.attempts}</td>
              <td className="td">{e.invoice_id ? <Link className="link" to={`/invoices/${e.invoice_id}`}>{e.invoice_number}</Link> : '—'}</td>
              <td className="td text-[12px] text-ink-soft">{fdatetime(e.created_at)}</td>
              <td className="td text-right">{e.status !== 'invoiced' && <Button size="sm" icon={<RotateCcw className="h-3.5 w-3.5" />} loading={busy === `r${e.id}`} onClick={() => run(`r${e.id}`, () => api<Msg>(`/billing/events/${e.id}/retry`, { method: 'POST' }), (r) => r.message)}>Retry</Button>}</td>
            </tr>))}</tbody></table></div>
      )}
      {data && <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} />}
    </Card>
  )
}

export function InvoiceDocument({ inv, company = 'Brightloop Software' }: { inv: Invoice; company?: string }) {
  return (
    <div className="card p-6 md:p-10">
      <div className="flex flex-wrap items-start justify-between gap-6 border-b border-line pb-6">
        <div><Wordmark /><p className="mt-3 font-display text-[18px] font-bold">{company}</p><p className="text-[12px] text-ink-soft">Kochi, Kerala · billing@brightloop.example</p></div>
        <div className="sm:text-right">
          <p className="text-[11px] font-bold uppercase tracking-[.2em] text-brand-700">Tax invoice</p>
          <p className="font-display text-[24px] font-extrabold">{inv.number}</p>
          <div className="mt-1"><Status state={inv.is_overdue ? 'overdue' : inv.state} /></div>
        </div>
      </div>
      <div className="grid gap-6 border-b border-line py-6 text-[13px] sm:grid-cols-3">
        <div><p className="label">Billed to</p><p className="font-semibold">{inv.customer.name}</p>{inv.customer.company && <p>{inv.customer.company}</p>}<p className="whitespace-pre-line text-ink-soft">{inv.customer.address}</p><p className="text-ink-soft">{inv.customer.email}</p>{inv.customer.gstin && <p className="text-ink-soft">GSTIN {inv.customer.gstin}</p>}</div>
        <div><p className="label">Invoice date</p><p>{fdate(inv.invoice_date)}</p><p className="label mt-3">Due date</p><p className={inv.is_overdue ? 'font-semibold text-bad' : ''}>{fdate(inv.due_date)}</p></div>
        <div><p className="label">Billing period</p><p>{inv.period_start ? `${fdate(inv.period_start)} – ${fdate(inv.period_end)}` : '—'}</p><p className="label mt-3">Subscription</p><p>{inv.subscription_number ?? '—'}</p></div>
      </div>
      <div className="overflow-x-auto"><table className="w-full min-w-[640px] text-[13px]">
        <thead><tr><th className="th">Description</th><th className="th text-right">Qty</th><th className="th text-right">Unit price</th><th className="th text-right">Discount</th><th className="th text-right">Taxable</th><th className="th">Tax</th><th className="th text-right">Amount</th></tr></thead>
        <tbody>{inv.lines.map((l) => (
          <tr key={l.id}><td className="td font-medium">{l.description}</td><td className="td text-right num">{l.quantity}</td><td className="td text-right num">{inr(l.unit_price)}</td>
            <td className="td text-right num text-ok">{Number(l.discount_amount) ? `−${inr(l.discount_amount)}` : '—'}</td><td className="td text-right num">{inr(l.taxable_amount)}</td>
            <td className="td text-ink-soft">{l.tax_name ? <>{l.tax_name}<span className="block num">{inr(l.tax_amount)}</span></> : '—'}</td><td className="td text-right num font-semibold">{inr(l.total)}</td></tr>))}</tbody>
      </table></div>
      <div className="mt-6 flex flex-wrap justify-between gap-6">
        <div className="max-w-sm text-[12px] text-ink-soft">
          {!!inv.discounts.length && <><p className="label">Discounts applied</p>{inv.discounts.map((d) => <p key={d.name}>{d.name} ({d.type === 'percentage' ? `${Number(d.value)}%` : inr(d.value)}): −{inr(d.amount)}</p>)}</>}
          <p className="mt-3">Tax is calculated on the amount after discounts using the configured tax rules.</p>
        </div>
        <dl className="w-full max-w-xs space-y-1.5 text-[13px]">
          <div className="flex justify-between"><dt className="text-ink-soft">Subtotal</dt><dd className="num">{inr(inv.untaxed_amount)}</dd></div>
          <div className="flex justify-between"><dt className="text-ink-soft">Discount</dt><dd className="num text-ok">−{inr(inv.discount_amount)}</dd></div>
          <div className="flex justify-between"><dt className="text-ink-soft">Taxable amount</dt><dd className="num">{inr(Number(inv.untaxed_amount) - Number(inv.discount_amount))}</dd></div>
          <div className="flex justify-between"><dt className="text-ink-soft">Tax</dt><dd className="num">{inr(inv.tax_amount)}</dd></div>
          <div className="flex justify-between border-t border-line pt-2 text-[15px] font-bold"><dt>Total</dt><dd className="num">{inr(inv.total)}</dd></div>
          <div className="flex justify-between"><dt className="text-ink-soft">Paid</dt><dd className="num">{inr(inv.amount_paid)}</dd></div>
          <div className="flex justify-between rounded-lg bg-brand-50 px-3 py-2 text-[15px] font-bold text-brand-800"><dt>Amount due</dt><dd className="num">{inr(inv.amount_due)}</dd></div>
        </dl>
      </div>
    </div>
  )
}

export function RecordPayment({ inv, onClose }: { inv: Pick<Invoice, 'id' | 'number' | 'amount_due' | 'customer_name' | 'customer_id'>; onClose: () => void }) {
  const [f, setF] = useState({ amount: String(inv.amount_due), method: 'bank_transfer', payment_date: todayISO(), reference: '', note: '' })
  const { run, busy } = useRunner()
  const over = Number(f.amount) > Number(inv.amount_due)
  const save = async () => {
    const r = await run('pay', () => api<Payment>('/payments', { body: { invoice_id: inv.id, customer_id: inv.customer_id, ...f, reference: f.reference || null, note: f.note || null } }),
      (p) => `Payment ${p.reference} of ${inr(p.amount)} recorded against ${inv.number}`)
    if (r) onClose()
  }
  return (
    <Modal open onClose={onClose} title={`Record payment · ${inv.number}`} footer={<><Button onClick={onClose}>Cancel</Button><Button variant="success" loading={busy === 'pay'} disabled={!(Number(f.amount) > 0) || over} onClick={save}>Record payment</Button></>}>
      <div className="mb-4 flex items-center justify-between rounded-lg bg-canvas p-3 text-[13px]"><span>{inv.customer_name}</span><span>Outstanding <b className="num">{inr(inv.amount_due)}</b></span></div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Amount (₹)" error={over ? 'Cannot exceed the outstanding balance' : undefined} hint={Number(f.amount) < Number(inv.amount_due) && Number(f.amount) > 0 ? 'Partial payment — the invoice stays open for the balance' : undefined}>
          <input className="input num" type="number" min="0.01" step="0.01" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Field>
        <Field label="Method"><select className="input" value={f.method} onChange={(e) => setF({ ...f, method: e.target.value })}>{Object.entries(methodLabel).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
        <Field label="Payment date"><input className="input" type="date" max={todayISO()} value={f.payment_date} onChange={(e) => setF({ ...f, payment_date: e.target.value })} /></Field>
        <Field label="Reference" hint="UTR / cheque no. Leave blank to auto-number"><input className="input" value={f.reference} onChange={(e) => setF({ ...f, reference: e.target.value })} /></Field>
        <Field label="Note" className="sm:col-span-2"><textarea className="input" rows={2} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></Field>
      </div>
    </Modal>
  )
}

export function InvoiceDetail({ portal = false }: { portal?: boolean }) {
  const { id } = useParams()
  const { isAdmin } = useAuth()
  const { data: inv, error, refetch } = useApi<Invoice>(`/invoices/${id}`)
  const { confirm, toast } = useUi()
  const { run, busy } = useRunner()
  const [pay, setPay] = useState(false)
  if (error) return <ErrorBox error={error} onRetry={refetch} />
  if (!inv) return <Skeleton className="h-96" />
  const act = async (a: 'confirm' | 'cancel') => {
    const r = await confirm(a === 'confirm'
      ? { title: 'Confirm invoice', body: 'Confirmed invoices are visible to the customer and can receive payments. Discounts on this invoice count against their usage limits.', confirmLabel: 'Confirm invoice' }
      : { title: 'Cancel invoice', body: 'Cancelled invoices stay on record but are no longer payable. Any discount usage is released.', confirmLabel: 'Cancel invoice', danger: true, reason: { label: 'Reason', required: true } })
    if (r.ok) run(a, () => api(`/invoices/${inv.id}/actions/${a}`, { body: { reason: r.reason } }), a === 'confirm' ? 'Invoice confirmed' : 'Invoice cancelled')
  }
  const send = async () => {
    try {
      const r = await api<Msg>(`/invoices/${inv.id}/send`, { method: 'POST' })
      toast(r.detail?.email_status === 'sent' ? 'success' : 'warning', r.message)
      refetch()
    } catch (e) { toast('error', (e as Error).message) }
  }
  const voidPay = async (p: Payment) => {
    const r = await confirm({ title: `Void payment ${p.reference}`, body: 'The payment stays on record as voided and the invoice balance is reopened.', danger: true, confirmLabel: 'Void payment', reason: { label: 'Reason', required: true } })
    if (r.ok) run('void', () => api(`/payments/${p.id}/void`, { body: { reason: r.reason } }), 'Payment voided')
  }
  const a = inv.allowed_actions
  return (
    <>
      <div className="no-print">
        <PageHeader crumbs={[{ label: 'Invoices', to: portal ? '/portal/invoices' : '/invoices' }, { label: inv.number }]} title={inv.number}
          subtitle={<>{portal ? 'Your invoice' : <Link className="link" to={`/customers/${inv.customer_id}`}>{inv.customer_name}</Link>}{inv.subscription_id && !portal && <> · <Link className="link" to={`/subscriptions/${inv.subscription_id}`}>{inv.subscription_number}</Link></>}</>}
          actions={<>
            {a.includes('confirm') && <Button variant="primary" icon={<CheckCircle2 className="h-4 w-4" />} loading={busy === 'confirm'} onClick={() => act('confirm')}>Confirm</Button>}
            {a.includes('pay') && <Button variant="success" icon={<CreditCard className="h-4 w-4" />} onClick={() => setPay(true)}>Record payment</Button>}
            {a.includes('send') && <Button icon={<Mail className="h-4 w-4" />} onClick={send}>Send</Button>}
            <Button icon={<Printer className="h-4 w-4" />} onClick={() => window.print()}>Print</Button>
            {inv.state !== 'draft' || !portal ? <Button icon={<Download className="h-4 w-4" />} onClick={() => download(`/invoices/${inv.id}/pdf`).catch((e) => toast('error', e.message))}>PDF</Button> : null}
            {a.includes('cancel') && <Button variant="danger" icon={<XCircle className="h-4 w-4" />} loading={busy === 'cancel'} onClick={() => act('cancel')}>Cancel</Button>}
          </>} />
        {inv.is_overdue && <div className="mb-4 flex items-center gap-3 rounded-xl border border-brand-200 bg-brand-50 px-4 py-3 text-brand-900"><AlertTriangle className="h-5 w-5" /><p><b>Overdue.</b> {inr(inv.amount_due)} was due on {fdate(inv.due_date)}.</p></div>}
        {inv.state === 'draft' && <div className="mb-4 rounded-xl border border-line bg-white px-4 py-3 text-[13px] text-ink-soft">This invoice is a <b>draft</b> — review and confirm it to make it payable and visible to the customer.</div>}
      </div>
      <div className="grid gap-5 xl:grid-cols-[1fr_320px]">
        <InvoiceDocument inv={inv} />
        <div className="no-print space-y-5">
          <Card title="Payments" pad={false}>
            {!inv.payments.length ? <p className="p-5 text-[13px] text-ink-soft">No payments recorded yet.</p> : (
              <ul className="divide-y divide-line">{inv.payments.map((p) => (
                <li key={p.id} className="px-5 py-3 text-[13px]">
                  <div className="flex items-center justify-between"><span className={clsx('num font-semibold', p.status === 'voided' && 'text-ink-faint line-through')}>{inr(p.amount)}</span><Status state={p.status} /></div>
                  <p className="text-ink-soft">{methodLabel[p.method]} · {fdate(p.payment_date)} · <span className="font-mono text-[11px]">{p.reference}</span></p>
                  {p.note && <p className="text-[12px] text-ink-soft">{p.note}</p>}
                  {p.voided_reason && <p className="text-[12px] text-bad">Voided: {p.voided_reason}</p>}
                  {isAdmin && p.status === 'posted' && <button className="mt-1 text-[12px] text-bad hover:underline" onClick={() => voidPay(p)}>Void</button>}
                </li>))}</ul>
            )}
          </Card>
          <Card title="History">
            <ul className="space-y-2 text-[13px]">
              <li className="flex justify-between"><span className="text-ink-soft">Generated</span><span>{fdate(inv.invoice_date)}</span></li>
              <li className="flex justify-between"><span className="text-ink-soft">Confirmed</span><span>{fdatetime(inv.confirmed_at)}</span></li>
              <li className="flex justify-between"><span className="text-ink-soft">Emailed</span><span>{inv.sent_at ? fdatetime(inv.sent_at) : 'Not sent'}</span></li>
              <li className="flex justify-between"><span className="text-ink-soft">Paid in full</span><span>{fdatetime(inv.paid_at)}</span></li>
            </ul>
            {inv.notes && <p className="mt-3 whitespace-pre-line rounded-lg bg-canvas p-3 text-[12px] text-ink-soft">{inv.notes}</p>}
          </Card>
        </div>
      </div>
      {pay && <RecordPayment inv={inv} onClose={() => setPay(false)} />}
    </>
  )
}

/* ======================= Payments ======================= */
export function Payments() {
  const [f, set] = useUrlFilters({ q: '', method: '', status: '', date_from: '', date_to: '', page: '1' })
  const [q, setQ] = useState(f.q)
  const dq = useDebounced(q)
  const { data, isLoading, error, refetch } = useApi<Page<Payment>>('/payments', { ...f, q: dq })
  const [pick, setPick] = useState(false)
  const nav = useNavigate()
  return (
    <>
      <PageHeader title="Payments" subtitle="Money received, each payment allocated to exactly one invoice." actions={<Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setPick(true)}>Record payment</Button>} />
      <Card pad={false}>
        <div className="flex flex-wrap gap-2 border-b border-line p-3">
          <input className="input max-w-[240px]" placeholder="Reference or customer" value={q} onChange={(e) => { setQ(e.target.value); set({ q: e.target.value }) }} />
          <select className="input w-40" value={f.method} onChange={(e) => set({ method: e.target.value })}><option value="">All methods</option>{Object.entries(methodLabel).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
          <select className="input w-32" value={f.status} onChange={(e) => set({ status: e.target.value })}><option value="">Any status</option><option value="posted">Posted</option><option value="voided">Voided</option></select>
          <input type="date" className="input w-[150px]" value={f.date_from} onChange={(e) => set({ date_from: e.target.value })} aria-label="From" />
          <input type="date" className="input w-[150px]" value={f.date_to} onChange={(e) => set({ date_to: e.target.value })} aria-label="To" />
        </div>
        {error ? <div className="p-4"><ErrorBox error={error} onRetry={refetch} /></div> : isLoading ? <TableSkeleton /> : !data?.items.length ? <Empty icon={<CreditCard className="h-5 w-5" />} title="No payments found" /> : (
          <div className="overflow-x-auto"><table className="w-full min-w-[820px]">
            <thead><tr><th className="th">Reference</th><th className="th">Date</th><th className="th">Customer</th><th className="th">Invoice</th><th className="th">Method</th><th className="th">Recorded by</th><th className="th">Status</th><th className="th text-right">Amount</th></tr></thead>
            <tbody>{data.items.map((p) => (
              <tr key={p.id} className="cursor-pointer hover:bg-canvas" onClick={() => nav(`/invoices/${p.invoice_id}`)}>
                <td className="td font-mono text-[12px]">{p.reference}</td><td className="td">{fdate(p.payment_date)}</td><td className="td">{p.customer_name}</td>
                <td className="td font-semibold">{p.invoice_number}</td><td className="td">{methodLabel[p.method]}</td><td className="td text-[13px] text-ink-soft">{p.recorded_by_name ?? '—'}</td>
                <td className="td"><Status state={p.status} /></td><td className={clsx('td text-right num font-semibold', p.status === 'voided' && 'text-ink-faint line-through')}>{inr(p.amount)}</td>
              </tr>))}</tbody></table></div>
        )}
        {data && <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={(p) => set({ page: String(p) })} />}
      </Card>
      {pick && <PickInvoice onClose={() => setPick(false)} />}
    </>
  )
}

function PickInvoice({ onClose }: { onClose: () => void }) {
  const [q, setQ] = useState('')
  const dq = useDebounced(q)
  const { data } = useApi<Page<InvRow>>('/invoices', { outstanding: true, q: dq, page_size: 20 })
  const [inv, setInv] = useState<InvRow | null>(null)
  if (inv) return <RecordPayment inv={inv} onClose={onClose} />
  return (
    <Modal open onClose={onClose} title="Which invoice is this payment for?">
      <input className="input mb-3" autoFocus placeholder="Search invoice number or customer" value={q} onChange={(e) => setQ(e.target.value)} />
      <ul className="max-h-80 divide-y divide-line overflow-y-auto rounded-lg border border-line">
        {!data?.items.length && <li className="p-4 text-center text-ink-soft">No outstanding confirmed invoices.</li>}
        {data?.items.map((i) => (
          <li key={i.id}><button onClick={() => setInv(i)} className="flex w-full items-center justify-between px-4 py-2.5 text-left hover:bg-brand-50">
            <span><b>{i.number}</b><span className="block text-[12px] text-ink-soft">{i.customer_name} · due {fdate(i.due_date)}</span></span>
            <span className="text-right"><span className="num font-semibold">{inr(i.amount_due)}</span>{i.is_overdue && <Badge color="red" className="ml-2">Overdue</Badge>}</span>
          </button></li>))}
      </ul>
    </Modal>
  )
}

/* ======================= Discounts ======================= */
function DiscountForm({ initial, onClose }: { initial?: Discount; onClose: () => void }) {
  const { data: prods } = useApi<Page<Product>>('/products', { page_size: 200 })
  const [sq, setSq] = useState('')
  const dsq = useDebounced(sq)
  const { data: subs } = useApi<Page<SubRow>>('/subscriptions', { state: 'active,paused,confirmed', q: dsq, page_size: 30 })
  const [f, setF] = useState({
    name: initial?.name ?? '', discount_type: initial?.discount_type ?? 'percentage', value: initial?.value ?? '', scope: initial?.scope ?? 'subscription',
    min_purchase: initial?.min_purchase ?? '0', min_quantity: initial?.min_quantity ?? 0, start_date: initial?.start_date ?? '', end_date: initial?.end_date ?? '',
    max_usage: initial?.max_usage ?? '', is_active: initial?.is_active ?? true, product_ids: initial?.product_ids ?? [], subscription_ids: initial?.subscription_ids ?? [],
  })
  const { run, busy } = useRunner()
  const err = f.discount_type === 'percentage' && Number(f.value) > 100 ? 'Percentage cannot exceed 100' : f.start_date && f.end_date && f.end_date < f.start_date ? 'End date must be after start date' : f.scope === 'products' && !f.product_ids.length ? 'Pick at least one product' : ''
  const save = async () => {
    const body = { ...f, start_date: f.start_date || null, end_date: f.end_date || null, max_usage: f.max_usage === '' ? null : Number(f.max_usage) }
    if (await run('save', () => initial ? api(`/discounts/${initial.id}`, { method: 'PUT', body }) : api('/discounts', { body }), 'Discount rule saved')) onClose()
  }
  const toggle = (k: 'product_ids' | 'subscription_ids', id: number) => setF({ ...f, [k]: f[k].includes(id) ? f[k].filter((x) => x !== id) : [...f[k], id] })
  return (
    <Modal open wide onClose={onClose} title={initial ? 'Edit discount rule' : 'New discount rule'} footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy === 'save'} disabled={!f.name || !(Number(f.value) > 0) || !!err} onClick={save}>Save rule</Button></>}>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Name" className="sm:col-span-3"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Type"><select className="input" value={f.discount_type} onChange={(e) => setF({ ...f, discount_type: e.target.value as 'fixed' })}><option value="percentage">Percentage</option><option value="fixed">Fixed amount</option></select></Field>
        <Field label={f.discount_type === 'percentage' ? 'Value (%)' : 'Value (₹)'}><input className="input num" type="number" min="0.01" step="0.01" value={f.value} onChange={(e) => setF({ ...f, value: e.target.value })} /></Field>
        <Field label="Applies to"><select className="input" value={f.scope} onChange={(e) => setF({ ...f, scope: e.target.value as 'products' })}><option value="subscription">Whole subscription</option><option value="products">Specific products</option></select></Field>
        <Field label="Min. purchase (₹)" hint="Of the eligible lines"><input className="input num" type="number" min={0} value={f.min_purchase} onChange={(e) => setF({ ...f, min_purchase: e.target.value })} /></Field>
        <Field label="Min. quantity"><input className="input" type="number" min={0} value={f.min_quantity} onChange={(e) => setF({ ...f, min_quantity: Number(e.target.value) })} /></Field>
        <Field label="Usage limit" hint="Blank = unlimited"><input className="input" type="number" min={1} value={f.max_usage} onChange={(e) => setF({ ...f, max_usage: e.target.value as never })} /></Field>
        <Field label="Starts"><input className="input" type="date" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} /></Field>
        <Field label="Ends"><input className="input" type="date" value={f.end_date} onChange={(e) => setF({ ...f, end_date: e.target.value })} /></Field>
        <div className="flex items-end"><Toggle checked={f.is_active} onChange={(v) => setF({ ...f, is_active: v })} label="Active" /></div>
      </div>
      {f.scope === 'products' && <><p className="mb-2 mt-5 font-display font-bold">Products</p><div className="flex flex-wrap gap-2">{prods?.items.map((p) => <button key={p.id} type="button" onClick={() => toggle('product_ids', p.id)} className={clsx('rounded-full border px-3 py-1 text-[12px] font-semibold', f.product_ids.includes(p.id) ? 'border-brand-600 bg-brand-50 text-brand-700' : 'border-line text-ink-soft')}>{p.name}</button>)}</div></>}
      <p className="mb-1 mt-5 font-display font-bold">Limit to subscriptions <span className="font-sans text-[12px] font-normal text-ink-soft">(optional — none selected means all)</span></p>
      {!!f.subscription_ids.length && <div className="mb-2 flex flex-wrap gap-1.5">{f.subscription_ids.map((id) => <button key={id} type="button" onClick={() => toggle('subscription_ids', id)} className="rounded-full border border-brand-600 bg-brand-50 px-2.5 py-0.5 text-[12px] font-semibold text-brand-700">#{id} ✕</button>)}</div>}
      <input className="input mb-2" placeholder="Search subscription number, customer or plan…" value={sq} onChange={(e) => setSq(e.target.value)} />
      <div className="flex max-h-32 flex-wrap gap-2 overflow-y-auto">{subs?.items.map((s) => <button key={s.id} type="button" onClick={() => toggle('subscription_ids', s.id)} className={clsx('rounded-full border px-3 py-1 text-[12px] font-semibold', f.subscription_ids.includes(s.id) ? 'border-brand-600 bg-brand-50 text-brand-700' : 'border-line text-ink-soft')}>{s.number} · {s.customer_name}</button>)}</div>
      {err && <p className="mt-3 text-[13px] text-bad">{err}</p>}
    </Modal>
  )
}

export function Discounts() {
  const { isAdmin } = useAuth()
  const { data, isLoading, error, refetch } = useApi<Discount[]>('/discounts')
  const [edit, setEdit] = useState<Discount | 'new' | null>(null)
  return (
    <>
      <PageHeader title="Discounts" subtitle={isAdmin ? 'Rules apply automatically to the next qualifying invoice and stop when they expire or run out.' : 'View-only — only an administrator can create or change discount rules.'}
        actions={isAdmin && <Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setEdit('new')}>New discount</Button>} />
      {error && <ErrorBox error={error} onRetry={refetch} />}
      <Card pad={false}>
        {isLoading ? <TableSkeleton /> : !data?.length ? <Empty icon={<Percent className="h-5 w-5" />} title="No discount rules" /> : (
          <div className="overflow-x-auto"><table className="w-full min-w-[900px]">
            <thead><tr><th className="th">Rule</th><th className="th">Value</th><th className="th">Eligibility</th><th className="th">Validity</th><th className="th">Usage</th><th className="th text-right">Discounted</th><th className="th">Status</th>{isAdmin && <th className="th" />}</tr></thead>
            <tbody>{data.map((d) => {
              const pct = d.max_usage ? Math.min(100, (d.usage_reserved / d.max_usage) * 100) : 0
              return (
                <tr key={d.id} className="hover:bg-canvas">
                  <td className="td font-semibold">{d.name}<span className="block text-[12px] font-normal text-ink-soft">{d.scope === 'products' ? `${d.product_ids.length} product(s)` : 'Whole subscription'}{d.subscription_ids.length ? ` · ${d.subscription_ids.length} subscription(s)` : ''}</span></td>
                  <td className="td num font-bold text-brand-700">{d.discount_type === 'percentage' ? `${Number(d.value)}%` : inr(d.value)}</td>
                  <td className="td text-[12px] text-ink-soft">{Number(d.min_purchase) ? `Min ${inr(d.min_purchase)}` : 'Any amount'}{d.min_quantity ? ` · ${d.min_quantity}+ units` : ''}</td>
                  <td className="td text-[12px]">{d.start_date || d.end_date ? `${fdate(d.start_date)} – ${fdate(d.end_date)}` : 'Always'}</td>
                  <td className="td w-40 text-[12px]">{d.max_usage ? <><div className="mb-1 h-1.5 overflow-hidden rounded-full bg-gray-100"><div className="h-full bg-brand-500" style={{ width: `${pct}%` }} /></div>{d.usage_consumed} used{d.usage_reserved > d.usage_consumed && ` + ${d.usage_reserved - d.usage_consumed} on drafts`} / {d.max_usage}</> : <>{d.usage_consumed} used · no limit</>}</td>
                  <td className="td text-right num">{inr(d.total_discounted)}</td>
                  <td className="td"><Status state={d.status} /></td>
                  {isAdmin && <td className="td text-right"><Button size="sm" variant="ghost" onClick={() => setEdit(d)}>Edit</Button></td>}
                </tr>
              )
            })}</tbody></table></div>
        )}
      </Card>
      {edit && <DiscountForm initial={edit === 'new' ? undefined : edit} onClose={() => setEdit(null)} />}
    </>
  )
}

