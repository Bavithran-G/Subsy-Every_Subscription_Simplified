import { clsx } from 'clsx'
import {
  ArrowRight, CalendarClock, Check, CheckCircle2, CirclePause, CirclePlay, Clock, FilePlus2, FileText, Pencil, Plus,
  Receipt, RefreshCcw, Repeat, Send, Timer, XCircle,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { CustomerPicker } from '../components/CustomerPicker'
import { type EditLine, LineEditor, emptyLine, toPayload } from '../components/LineEditor'
import { Badge, Button, Card, DemoTag, Empty, ErrorBox, Field, Modal, PageHeader, Pagination, Skeleton, Status, TableSkeleton, Tabs, useUi } from '../components/ui'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { fdate, fdatetime, inr, periodLabel, titleCase, todayISO } from '../lib/format'
import { useApi, useDebounced, useRunner, useUrlFilters } from '../lib/hooks'
import type { Invoice, InvRow, Page, Plan, SubRow, Subscription, Template } from '../lib/types'

const LIFECYCLE = ['draft', 'quotation', 'confirmed', 'active', 'closed']

/* ---------------- list (used for both Quotations and Subscriptions) ---------------- */
export function SubscriptionList({ mode }: { mode: 'quotations' | 'subscriptions' }) {
  const nav = useNavigate()
  const [f, set] = useUrlFilters({ q: '', state: '', view: '', plan_id: '', billing_period: '', page: '1', tab: 'list' })
  const [q, setQ] = useState(f.q)
  const dq = useDebounced(q)
  const { data: plans } = useApi<Plan[]>('/plans')
  const isQ = mode === 'quotations'
  const params = { ...f, q: dq, tab: undefined, view: isQ && !f.state ? 'quotations' : f.view,
    state: f.state || (isQ ? undefined : 'confirmed,active,paused,closed') }
  const { data, isLoading, error, refetch } = useApi<Page<SubRow>>('/subscriptions', params)
  const states = isQ ? ['draft', 'quotation', 'cancelled'] : ['confirmed', 'active', 'paused', 'closed']
  const views = isQ ? [] : [['renewals', 'Renewing in 30 days'], ['expiring', 'Expiring in 7 days'], ['expired', 'Past expiry']]
  const base = isQ ? '/quotations' : '/subscriptions'
  const list = (
    <Card pad={false}>
      <div className="flex flex-wrap items-center gap-2 border-b border-line p-3">
        <input className="input max-w-[260px]" placeholder="Search number, customer, plan" value={q} onChange={(e) => { setQ(e.target.value); set({ q: e.target.value }) }} />
        <div className="flex flex-wrap gap-1">
          <button onClick={() => set({ state: '', view: '' })} className={clsx('rounded-full px-3 py-1 text-[12px] font-semibold', !f.state && !f.view ? 'bg-brand-600 text-white' : 'bg-canvas text-ink-soft hover:bg-gray-100')}>All</button>
          {states.map((s) => <button key={s} onClick={() => set({ state: s, view: '' })} className={clsx('rounded-full px-3 py-1 text-[12px] font-semibold', f.state === s ? 'bg-brand-600 text-white' : 'bg-canvas text-ink-soft hover:bg-gray-100')}>{titleCase(s)}</button>)}
          {views.map(([v, l]) => <button key={v} onClick={() => set({ view: v, state: '' })} className={clsx('rounded-full px-3 py-1 text-[12px] font-semibold', f.view === v ? 'bg-warn text-white' : 'bg-warn-soft text-warn hover:brightness-95')}>{l}</button>)}
        </div>
        <div className="ml-auto flex gap-2">
          <select className="input h-8 w-40" value={f.plan_id} onChange={(e) => set({ plan_id: e.target.value })}><option value="">All plans</option>{plans?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
          {!isQ && <select className="input h-8 w-32" value={f.billing_period} onChange={(e) => set({ billing_period: e.target.value })}><option value="">Any billing</option>{Object.entries(periodLabel).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>}
        </div>
      </div>
      {error ? <div className="p-4"><ErrorBox error={error} onRetry={refetch} /></div> : isLoading ? <TableSkeleton /> : !data?.items.length ? (
        <Empty icon={isQ ? <FileText className="h-5 w-5" /> : <Repeat className="h-5 w-5" />} title={isQ ? 'No quotations here' : 'No subscriptions match'} body={isQ ? 'Start one from a template in a few clicks.' : 'Try clearing filters.'}
          action={isQ && <Button variant="primary" onClick={() => nav('/quotations/new')}>New quotation</Button>} />
      ) : (
        <div className="overflow-x-auto"><table className="w-full min-w-[860px]">
          <thead><tr><th className="th">Number</th><th className="th">Customer</th><th className="th">Plan</th><th className="th">Status</th>
            {isQ ? <><th className="th">Quoted</th><th className="th">Valid until</th></> : <><th className="th">Start</th><th className="th">Expiry</th><th className="th">Next invoice</th></>}
            <th className="th text-right">Per period</th></tr></thead>
          <tbody>{data.items.map((s) => (
            <tr key={s.id} className="cursor-pointer hover:bg-canvas" onClick={() => nav(`${base}/${s.id}`)}>
              <td className="td font-semibold">{s.number}{s.is_demo && <DemoTag />}</td>
              <td className="td">{s.customer_name}</td>
              <td className="td">{s.plan_name}<span className="block text-[12px] text-ink-soft">{periodLabel[s.billing_period]}</span></td>
              <td className="td"><Status state={s.is_expired_quotation ? 'expired' : s.state} label={s.is_expired_quotation ? 'Expired' : undefined} /></td>
              {isQ ? <><td className="td">{fdate(s.quotation_date)}</td><td className={clsx('td', s.is_expired_quotation && 'text-bad')}>{fdate(s.valid_until)}</td></>
                : <><td className="td">{fdate(s.start_date)}</td><td className="td">{fdate(s.end_date)}</td><td className="td">{s.state === 'active' ? fdate(s.next_invoice_date) : '—'}</td></>}
              <td className="td text-right num font-semibold">{inr(s.total)}</td>
            </tr>))}</tbody></table></div>
      )}
      {data && <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={(p) => set({ page: String(p) })} />}
    </Card>
  )
  return (
    <>
      <PageHeader title={isQ ? 'Quotations' : 'Subscriptions'}
        subtitle={isQ ? 'Offers in draft or sent to customers. Confirming one turns it into a subscription.' : 'Every confirmed, active, paused and closed subscription — with its billing schedule.'}
        actions={<Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => nav('/quotations/new')}>New quotation</Button>} />
      {isQ ? (
        <>
          <div className="mb-4"><Tabs value={f.tab as 'list' | 'templates'} onChange={(t) => set({ tab: t })} tabs={[{ id: 'list', label: 'Quotations' }, { id: 'templates', label: 'Quotation templates' }]} /></div>
          {f.tab === 'templates' ? <Templates /> : list}
        </>
      ) : list}
    </>
  )
}

/* ---------------- new quotation ---------------- */
export function NewQuotation() {
  const nav = useNavigate()
  const [sp] = useSearchParams()
  const { data: plans } = useApi<Plan[]>('/plans', { active: true })
  const { data: templates } = useApi<Template[]>('/templates', { active: true })
  const [f, setF] = useState({ customer_id: sp.get('customer_id') ?? '', template_id: '', plan_id: '', start_date: '', end_date: '', payment_terms_days: '15', notes: '' })
  const [lines, setLines] = useState<EditLine[]>([emptyLine()])
  const { run, busy } = useRunner()
  const plan = plans?.find((p) => String(p.id) === f.plan_id)
  const preTemplate = sp.get('template')
  useEffect(() => { if (preTemplate && templates && !f.template_id) pickTemplate(preTemplate) }, [preTemplate, templates]) // eslint-disable-line

  const pickTemplate = (id: string) => {
    const t = templates?.find((x) => String(x.id) === id)
    if (!t) return setF({ ...f, template_id: '' })
    setF({ ...f, template_id: id, plan_id: String(t.plan_id), payment_terms_days: String(t.payment_terms_days), notes: t.notes ?? '' })
    setLines(t.lines.map((l) => ({ product_id: l.product_id, variant_id: l.variant_id ?? '', quantity: l.quantity, unit_price: l.unit_price ?? '' })))
  }
  const pickPlan = (id: string) => {
    const p = plans?.find((x) => String(x.id) === id)
    setF({ ...f, plan_id: id, template_id: '' })
    if (p) setLines(p.lines.map((l) => ({ product_id: l.product_id, variant_id: l.variant_id ?? '', quantity: Math.max(l.quantity, p.min_quantity), unit_price: l.unit_price ?? '' })))
  }
  const save = async () => {
    const r = await run('save', () => api<Subscription>('/subscriptions', { body: {
      customer_id: Number(f.customer_id), plan_id: Number(f.plan_id), template_id: f.template_id ? Number(f.template_id) : null,
      start_date: f.start_date || null, end_date: f.end_date || null, payment_terms_days: Number(f.payment_terms_days), notes: f.notes || null, lines: toPayload(lines),
    } }), (s) => `Quotation ${s.number} created`)
    if (r) nav(`/quotations/${r.id}`)
  }
  return (
    <>
      <PageHeader crumbs={[{ label: 'Quotations', to: '/quotations' }, { label: 'New' }]} title="New quotation" subtitle="Start from a template so the plan and product lines are filled in for you." />
      <div className="grid gap-5 xl:grid-cols-[1fr_340px]">
        <Card title="Offer">
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Customer"><CustomerPicker value={f.customer_id} onChange={(id) => setF({ ...f, customer_id: id })} /></Field>
            <Field label="Quotation template" hint="Fills plan, lines, validity and terms"><select className="input" value={f.template_id} onChange={(e) => pickTemplate(e.target.value)}><option value="">No template (build manually)</option>{templates?.map((t) => <option key={t.id} value={t.id}>{t.name} · {t.plan_name}</option>)}</select></Field>
            <Field label="Plan"><select className="input" value={f.plan_id} onChange={(e) => pickPlan(e.target.value)}><option value="">Select plan…</option>{plans?.map((p) => <option key={p.id} value={p.id}>{p.name} ({periodLabel[p.billing_period]})</option>)}</select></Field>
            <Field label="Payment terms"><select className="input" value={f.payment_terms_days} onChange={(e) => setF({ ...f, payment_terms_days: e.target.value })}>{[0, 7, 15, 30, 45, 60].map((d) => <option key={d} value={d}>{d === 0 ? 'Due on receipt' : `Net ${d} days`}</option>)}</select></Field>
            <Field label="Start date" hint="Blank = the day it's activated"><input className="input" type="date" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} /></Field>
            <Field label="Expiry date" hint={plan?.term_periods ? `Blank = ${plan.term_periods} ${plan.billing_period.replace('ly', '')} periods from start` : 'Blank = no expiry'}><input className="input" type="date" value={f.end_date} onChange={(e) => setF({ ...f, end_date: e.target.value })} /></Field>
          </div>
          <p className="mb-2 mt-6 font-display font-bold">Product lines</p>
          <LineEditor lines={lines} onChange={setLines} minQty={plan?.min_quantity ?? 1} />
          <Field label="Notes" className="mt-4"><textarea className="input" rows={2} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
        </Card>
        <div className="space-y-4">
          <Card title="Plan rules">
            {plan ? <ul className="space-y-2 text-[13px]">
              <li className="flex justify-between"><span className="text-ink-soft">Billing</span><b>{periodLabel[plan.billing_period]}{plan.billing_interval > 1 ? ` × ${plan.billing_interval}` : ''}</b></li>
              <li className="flex justify-between"><span className="text-ink-soft">Minimum qty</span><b>{plan.min_quantity}</b></li>
              {[['Auto-close at expiry', plan.auto_close], ['Early closure', plan.closable], ['Pause', plan.pausable], ['Renewal', plan.renewable]].map(([l, v]) => (
                <li key={l as string} className="flex justify-between"><span className="text-ink-soft">{l}</span>{v ? <Check className="h-4 w-4 text-ok" /> : <XCircle className="h-4 w-4 text-ink-faint" />}</li>))}
            </ul> : <p className="text-ink-soft">Pick a plan or template to see its rules.</p>}
          </Card>
          <Button variant="primary" className="h-10 w-full" loading={busy === 'save'} disabled={!f.customer_id || !f.plan_id || !toPayload(lines).length} onClick={save} icon={<FilePlus2 className="h-4 w-4" />}>Create draft quotation</Button>
          <p className="text-center text-[12px] text-ink-soft">Taxes are calculated from each product's tax rule.</p>
        </div>
      </div>
    </>
  )
}

/* ---------------- detail ---------------- */
function Lifecycle({ sub }: { sub: Subscription }) {
  const idx = LIFECYCLE.indexOf(sub.state === 'paused' ? 'active' : sub.state)
  return (
    <ol className="flex items-center overflow-x-auto pb-1">
      {LIFECYCLE.map((s, i) => {
        const done = idx >= 0 && i < idx; const cur = i === idx
        return (
          <li key={s} className="flex items-center">
            <span className={clsx('flex items-center gap-2 whitespace-nowrap rounded-full px-3 py-1 text-[12px] font-semibold',
              cur ? 'bg-brand-600 text-white' : done ? 'bg-brand-50 text-brand-700' : 'bg-gray-100 text-ink-faint')}>
              {done ? <Check className="h-3.5 w-3.5" /> : <span className="h-1.5 w-1.5 rounded-full bg-current" />}{cur && sub.state === 'paused' ? 'Active · Paused' : titleCase(s)}
            </span>
            {i < LIFECYCLE.length - 1 && <span className={clsx('mx-1 h-px w-6', done ? 'bg-brand-300' : 'bg-line')} />}
          </li>
        )
      })}
      {sub.state === 'cancelled' && <li className="ml-2"><Status state="cancelled" /></li>}
    </ol>
  )
}

const ACTION_META: Record<string, { label: string; icon: typeof Send; variant?: 'primary' | 'danger' | 'secondary'; confirm?: string; reason?: boolean; danger?: boolean }> = {
  send: { label: 'Send quotation', icon: Send, confirm: 'Email this quotation to the customer and mark it as sent?' },
  confirm: { label: 'Confirm', icon: CheckCircle2, variant: 'primary', confirm: 'Confirm this quotation? Its lines become the agreed subscription.' },
  activate: { label: 'Activate', icon: CirclePlay, variant: 'primary' },
  invoice: { label: 'Create invoice now', icon: Receipt, confirm: 'Generate the invoice for the next billing period now? The scheduler will not bill the same period again.' },
  pause: { label: 'Pause', icon: CirclePause, confirm: 'Pause this subscription? Periods that start while paused are not billed.', reason: true },
  resume: { label: 'Resume', icon: CirclePlay, variant: 'primary' },
  renew: { label: 'Renew', icon: RefreshCcw, confirm: 'Renew for one more term? The expiry date moves forward.' },
  extend: { label: 'Extend validity', icon: Timer },
  close: { label: 'Close', icon: XCircle, variant: 'danger', confirm: 'Close this subscription? No further invoices will be generated.', reason: true, danger: true },
  cancel: { label: 'Cancel quotation', icon: XCircle, variant: 'danger', confirm: 'Cancel this quotation?', reason: true, danger: true },
}

export function SubscriptionActions({ sub, base }: { sub: Subscription; base: string }) {
  const { confirm, toast } = useUi()
  const { run, busy } = useRunner()
  const nav = useNavigate()
  const [activate, setActivate] = useState(false)
  const [start, setStart] = useState(sub.start_date ?? todayISO())
  const doAct = async (a: string) => {
    const m = ACTION_META[a]
    if (a === 'activate') return setActivate(true)
    if (a === 'edit') return nav(`/quotations/${sub.id}/edit`)
    let reason: string | undefined
    if (m.confirm) {
      const r = await confirm({ title: m.label, body: m.confirm, confirmLabel: m.label, danger: m.danger, reason: m.reason ? { label: 'Reason (recorded in history)' } : undefined })
      if (!r.ok) return
      reason = r.reason
    }
    if (a === 'invoice') {
      const inv = await run(a, () => api<Invoice>(`${base}/${sub.id}/invoice-now`, { method: 'POST' }), (i) => `Invoice ${i.number} generated for ${fdate(i.period_start)} – ${fdate(i.period_end)}`)
      if (inv) nav(`/invoices/${inv.id}`)
      return
    }
    const r = await run(a, () => api<Subscription>(`${base}/${sub.id}/actions/${a}`, { body: { reason, days: a === 'extend' ? 30 : undefined } }), `${m.label}: done`)
    if (r && a === 'confirm') toast('info', `${r.number} is now a confirmed subscription — activate it to start billing.`)
  }
  const order = ['edit', 'send', 'confirm', 'activate', 'invoice', 'resume', 'pause', 'renew', 'extend', 'close', 'cancel']
  return (
    <>
      {order.filter((a) => sub.allowed_actions.includes(a)).map((a) => {
        if (a === 'edit') return <Button key={a} icon={<Pencil className="h-4 w-4" />} onClick={() => doAct(a)}>Edit</Button>
        const m = ACTION_META[a]; const Icon = m.icon
        return <Button key={a} variant={m.variant ?? 'secondary'} loading={busy === a} icon={<Icon className="h-4 w-4" />} onClick={() => doAct(a)}>{m.label}</Button>
      })}
      <Modal open={activate} onClose={() => setActivate(false)} title="Activate subscription"
        footer={<><Button onClick={() => setActivate(false)}>Cancel</Button><Button variant="primary" loading={busy === 'activate'} onClick={async () => { if (await run('activate', () => api(`${base}/${sub.id}/actions/activate`, { body: { start_date: start } }), 'Subscription activated — billing schedule started')) setActivate(false) }}>Activate</Button></>}>
        <Field label="Start date" hint="The first billing period starts on this date; recurring invoices follow automatically."><input type="date" className="input" value={start} onChange={(e) => setStart(e.target.value)} /></Field>
      </Modal>
    </>
  )
}

export function SubscriptionDetail({ portal = false }: { portal?: boolean }) {
  const { id } = useParams()
  const { isInternal } = useAuth()
  const base = portal ? '/portal/subscriptions' : '/subscriptions'
  const { data: s, error, refetch } = useApi<Subscription>(`${base}/${id}`)
  const { data: invs } = useApi<Page<InvRow> | InvRow[]>(s ? (portal ? '/portal/invoices' : '/invoices') : null, portal ? { page_size: 100 } : { subscription_id: id, page_size: 50 })
  if (error) return <ErrorBox error={error} onRetry={refetch} />
  if (!s) return <div className="space-y-4"><Skeleton className="h-16" /><Skeleton className="h-64" /></div>
  const isQ = s.state === 'draft' || s.state === 'quotation' || s.state === 'cancelled'
  const listBase = portal ? '/portal/subscriptions' : isQ ? '/quotations' : '/subscriptions'
  const invoices = (Array.isArray(invs) ? invs : invs?.items ?? []).filter((i) => !portal || i.subscription_id === s.id)
  return (
    <>
      <PageHeader crumbs={[{ label: portal ? 'My subscriptions' : isQ ? 'Quotations' : 'Subscriptions', to: listBase }, { label: s.number }]}
        title={<span className="flex flex-wrap items-center gap-3">{s.number}<Status state={s.is_expired_quotation ? 'expired' : s.state} label={s.is_expired_quotation ? 'Quotation expired' : undefined} />{s.is_demo && <DemoTag />}</span>}
        subtitle={<>{portal ? s.plan_name : <Link className="link" to={`/customers/${s.customer_id}`}>{s.customer_name}</Link>} · {s.plan_name} · {periodLabel[s.plan.billing_period]}</>}
        actions={<SubscriptionActions sub={s} base={portal ? '/portal/subscriptions' : '/subscriptions'} />} />
      <Card className="mb-5"><Lifecycle sub={s} /></Card>
      <div className="grid gap-5 xl:grid-cols-[1fr_360px]">
        <div className="space-y-5">
          <Card title="Subscription lines" pad={false}>
            <div className="overflow-x-auto"><table className="w-full min-w-[620px]">
              <thead><tr><th className="th">Product</th><th className="th text-right">Qty</th><th className="th text-right">Unit price</th><th className="th">Tax</th><th className="th text-right">Amount</th></tr></thead>
              <tbody>{s.lines.map((l) => <tr key={l.id}><td className="td font-medium">{l.description}</td><td className="td text-right num">{l.quantity}</td><td className="td text-right num">{inr(l.unit_price)}</td><td className="td text-[13px] text-ink-soft">{l.tax_name ?? '—'}{Number(l.tax_amount) > 0 && <span className="block num">{inr(l.tax_amount)}</span>}</td><td className="td text-right num font-semibold">{inr(l.subtotal)}</td></tr>)}</tbody>
              <tfoot className="text-[13px]">
                <tr><td colSpan={4} className="td text-right text-ink-soft">Subtotal</td><td className="td text-right num">{inr(s.untaxed)}</td></tr>
                <tr><td colSpan={4} className="px-4 py-1.5 text-right text-ink-soft">Tax</td><td className="px-4 py-1.5 text-right num">{inr(s.tax)}</td></tr>
                <tr><td colSpan={4} className="td text-right font-bold">Total per billing period</td><td className="td text-right num text-[15px] font-bold">{inr(s.total)}</td></tr>
              </tfoot>
            </table></div>
            <p className="border-t border-line px-4 py-2.5 text-[12px] text-ink-soft">Discount rules are applied automatically on each invoice when the customer qualifies.</p>
          </Card>
          {!isQ && (
            <Card title="Invoices" pad={false} actions={!portal && <Link to={`/invoices?subscription_id=${s.id}`} className="link text-[13px]">Open in invoices</Link>}>
              {!invoices.length ? <Empty icon={<Receipt className="h-5 w-5" />} title="No invoices yet" body={s.state === 'active' ? `The first invoice is due ${fdate(s.next_invoice_date)}.` : undefined} /> : (
                <div className="overflow-x-auto"><table className="w-full min-w-[560px]"><thead><tr><th className="th">Invoice</th><th className="th">Period</th><th className="th">Status</th><th className="th text-right">Total</th><th className="th text-right">Due</th></tr></thead>
                  <tbody>{invoices.map((i) => <tr key={i.id} className="hover:bg-canvas"><td className="td"><Link className="link" to={portal ? `/portal/invoices/${i.id}` : `/invoices/${i.id}`}>{i.number}</Link></td><td className="td text-[13px]">{fdate(i.period_start)} – {fdate(i.period_end)}</td><td className="td"><Status state={i.is_overdue ? 'overdue' : i.state} /></td><td className="td text-right num">{inr(i.total)}</td><td className="td text-right num">{inr(i.amount_due)}</td></tr>)}</tbody></table></div>
              )}
            </Card>
          )}
          {isInternal && !!s.billing_events.length && (
            <Card title="Billing events" pad={false}>
              <p className="border-b border-line px-5 py-2.5 text-[12px] text-ink-soft">Each billing period has exactly one billing event — the system cannot invoice the same period twice.</p>
              <div className="overflow-x-auto"><table className="w-full min-w-[560px]"><thead><tr><th className="th">#</th><th className="th">Period</th><th className="th">Status</th><th className="th">Source</th><th className="th">Invoice</th></tr></thead>
                <tbody>{s.billing_events.map((e) => <tr key={e.id}><td className="td num text-ink-soft">{e.period_index + 1}</td><td className="td text-[13px]">{fdate(e.period_start)} – {fdate(e.period_end)}</td><td className="td"><Status state={e.status} />{e.error && <span className="block max-w-xs truncate text-[11px] text-bad" title={e.error}>{e.error}</span>}</td><td className="td text-[13px]">{titleCase(e.source)}</td><td className="td">{e.invoice_id ? <Link className="link" to={`/invoices/${e.invoice_id}`}>{e.invoice_number}</Link> : '—'}</td></tr>)}</tbody></table></div>
            </Card>
          )}
        </div>
        <div className="space-y-5">
          <Card title="Details">
            <dl className="grid grid-cols-2 gap-x-3 gap-y-3 text-[13px]">
              <div><dt className="label">Quotation date</dt><dd>{fdate(s.quotation_date)}</dd></div>
              <div><dt className="label">Valid until</dt><dd className={s.is_expired_quotation ? 'text-bad' : ''}>{fdate(s.valid_until)}</dd></div>
              <div><dt className="label">Start date</dt><dd>{fdate(s.start_date)}</dd></div>
              <div><dt className="label">Expiry date</dt><dd>{fdate(s.end_date)}</dd></div>
              <div><dt className="label">Payment terms</dt><dd>{s.payment_terms_days ? `Net ${s.payment_terms_days} days` : 'Due on receipt'}</dd></div>
              <div><dt className="label">Next invoice</dt><dd className="font-semibold text-brand-700">{s.state === 'active' ? fdate(s.next_invoice_date) : '—'}</dd></div>
            </dl>
            {s.notes && <p className="mt-4 rounded-lg bg-canvas p-3 text-[13px] text-ink-soft">{s.notes}</p>}
          </Card>
          <Card title="Plan permissions">
            <ul className="space-y-2 text-[13px]">{([['Close automatically at expiry', s.plan.auto_close], ['Close early', s.plan.closable], ['Pause / resume', s.plan.pausable], ['Renew', s.plan.renewable]] as const).map(([l, v]) => (
              <li key={l} className="flex items-center justify-between"><span className="text-ink-soft">{l}</span>{v ? <Badge color="green">Allowed</Badge> : <Badge color="gray">Not allowed</Badge>}</li>))}</ul>
          </Card>
          <Card title="Timeline">
            <ol className="relative space-y-4 border-l border-line pl-5">{[...s.history].reverse().map((h) => (
              <li key={h.id} className="relative">
                <span className="absolute -left-[26px] top-1 grid h-3 w-3 place-items-center rounded-full border-2 border-white bg-brand-500 ring-2 ring-brand-100" />
                <p className="text-[13px] font-semibold">{titleCase(h.action)}{h.from_state !== h.to_state && h.from_state && <span className="font-normal text-ink-soft"> · {titleCase(h.from_state)} <ArrowRight className="inline h-3 w-3" /> {titleCase(h.to_state)}</span>}</p>
                {h.reason && <p className="text-[12px] text-ink-soft">{h.reason}</p>}
                <p className="flex items-center gap-1 text-[11px] text-ink-faint"><Clock className="h-3 w-3" />{fdatetime(h.created_at)} · {h.user_name}</p>
              </li>))}</ol>
            {!!s.renewals.length && <div className="mt-4 border-t border-line pt-3"><p className="label">Renewals</p>{s.renewals.map((r) => <p key={r.id} className="flex items-center gap-2 text-[13px]"><CalendarClock className="h-3.5 w-3.5 text-ink-faint" />{fdate(r.previous_end_date)} → {fdate(r.new_end_date)}</p>)}</div>}
          </Card>
        </div>
      </div>
    </>
  )
}

/* ---------------- edit quotation ---------------- */
export function EditQuotation() {
  const { id } = useParams()
  const nav = useNavigate()
  const { data: s } = useApi<Subscription>(`/subscriptions/${id}`)
  const [lines, setLines] = useState<EditLine[] | null>(null)
  const [f, setF] = useState({ start_date: '', end_date: '', valid_until: '', payment_terms_days: '15', notes: '' })
  const { run, busy } = useRunner()
  useEffect(() => {
    if (s && !lines) {
      setLines(s.lines.map((l) => ({ product_id: l.product_id, variant_id: l.variant_id ?? '', quantity: l.quantity, unit_price: l.unit_price })))
      setF({ start_date: s.start_date ?? '', end_date: s.end_date ?? '', valid_until: s.valid_until ?? '', payment_terms_days: String(s.payment_terms_days), notes: s.notes ?? '' })
    }
  }, [s, lines])
  if (!s || !lines) return <Skeleton className="h-64" />
  const save = async () => {
    const ok = await run('save', () => api(`/subscriptions/${s.id}`, { method: 'PUT', body: { ...f, start_date: f.start_date || null, end_date: f.end_date || null, valid_until: f.valid_until || null, payment_terms_days: Number(f.payment_terms_days), lines: toPayload(lines) } }), 'Quotation saved')
    if (ok) nav(`/quotations/${s.id}`)
  }
  return (
    <>
      <PageHeader crumbs={[{ label: 'Quotations', to: '/quotations' }, { label: s.number, to: `/quotations/${s.id}` }, { label: 'Edit' }]} title={`Edit ${s.number}`} subtitle={`${s.customer_name} · ${s.plan_name}`}
        actions={<><Button onClick={() => nav(-1)}>Cancel</Button><Button variant="primary" loading={busy === 'save'} onClick={save}>Save changes</Button></>} />
      <Card>
        <div className="grid gap-4 md:grid-cols-4">
          <Field label="Start date"><input type="date" className="input" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} /></Field>
          <Field label="Expiry date"><input type="date" className="input" value={f.end_date} onChange={(e) => setF({ ...f, end_date: e.target.value })} /></Field>
          <Field label="Valid until"><input type="date" className="input" value={f.valid_until} onChange={(e) => setF({ ...f, valid_until: e.target.value })} /></Field>
          <Field label="Payment terms (days)"><input type="number" min={0} className="input" value={f.payment_terms_days} onChange={(e) => setF({ ...f, payment_terms_days: e.target.value })} /></Field>
        </div>
        <p className="mb-2 mt-6 font-display font-bold">Product lines</p>
        <LineEditor lines={lines} onChange={setLines} minQty={s.plan.min_quantity} />
        <Field label="Notes" className="mt-4"><textarea className="input" rows={2} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
      </Card>
    </>
  )
}

/* ---------------- templates ---------------- */
function TemplateForm({ initial, onClose }: { initial?: Template; onClose: () => void }) {
  const { data: plans } = useApi<Plan[]>('/plans')
  const [f, setF] = useState({ name: initial?.name ?? '', plan_id: initial ? String(initial.plan_id) : '', validity_days: initial?.validity_days ?? 30, payment_terms_days: initial?.payment_terms_days ?? 15, notes: initial?.notes ?? '', is_active: initial?.is_active ?? true })
  const [lines, setLines] = useState<EditLine[]>(initial?.lines.map((l) => ({ product_id: l.product_id, variant_id: l.variant_id ?? '', quantity: l.quantity, unit_price: l.unit_price ?? '' })) ?? [emptyLine()])
  const { run, busy } = useRunner()
  const save = async () => {
    const body = { ...f, plan_id: Number(f.plan_id), notes: f.notes || null, lines: toPayload(lines) }
    if (await run('save', () => initial ? api(`/templates/${initial.id}`, { method: 'PUT', body }) : api('/templates', { body }), 'Template saved')) onClose()
  }
  return (
    <Modal open wide onClose={onClose} title={initial ? 'Edit template' : 'New quotation template'} footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy === 'save'} disabled={!f.name || !f.plan_id || !toPayload(lines).length} onClick={save}>Save template</Button></>}>
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="Template name"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Plan"><select className="input" value={f.plan_id} onChange={(e) => setF({ ...f, plan_id: e.target.value })}><option value="">Select…</option>{plans?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
        <Field label="Valid for (days)"><input className="input" type="number" min={1} max={365} value={f.validity_days} onChange={(e) => setF({ ...f, validity_days: Number(e.target.value) })} /></Field>
        <Field label="Payment terms (days)"><input className="input" type="number" min={0} value={f.payment_terms_days} onChange={(e) => setF({ ...f, payment_terms_days: Number(e.target.value) })} /></Field>
        <Field label="Default notes" className="md:col-span-2"><input className="input" value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
      </div>
      <p className="mb-2 mt-5 font-display font-bold">Default product lines</p>
      <LineEditor lines={lines} onChange={setLines} />
    </Modal>
  )
}

function Templates() {
  const { data, isLoading } = useApi<Template[]>('/templates')
  const [edit, setEdit] = useState<Template | 'new' | null>(null)
  const nav = useNavigate()
  return (
    <>
      <div className="mb-3 flex justify-end"><Button icon={<Plus className="h-4 w-4" />} onClick={() => setEdit('new')}>New template</Button></div>
      {isLoading ? <TableSkeleton /> : !data?.length ? <Card><Empty title="No templates yet" body="Templates pre-fill the plan, products, validity and payment terms of a quotation." /></Card> : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{data.map((t) => (
          <div key={t.id} className="card flex flex-col p-5">
            <div className="flex items-start justify-between"><div><h3 className="font-bold">{t.name}</h3><p className="text-[12px] text-ink-soft">{t.plan_name}</p></div>{!t.is_active && <Badge>Inactive</Badge>}</div>
            <ul className="mt-3 space-y-1 text-[13px]">{t.lines.map((l) => <li key={l.id}>{l.quantity} × {l.product_name}{l.variant_label && <span className="text-ink-soft"> ({l.variant_label})</span>}</li>)}</ul>
            <p className="mt-3 text-[12px] text-ink-soft">Valid {t.validity_days} days · Net {t.payment_terms_days}</p>
            <div className="mt-4 flex gap-2 border-t border-line pt-3">
              <Button size="sm" variant="primary" onClick={() => nav(`/quotations/new?template=${t.id}`)} icon={<FilePlus2 className="h-4 w-4" />}>Use</Button>
              <Button size="sm" variant="ghost" onClick={() => setEdit(t)} icon={<Pencil className="h-4 w-4" />}>Edit</Button>
            </div>
          </div>))}</div>
      )}
      {edit && <TemplateForm initial={edit === 'new' ? undefined : edit} onClose={() => setEdit(null)} />}
    </>
  )
}
