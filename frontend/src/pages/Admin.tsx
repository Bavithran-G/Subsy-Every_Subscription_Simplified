import { Mail, Play, Plus, ShieldCheck, UserPlus } from 'lucide-react'
import { useState } from 'react'
import { PasswordChecklist } from './Auth'
import { Badge, Button, Card, Empty, Field, Modal, PageHeader, Pagination, Status, TableSkeleton, Tabs, Toggle } from '../components/ui'
import { api } from '../lib/api'
import { PASSWORD_RULES, useAuth } from '../lib/auth'
import { fdatetime, titleCase } from '../lib/format'
import { useApi, useRunner, useUrlFilters } from '../lib/hooks'
import type { Page, Tax, User } from '../lib/types'

type Tab = 'users' | 'taxes' | 'automation' | 'settings' | 'audit' | 'outbox'

function Users() {
  const { user: me } = useAuth()
  const [role, setRole] = useState('')
  const [page, setPage] = useState(1)
  const { data, isLoading } = useApi<Page<User>>('/users', { role, page })
  const [open, setOpen] = useState(false)
  const [f, setF] = useState({ full_name: '', email: '', password: '' })
  const { run, busy } = useRunner()
  const create = async () => { if (await run('c', () => api('/users/staff', { body: f }), `Staff account created for ${f.email}`)) { setOpen(false); setF({ full_name: '', email: '', password: '' }) } }
  return (
    <Card pad={false} title="Users" actions={<Button variant="primary" size="sm" icon={<UserPlus className="h-4 w-4" />} onClick={() => setOpen(true)}>Add staff member</Button>}>
      <div className="flex gap-2 border-b border-line p-3">{['', 'admin', 'staff', 'customer'].map((r) => <button key={r} onClick={() => { setRole(r); setPage(1) }} className={`rounded-full px-3 py-1 text-[12px] font-semibold ${role === r ? 'bg-brand-600 text-white' : 'bg-canvas text-ink-soft'}`}>{r ? titleCase(r) : 'All'}</button>)}</div>
      {isLoading ? <TableSkeleton /> : (
        <div className="overflow-x-auto"><table className="w-full min-w-[640px]">
          <thead><tr><th className="th">User</th><th className="th">Role</th><th className="th">Last sign-in</th><th className="th">Status</th><th className="th" /></tr></thead>
          <tbody>{data?.items.map((u) => (
            <tr key={u.id}><td className="td"><b>{u.full_name}</b><span className="block text-[12px] text-ink-soft">{u.email}</span></td><td className="td"><Status state={u.role} /></td>
              <td className="td text-[13px] text-ink-soft">{fdatetime(u.last_login_at)}</td><td className="td">{u.is_active ? <Badge color="green">Active</Badge> : <Badge>Deactivated</Badge>}</td>
              <td className="td text-right">{u.id !== me?.id && <Button size="sm" variant={u.is_active ? 'danger' : 'secondary'} loading={busy === `u${u.id}`} onClick={() => run(`u${u.id}`, () => api(`/users/${u.id}`, { method: 'PATCH', body: { is_active: !u.is_active } }), u.is_active ? 'User deactivated and signed out' : 'User reactivated')}>{u.is_active ? 'Deactivate' : 'Reactivate'}</Button>}</td></tr>))}</tbody></table></div>
      )}
      {data && <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} />}
      <Modal open={open} onClose={() => setOpen(false)} title="Add internal staff member" footer={<><Button onClick={() => setOpen(false)}>Cancel</Button><Button variant="primary" loading={busy === 'c'} disabled={!f.full_name || !f.email || !PASSWORD_RULES.every((r) => r.test(f.password))} onClick={create}>Create account</Button></>}>
        <p className="mb-4 flex items-center gap-2 rounded-lg bg-canvas p-3 text-[13px] text-ink-soft"><ShieldCheck className="h-4 w-4 text-brand-600" />Only administrators can add staff. Staff can manage customers, quotations, subscriptions, invoices and payments — not discounts, taxes, products, plans or users.</p>
        <div className="space-y-4">
          <Field label="Full name"><input className="input" value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></Field>
          <Field label="Work email"><input className="input" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
          <Field label="Temporary password"><input className="input" type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /><PasswordChecklist pw={f.password} /></Field>
        </div>
      </Modal>
    </Card>
  )
}

function Taxes() {
  const { data, isLoading } = useApi<Tax[]>('/taxes')
  const [edit, setEdit] = useState<Partial<Tax> | null>(null)
  const { run, busy } = useRunner()
  const save = async () => {
    const body = { name: edit!.name, tax_type: edit!.tax_type, rate: edit!.rate, description: edit!.description || null, is_active: edit!.is_active ?? true }
    if (await run('s', () => edit!.id ? api(`/taxes/${edit!.id}`, { method: 'PUT', body }) : api('/taxes', { body }), 'Tax rule saved')) setEdit(null)
  }
  return (
    <Card pad={false} title="Tax rules" actions={<Button size="sm" variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setEdit({ tax_type: 'percentage', rate: '', is_active: true })}>New tax</Button>}>
      <p className="border-b border-line px-5 py-2.5 text-[12px] text-ink-soft">Taxes are attached to products and calculated automatically on every quotation and invoice line, on the amount after discounts.</p>
      {isLoading ? <TableSkeleton /> : !data?.length ? <Empty title="No taxes configured" /> : (
        <table className="w-full"><thead><tr><th className="th">Name</th><th className="th">Type</th><th className="th">Rate</th><th className="th">Applies to</th><th className="th">Status</th><th className="th" /></tr></thead>
          <tbody>{data.map((t) => <tr key={t.id}><td className="td"><b>{t.name}</b><span className="block text-[12px] text-ink-soft">{t.description}</span></td><td className="td">{t.tax_type === 'percentage' ? 'Percentage' : 'Fixed per unit'}</td>
            <td className="td num font-semibold">{t.tax_type === 'percentage' ? `${Number(t.rate)}%` : `₹${Number(t.rate)}`}</td><td className="td">{titleCase(t.applicability)}</td>
            <td className="td"><Status state={t.is_active ? 'active' : 'inactive'} /></td><td className="td text-right"><Button size="sm" variant="ghost" onClick={() => setEdit(t)}>Edit</Button></td></tr>)}</tbody></table>
      )}
      <Modal open={!!edit} onClose={() => setEdit(null)} title={edit?.id ? 'Edit tax' : 'New tax'} footer={<><Button onClick={() => setEdit(null)}>Cancel</Button><Button variant="primary" loading={busy === 's'} disabled={!edit?.name || edit?.rate === ''} onClick={save}>Save</Button></>}>
        {edit && <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Name" className="sm:col-span-2"><input className="input" value={edit.name ?? ''} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
          <Field label="Type"><select className="input" value={edit.tax_type} onChange={(e) => setEdit({ ...edit, tax_type: e.target.value as 'fixed' })}><option value="percentage">Percentage</option><option value="fixed">Fixed amount per unit</option></select></Field>
          <Field label={edit.tax_type === 'percentage' ? 'Rate (%)' : 'Amount per unit (₹)'}><input className="input num" type="number" min={0} step="0.01" value={edit.rate ?? ''} onChange={(e) => setEdit({ ...edit, rate: e.target.value })} /></Field>
          <Field label="Description" className="sm:col-span-2"><input className="input" value={edit.description ?? ''} onChange={(e) => setEdit({ ...edit, description: e.target.value })} /></Field>
          <div className="sm:col-span-2"><Toggle checked={edit.is_active ?? true} onChange={(v) => setEdit({ ...edit, is_active: v })} label="Active" hint="Inactive taxes are not charged on new invoices" /></div>
        </div>}
      </Modal>
    </Card>
  )
}

interface Run { id: number; job: string; trigger: string; status: string; processed: number; created: number; failed: number; message: string | null; started_at: string; finished_at: string | null }
function Automation() {
  const [page, setPage] = useState(1)
  const { data, isLoading } = useApi<Page<Run>>('/admin/automation/runs', { page })
  const { data: st } = useApi<Record<string, unknown>>('/admin/settings')
  const { run, busy } = useRunner()
  const jobs: [string, string, string][] = [
    ['billing', 'Recurring billing', 'Generates one invoice per due billing period'], ['auto_close', 'Auto-close', 'Closes expired subscriptions on auto-close plans'],
    ['renewal_reminders', 'Renewal reminders', 'Notifies customers and staff 7 days before expiry'], ['overdue_scan', 'Overdue scan', 'Flags and notifies overdue invoices'],
    ['discount_housekeeping', 'Discount housekeeping', 'Deactivates expired or exhausted discount rules'],
  ]
  return (
    <div className="space-y-5">
      <Card title="Scheduled jobs" actions={<Button size="sm" variant="primary" icon={<Play className="h-4 w-4" />} loading={busy === 'all'} onClick={() => run('all', () => api<{ job: string }[]>('/admin/automation/all/run', { method: 'POST' }), 'All daily jobs ran')}>Run all now</Button>}>
        <p className="mb-4 text-[13px] text-ink-soft">The scheduler runs these automatically every day at <b>{String(st?.billing_time ?? '01:00')}</b>{st && !st.scheduler_enabled && <span className="text-bad"> (scheduler is disabled on this server)</span>}. Every job is idempotent — running it again never duplicates work.</p>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{jobs.map(([id, l, d]) => (
          <div key={id} className="flex items-start justify-between gap-3 rounded-lg border border-line p-3"><div><p className="font-semibold">{l}</p><p className="text-[12px] text-ink-soft">{d}</p></div>
            <Button size="sm" loading={busy === id} onClick={() => run(id, () => api<{ message: string }[]>(`/admin/automation/${id}/run`, { method: 'POST' }), (r) => r[0]?.message ?? 'Done')}>Run</Button></div>))}</div>
      </Card>
      <Card title="Run history" pad={false}>
        {isLoading ? <TableSkeleton /> : (
          <div className="overflow-x-auto"><table className="w-full min-w-[760px]"><thead><tr><th className="th">Job</th><th className="th">Trigger</th><th className="th">Status</th><th className="th">Result</th><th className="th">Started</th></tr></thead>
            <tbody>{data?.items.map((r) => <tr key={r.id}><td className="td font-semibold">{titleCase(r.job)}</td><td className="td text-[13px]">{titleCase(r.trigger)}</td><td className="td"><Status state={r.status} /></td><td className="td max-w-md text-[12px] text-ink-soft">{r.message}</td><td className="td text-[12px] text-ink-soft">{fdatetime(r.started_at)}</td></tr>)}</tbody></table></div>
        )}
        {data && <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} />}
      </Card>
    </div>
  )
}

function Settings() {
  const { data } = useApi<Record<string, string | boolean>>('/admin/settings')
  const { run } = useRunner()
  if (!data) return <TableSkeleton />
  return (
    <Card title="System settings" className="max-w-2xl">
      <div className="space-y-4">
        <Toggle checked={!!data.auto_confirm_invoices} onChange={(v) => run('s', () => api('/admin/settings', { method: 'PUT', body: { auto_confirm_invoices: v } }), 'Setting saved')}
          label="Auto-confirm generated invoices" hint="When off, the billing engine creates draft invoices for staff to review and confirm." />
        <dl className="grid gap-3 text-[13px] sm:grid-cols-2">
          {[['Company', data.company_name], ['Currency', data.currency], ['Email delivery', data.email_delivery], ['Daily automation', data.billing_time], ['Business date', data.business_date]].map(([k, v]) => (
            <div key={k as string} className="rounded-lg bg-canvas p-3"><dt className="label">{k}</dt><dd className="font-medium">{String(v)}</dd></div>))}
        </dl>
      </div>
    </Card>
  )
}

function Audit() {
  const [page, setPage] = useState(1)
  const { data, isLoading } = useApi<Page<{ id: number; action: string; entity: string; entity_id: number; detail: string | null; user: string; created_at: string }>>('/admin/audit', { page })
  return (
    <Card title="Audit log" pad={false}>
      {isLoading ? <TableSkeleton /> : <div className="overflow-x-auto"><table className="w-full min-w-[760px]"><thead><tr><th className="th">When</th><th className="th">User</th><th className="th">Action</th><th className="th">Record</th><th className="th">Detail</th></tr></thead>
        <tbody>{data?.items.map((a) => <tr key={a.id}><td className="td whitespace-nowrap text-[12px] text-ink-soft">{fdatetime(a.created_at)}</td><td className="td text-[13px]">{a.user}</td><td className="td"><code className="rounded bg-canvas px-1.5 py-0.5 text-[12px]">{a.action}</code></td><td className="td text-[13px]">{a.entity} #{a.entity_id}</td><td className="td max-w-xs truncate font-mono text-[11px] text-ink-soft" title={a.detail ?? ''}>{a.detail}</td></tr>)}</tbody></table></div>}
      {data && <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} />}
    </Card>
  )
}

function Outbox() {
  const [page, setPage] = useState(1)
  const { data, isLoading } = useApi<Page<{ id: number; to_address: string; subject: string; body: string; status: string; error: string | null; created_at: string }>>('/admin/outbox', { page })
  const [open, setOpen] = useState<number | null>(null)
  return (
    <Card title="Email outbox" pad={false}>
      <p className="flex items-center gap-2 border-b border-line px-5 py-2.5 text-[12px] text-ink-soft"><Mail className="h-4 w-4" />Every email the system tries to send is recorded here. <b>Not sent</b> means SMTP is not configured — the email was never delivered.</p>
      {isLoading ? <TableSkeleton /> : !data?.items.length ? <Empty title="No emails yet" /> : (
        <ul className="divide-y divide-line">{data.items.map((m) => (
          <li key={m.id} className="px-5 py-3">
            <button className="flex w-full items-center gap-3 text-left" onClick={() => setOpen(open === m.id ? null : m.id)}>
              <Status state={m.status} /><span className="flex-1"><b>{m.subject}</b><span className="block text-[12px] text-ink-soft">to {m.to_address}</span></span><span className="text-[12px] text-ink-faint">{fdatetime(m.created_at)}</span>
            </button>
            {open === m.id && <pre className="mt-2 whitespace-pre-wrap rounded-lg bg-canvas p-3 text-[12px]">{m.body}</pre>}
          </li>))}</ul>
      )}
      {data && <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} />}
    </Card>
  )
}

export default function Admin() {
  const [f, set] = useUrlFilters({ tab: 'users' })
  const tab = f.tab as Tab
  return (
    <>
      <PageHeader title="Administration" subtitle="Users and roles, tax rules, automation monitoring and system settings." />
      <div className="mb-5"><Tabs value={tab} onChange={(t) => set({ tab: t })} tabs={[{ id: 'users', label: 'Users & roles' }, { id: 'taxes', label: 'Taxes' }, { id: 'automation', label: 'Automation' }, { id: 'settings', label: 'Settings' }, { id: 'audit', label: 'Audit log' }, { id: 'outbox', label: 'Email outbox' }]} /></div>
      {tab === 'users' && <Users />}{tab === 'taxes' && <Taxes />}{tab === 'automation' && <Automation />}{tab === 'settings' && <Settings />}{tab === 'audit' && <Audit />}{tab === 'outbox' && <Outbox />}
    </>
  )
}
