import { Archive, Boxes, CalendarRange, Layers, Pause, Pencil, Plus, RefreshCcw, Trash2, XCircle } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { type EditLine, LineEditor, emptyLine, toPayload } from '../components/LineEditor'
import { Badge, Button, Card, Empty, ErrorBox, Field, Modal, PageHeader, Pagination, Status, TableSkeleton, Toggle } from '../components/ui'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { fdate, inr, periodLabel, titleCase } from '../lib/format'
import { useApi, useDebounced, useRunner, useUrlFilters } from '../lib/hooks'
import type { Page, Plan, Product, Tax } from '../lib/types'

/* ======================= Products ======================= */
type VRow = { id?: number; attribute: string; value: string; price_extra: string; is_active: boolean }

function ProductForm({ initial, onClose }: { initial?: Product; onClose: () => void }) {
  const { data: taxes } = useApi<Tax[]>('/taxes')
  const [f, setF] = useState({
    name: initial?.name ?? '', product_type: initial?.product_type ?? 'software', sales_price: initial?.sales_price ?? '',
    cost_price: initial?.cost_price ?? '0', notes: initial?.notes ?? '', tax_id: initial?.tax_id ?? '', is_active: initial?.is_active ?? true,
  })
  const [vars, setVars] = useState<VRow[]>(initial?.variants.filter((v) => v.is_active).map((v) => ({ ...v })) ?? [])
  const { run, busy } = useRunner()
  const dup = new Set<string>(); const dupes = vars.some((v) => { const k = `${v.attribute.trim().toLowerCase()}|${v.value.trim().toLowerCase()}`; if (dup.has(k)) return true; dup.add(k); return false })
  const save = async () => {
    const body = { ...f, tax_id: f.tax_id || null, notes: f.notes || null, variants: vars.filter((v) => v.attribute && v.value) }
    const ok = await run('save', () => initial ? api(`/products/${initial.id}`, { method: 'PUT', body }) : api('/products', { body }), initial ? 'Product updated' : 'Product created')
    if (ok) onClose()
  }
  const margin = Number(f.sales_price) ? ((Number(f.sales_price) - Number(f.cost_price)) / Number(f.sales_price)) * 100 : 0
  return (
    <Modal open wide onClose={onClose} title={initial ? `Edit ${initial.name}` : 'New product'}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy === 'save'} disabled={!f.name || f.sales_price === '' || dupes} onClick={save}>Save product</Button></>}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Product name" className="sm:col-span-2"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Product type"><select className="input" value={f.product_type} onChange={(e) => setF({ ...f, product_type: e.target.value })}>
          <option value="software">Software</option><option value="addon">Add-on</option><option value="service">Service</option><option value="goods">Goods</option></select></Field>
        <Field label="Tax"><select className="input" value={f.tax_id} onChange={(e) => setF({ ...f, tax_id: Number(e.target.value) || '' })}>
          <option value="">No tax</option>{taxes?.filter((t) => t.is_active).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></Field>
        <Field label="Sales price (₹)"><input className="input num" type="number" min={0} step="0.01" value={f.sales_price} onChange={(e) => setF({ ...f, sales_price: e.target.value })} /></Field>
        <Field label="Cost price (₹)" hint={f.sales_price ? `Margin ${margin.toFixed(1)}%` : undefined}><input className="input num" type="number" min={0} step="0.01" value={f.cost_price} onChange={(e) => setF({ ...f, cost_price: e.target.value })} /></Field>
        <Field label="Notes" className="sm:col-span-2"><textarea className="input" rows={2} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
      </div>
      <div className="mt-5">
        <div className="mb-2 flex items-center justify-between"><p className="font-display font-bold">Variants</p><Button size="sm" variant="ghost" icon={<Plus className="h-4 w-4" />} onClick={() => setVars([...vars, { attribute: vars[0]?.attribute ?? 'Brand', value: '', price_extra: '0', is_active: true }])}>Add variant</Button></div>
        <p className="mb-3 text-[12px] text-ink-soft">Each variant adjusts the price, e.g. Brand = Odoo adds ₹560. The final price is used on quotations, subscriptions and invoices.</p>
        {vars.length === 0 && <p className="rounded-lg border border-dashed border-line p-4 text-center text-[13px] text-ink-soft">No variants — product is sold at its sales price.</p>}
        <div className="space-y-2">{vars.map((v, i) => (
          <div key={i} className="grid grid-cols-[1fr_1fr_120px_auto_32px] items-center gap-2">
            <input className="input" placeholder="Attribute (e.g. Brand)" value={v.attribute} onChange={(e) => setVars(vars.map((x, j) => j === i ? { ...x, attribute: e.target.value } : x))} />
            <input className="input" placeholder="Value (e.g. Odoo)" value={v.value} onChange={(e) => setVars(vars.map((x, j) => j === i ? { ...x, value: e.target.value } : x))} />
            <input className="input num" type="number" step="0.01" placeholder="+ ₹" value={v.price_extra} onChange={(e) => setVars(vars.map((x, j) => j === i ? { ...x, price_extra: e.target.value } : x))} />
            <span className="whitespace-nowrap text-[12px] text-ink-soft">= {inr(Number(f.sales_price || 0) + Number(v.price_extra || 0))}</span>
            <button className="grid place-items-center text-ink-faint hover:text-bad" onClick={() => setVars(vars.filter((_, j) => j !== i))} aria-label="Remove variant"><Trash2 className="h-4 w-4" /></button>
          </div>))}</div>
        {dupes && <p className="mt-2 text-[12px] text-bad">Each attribute/value combination can only appear once.</p>}
      </div>
    </Modal>
  )
}

export function Products() {
  const { isAdmin } = useAuth()
  const [f, set] = useUrlFilters({ q: '', product_type: '', active: 'true', page: '1' })
  const [q, setQ] = useState(f.q)
  const dq = useDebounced(q)
  const [edit, setEdit] = useState<Product | 'new' | null>(null)
  const { data, isLoading, error, refetch } = useApi<Page<Product>>('/products', { ...f, q: dq })
  const { run } = useRunner()
  const archive = (p: Product) => run('arch', () => api(`/products/${p.id}`, { method: 'PUT', body: { ...p, is_active: !p.is_active, variants: p.variants.filter((v) => v.is_active) } }), p.is_active ? 'Product archived' : 'Product restored')
  return (
    <>
      <PageHeader title="Products" subtitle="What Brightloop sells — software, add-ons and services, with priced variants."
        actions={isAdmin && <Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setEdit('new')}>New product</Button>} />
      <Card pad={false}>
        <div className="flex flex-wrap gap-2 border-b border-line p-3">
          <input className="input max-w-xs" placeholder="Search products" value={q} onChange={(e) => { setQ(e.target.value); set({ q: e.target.value }) }} />
          <select className="input w-40" value={f.product_type} onChange={(e) => set({ product_type: e.target.value })}><option value="">All types</option>{['software', 'addon', 'service', 'goods'].map((t) => <option key={t} value={t}>{titleCase(t)}</option>)}</select>
          <select className="input w-36" value={f.active} onChange={(e) => set({ active: e.target.value })}><option value="true">Available</option><option value="false">Archived</option><option value="">All</option></select>
        </div>
        {error ? <div className="p-4"><ErrorBox error={error} onRetry={refetch} /></div> : isLoading ? <TableSkeleton /> : !data?.items.length ? <Empty icon={<Boxes className="h-5 w-5" />} title="No products" body="Products you create appear here." /> : (
          <div className="overflow-x-auto"><table className="w-full min-w-[760px]">
            <thead><tr><th className="th">Product</th><th className="th">Type</th><th className="th">Variants</th><th className="th">Tax</th><th className="th text-right">Cost</th><th className="th text-right">Sales price</th>{isAdmin && <th className="th" />}</tr></thead>
            <tbody>{data.items.map((p) => (
              <tr key={p.id} className="hover:bg-canvas">
                <td className="td"><span className="font-semibold">{p.name}</span>{!p.is_active && <Badge className="ml-2" color="gray">Archived</Badge>}<span className="block max-w-xs truncate text-[12px] text-ink-soft">{p.notes}</span></td>
                <td className="td">{titleCase(p.product_type)}</td>
                <td className="td"><div className="flex flex-wrap gap-1">{p.variants.filter((v) => v.is_active).map((v) => <span key={v.id} className="rounded-md bg-canvas px-1.5 py-0.5 text-[12px]">{v.value}{Number(v.price_extra) ? <b className="ml-1 text-brand-700">+{inr(v.price_extra)}</b> : ''}</span>)}{!p.variants.some((v) => v.is_active) && <span className="text-ink-faint">—</span>}</div></td>
                <td className="td text-[13px]">{p.tax?.name ?? '—'}</td>
                <td className="td text-right num text-ink-soft">{inr(p.cost_price)}</td>
                <td className="td text-right num font-semibold">{inr(p.sales_price)}</td>
                {isAdmin && <td className="td text-right"><div className="flex justify-end gap-1">
                  <Button size="sm" variant="ghost" icon={<Pencil className="h-4 w-4" />} onClick={() => setEdit(p)} aria-label="Edit" />
                  <Button size="sm" variant="ghost" icon={<Archive className="h-4 w-4" />} onClick={() => archive(p)} title={p.is_active ? 'Archive' : 'Restore'} aria-label="Archive" />
                </div></td>}
              </tr>))}</tbody></table></div>
        )}
        {data && <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={(p) => set({ page: String(p) })} />}
      </Card>
      {edit && <ProductForm initial={edit === 'new' ? undefined : edit} onClose={() => setEdit(null)} />}
    </>
  )
}

/* ======================= Plans ======================= */
function PlanForm({ initial, onClose }: { initial?: Plan; onClose: () => void }) {
  const [f, setF] = useState({
    name: initial?.name ?? '', description: initial?.description ?? '', billing_period: initial?.billing_period ?? 'monthly',
    billing_interval: initial?.billing_interval ?? 1, min_quantity: initial?.min_quantity ?? 1, start_date: initial?.start_date ?? '',
    end_date: initial?.end_date ?? '', term_periods: initial?.term_periods ?? '', auto_close: initial?.auto_close ?? false,
    closable: initial?.closable ?? true, pausable: initial?.pausable ?? false, renewable: initial?.renewable ?? true, is_active: initial?.is_active ?? true,
  })
  const [lines, setLines] = useState<EditLine[]>(initial?.lines.map((l) => ({ product_id: l.product_id, variant_id: l.variant_id ?? '', quantity: l.quantity, unit_price: l.unit_price ?? '' })) ?? [emptyLine()])
  const { run, busy } = useRunner()
  const badDates = f.start_date && f.end_date && f.end_date < f.start_date
  const save = async () => {
    const body = { ...f, description: f.description || null, start_date: f.start_date || null, end_date: f.end_date || null, term_periods: f.term_periods || null, lines: toPayload(lines) }
    const ok = await run('save', () => initial ? api(`/plans/${initial.id}`, { method: 'PUT', body }) : api('/plans', { body }), initial ? 'Plan updated' : 'Plan created')
    if (ok) onClose()
  }
  return (
    <Modal open wide onClose={onClose} title={initial ? `Edit ${initial.name}` : 'New subscription plan'}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy === 'save'} disabled={!f.name || !!badDates} onClick={save}>Save plan</Button></>}>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Plan name" className="sm:col-span-2"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Billing frequency"><select className="input" value={f.billing_period} onChange={(e) => setF({ ...f, billing_period: e.target.value })}>{Object.entries(periodLabel).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
        <Field label="Bill every" hint="e.g. 3 = every 3 months"><input className="input" type="number" min={1} max={36} value={f.billing_interval} onChange={(e) => setF({ ...f, billing_interval: Number(e.target.value) })} /></Field>
        <Field label="Minimum quantity"><input className="input" type="number" min={1} value={f.min_quantity} onChange={(e) => setF({ ...f, min_quantity: Number(e.target.value) })} /></Field>
        <Field label="Term (periods)" hint="Sets the expiry date; blank = no expiry"><input className="input" type="number" min={1} value={f.term_periods} onChange={(e) => setF({ ...f, term_periods: e.target.value === '' ? '' : Number(e.target.value) as never })} /></Field>
        <Field label="Available from"><input className="input" type="date" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} /></Field>
        <Field label="Available until" error={badDates ? 'Must be on or after the start date' : undefined}><input className="input" type="date" value={f.end_date} onChange={(e) => setF({ ...f, end_date: e.target.value })} /></Field>
        <Field label="Status"><select className="input" value={String(f.is_active)} onChange={(e) => setF({ ...f, is_active: e.target.value === 'true' })}><option value="true">Active</option><option value="false">Inactive</option></select></Field>
        <Field label="Description" className="sm:col-span-3"><input className="input" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
      </div>
      <p className="mb-2 mt-5 font-display font-bold">What the plan allows</p>
      <div className="grid gap-2 sm:grid-cols-2">
        <Toggle checked={f.auto_close} onChange={(v) => setF({ ...f, auto_close: v })} label="Close automatically" hint="Subscriptions close themselves at expiry" />
        <Toggle checked={f.closable} onChange={(v) => setF({ ...f, closable: v })} label="Can be closed early" hint="Allow closing before the expiry date" />
        <Toggle checked={f.pausable} onChange={(v) => setF({ ...f, pausable: v })} label="Can be paused" hint="No billing while paused" />
        <Toggle checked={f.renewable} onChange={(v) => setF({ ...f, renewable: v })} label="Can be renewed" hint="Extend by one more term" />
      </div>
      <p className="mb-2 mt-5 font-display font-bold">Products in this plan</p>
      <LineEditor lines={lines} onChange={setLines} minQty={f.min_quantity} />
    </Modal>
  )
}

export function Plans() {
  const { isAdmin } = useAuth()
  const [edit, setEdit] = useState<Plan | 'new' | null>(null)
  const { data, isLoading, error, refetch } = useApi<Plan[]>('/plans')
  const perm = (on: boolean, Icon: typeof Pause, label: string) => (
    <span className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-semibold ${on ? 'bg-ok-soft text-ok' : 'bg-gray-100 text-ink-faint line-through'}`}><Icon className="h-3 w-3" />{label}</span>
  )
  return (
    <>
      <PageHeader title="Subscription plans" subtitle="Pricing, billing frequency and what each plan permits." actions={isAdmin && <Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setEdit('new')}>New plan</Button>} />
      {error && <ErrorBox error={error} onRetry={refetch} />}
      {isLoading ? <TableSkeleton /> : !data?.length ? <Card><Empty icon={<Layers className="h-5 w-5" />} title="No plans yet" body="Create a plan to start selling subscriptions." /></Card> : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.map((p) => (
            <div key={p.id} className={`card flex flex-col p-5 transition hover:shadow-pop ${!p.is_active ? 'opacity-70' : ''}`}>
              <div className="flex items-start justify-between gap-2">
                <div><h3 className="text-[16px] font-bold">{p.name}</h3><p className="text-[12px] text-ink-soft">{p.description ?? ' '}</p></div>
                <Status state={p.is_active ? 'active' : 'inactive'} />
              </div>
              <p className="mt-4 font-display text-[26px] font-extrabold leading-none">{inr(p.price)}<span className="ml-1 text-[13px] font-medium text-ink-soft">/ {p.billing_interval > 1 ? `${p.billing_interval} ` : ''}{p.billing_period.replace('ly', '').replace('dai', 'day')}{p.billing_interval > 1 ? 's' : ''}</span></p>
              <p className="mt-1 text-[12px] text-ink-soft">excl. tax · min qty {p.min_quantity}{p.term_periods ? ` · ${p.term_periods}-period term` : ' · no expiry'}</p>
              <ul className="mt-4 space-y-1 text-[13px]">{p.lines.map((l) => <li key={l.id} className="flex justify-between gap-2"><span>{l.quantity} × {l.product_name}{l.variant_label && <span className="text-ink-soft"> ({l.variant_label})</span>}</span><span className="num text-ink-soft">{inr(l.effective_price)}</span></li>)}</ul>
              <div className="mt-4 flex flex-wrap gap-1.5">{perm(p.auto_close, XCircle, 'Auto-close')}{perm(p.closable, XCircle, 'Early close')}{perm(p.pausable, Pause, 'Pause')}{perm(p.renewable, RefreshCcw, 'Renew')}</div>
              {(p.start_date || p.end_date) && <p className="mt-3 flex items-center gap-1.5 text-[12px] text-ink-soft"><CalendarRange className="h-3.5 w-3.5" />Available {fdate(p.start_date)} – {fdate(p.end_date)}</p>}
              <div className="mt-auto flex items-center justify-between border-t border-line pt-3 text-[13px]" style={{ marginTop: 'auto', paddingTop: 12 }}>
                <Link to={`/subscriptions?plan_id=${p.id}`} className="link">{p.subscription_count} subscription{p.subscription_count === 1 ? '' : 's'}</Link>
                {isAdmin && <Button size="sm" variant="ghost" icon={<Pencil className="h-4 w-4" />} onClick={() => setEdit(p)}>Edit</Button>}
              </div>
            </div>
          ))}
        </div>
      )}
      {edit && <PlanForm initial={edit === 'new' ? undefined : edit} onClose={() => setEdit(null)} />}
    </>
  )
}
