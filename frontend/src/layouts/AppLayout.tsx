import { clsx } from 'clsx'
import {
  BarChart3, Bell, Boxes, ChevronsLeft, ChevronsRight, CreditCard, FileText, LayoutDashboard, LogOut, Menu,
  Percent, Receipt, Repeat, Search, Settings, ShieldCheck, User as UserIcon, Users, Layers, X,
} from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { ago, titleCase } from '../lib/format'
import { useApi, useDebounced } from '../lib/hooks'
import type { Notification } from '../lib/types'
import { Wordmark } from '../components/Logo'

interface NavItem { to: string; label: string; icon: ReactNode; end?: boolean }
const I = (C: typeof Users) => <C className="h-[18px] w-[18px]" />

function navFor(role: string): { section?: string; items: NavItem[] }[] {
  if (role === 'customer') {
    return [{ items: [
      { to: '/portal', label: 'Overview', icon: I(LayoutDashboard), end: true },
      { to: '/portal/subscriptions', label: 'My subscriptions', icon: I(Repeat) },
      { to: '/portal/invoices', label: 'Invoices', icon: I(Receipt) },
      { to: '/portal/payments', label: 'Payments', icon: I(CreditCard) },
      { to: '/portal/profile', label: 'Profile', icon: I(UserIcon) },
    ] }]
  }
  const groups: { section?: string; items: NavItem[] }[] = [
    { items: [{ to: '/', label: 'Overview', icon: I(LayoutDashboard), end: true }] },
    { section: 'Sales', items: [
      { to: '/customers', label: 'Customers', icon: I(Users) },
      { to: '/quotations', label: 'Quotations', icon: I(FileText) },
      { to: '/subscriptions', label: 'Subscriptions', icon: I(Repeat) },
    ] },
    { section: 'Billing', items: [
      { to: '/invoices', label: 'Invoices', icon: I(Receipt) },
      { to: '/payments', label: 'Payments', icon: I(CreditCard) },
      { to: '/discounts', label: 'Discounts', icon: I(Percent) },
    ] },
    { section: 'Catalog', items: [
      { to: '/products', label: 'Products', icon: I(Boxes) },
      { to: '/plans', label: 'Plans', icon: I(Layers) },
    ] },
    { section: 'Insights', items: [{ to: '/reports', label: 'Reports & Analytics', icon: I(BarChart3) }] },
  ]
  if (role === 'admin') groups.push({ section: 'System', items: [{ to: '/admin', label: 'Administration', icon: I(Settings) }] })
  return groups
}

function SearchBox() {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const dq = useDebounced(q, 250)
  const nav = useNavigate()
  const { data } = useApi<Record<string, { id: number; label: string; sub: string }[]>>(dq.length >= 2 ? '/search' : null, { q: dq })
  const groups: [string, string][] = [['customers', '/customers'], ['subscriptions', '/subscriptions'], ['invoices', '/invoices']]
  const any = data && groups.some(([k]) => data[k]?.length)
  return (
    <div className="relative hidden w-full max-w-md md:block">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
      <input className="input h-9 pl-9" placeholder="Search customers, SUB- or INV- numbers…" value={q}
        onChange={(e) => { setQ(e.target.value); setOpen(true) }} onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)} aria-label="Global search" />
      {open && dq.length >= 2 && (
        <div className="absolute left-0 right-0 top-11 z-40 rounded-xl border border-line bg-white p-1.5 shadow-pop">
          {!any && <p className="px-3 py-2 text-[13px] text-ink-soft">No matches for “{dq}”</p>}
          {data && groups.map(([k, base]) => data[k]?.length ? (
            <div key={k}>
              <p className="px-3 pb-1 pt-2 text-[11px] font-bold uppercase tracking-wider text-ink-faint">{titleCase(k)}</p>
              {data[k].map((r) => (
                <button key={r.id} onMouseDown={() => { nav(`${base}/${r.id}`); setQ(''); setOpen(false) }}
                  className="flex w-full flex-col rounded-lg px-3 py-1.5 text-left hover:bg-brand-50">
                  <span className="font-semibold">{r.label}</span><span className="text-[12px] text-ink-soft">{r.sub}</span>
                </button>
              ))}
            </div>
          ) : null)}
        </div>
      )}
    </div>
  )
}

function Notifications() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const { data, refetch } = useApi<{ unread: number; items: Notification[] }>('/notifications', undefined, { refetchInterval: 60_000 })
  const nav = useNavigate()
  useEffect(() => {
    const h = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen(!open)} className="relative grid h-9 w-9 place-items-center rounded-lg text-ink-soft hover:bg-gray-100 hover:text-ink" aria-label="Notifications">
        <Bell className="h-[18px] w-[18px]" />
        {!!data?.unread && <span className="absolute right-1.5 top-1.5 grid h-4 min-w-4 place-items-center rounded-full bg-brand-600 px-1 text-[10px] font-bold text-white">{data.unread > 9 ? '9+' : data.unread}</span>}
      </button>
      {open && (
        <div className="absolute right-0 top-11 z-40 w-[min(360px,calc(100vw-1.5rem))] rounded-xl border border-line bg-white shadow-pop animate-fade-in">
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <p className="font-display font-bold">Notifications</p>
            {!!data?.unread && <button className="link text-[12px]" onClick={async () => { await api('/notifications/read-all', { method: 'POST' }); refetch() }}>Mark all read</button>}
          </div>
          <div className="max-h-96 overflow-y-auto">
            {!data?.items.length && <p className="px-4 py-8 text-center text-ink-soft">You're all caught up.</p>}
            {data?.items.map((n) => (
              <button key={n.id} onClick={() => { if (n.link) nav(n.link); setOpen(false) }} className={clsx('flex w-full gap-3 border-b border-line px-4 py-3 text-left last:border-0 hover:bg-canvas', !n.is_read && 'bg-brand-50/40')}>
                <span className={clsx('mt-1.5 h-2 w-2 shrink-0 rounded-full', n.is_read ? 'bg-transparent' : 'bg-brand-600')} />
                <span className="min-w-0"><span className="block font-semibold">{n.title}</span>{n.body && <span className="block text-[12px] text-ink-soft">{n.body}</span>}<span className="text-[11px] text-ink-faint">{ago(n.created_at)}</span></span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function ProfileMenu() {
  const { user, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const nav = useNavigate()
  const initials = user?.full_name.split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase()
  return (
    <div className="relative">
      <button onClick={() => setOpen(!open)} onBlur={() => setTimeout(() => setOpen(false), 150)} className="flex items-center gap-2 rounded-lg py-1 pl-1 pr-2 hover:bg-gray-100" aria-label="Account menu">
        <span className="grid h-8 w-8 place-items-center rounded-full bg-brand-100 text-[12px] font-bold text-brand-800">{initials}</span>
        <span className="hidden text-left leading-tight lg:block"><span className="block text-[13px] font-semibold">{user?.full_name}</span><span className="block text-[11px] capitalize text-ink-soft">{user?.role}</span></span>
      </button>
      {open && (
        <div className="absolute right-0 top-11 z-40 w-56 rounded-xl border border-line bg-white p-1.5 shadow-pop animate-fade-in">
          <p className="truncate px-3 py-2 text-[12px] text-ink-soft">{user?.email}</p>
          {user?.role === 'customer' && <button onMouseDown={() => nav('/portal/profile')} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 hover:bg-canvas"><UserIcon className="h-4 w-4" />Profile</button>}
          <button onMouseDown={() => nav('/account')} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 hover:bg-canvas"><ShieldCheck className="h-4 w-4" />Change password</button>
          <button onMouseDown={async () => { await logout(); nav('/login') }} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-bad hover:bg-brand-50"><LogOut className="h-4 w-4" />Sign out</button>
        </div>
      )}
    </div>
  )
}

export default function AppLayout() {
  const { user } = useAuth()
  const [collapsed, setCollapsed] = useState(() => { try { return localStorage.getItem('subsy.sidebar') === '1' } catch { return false } })
  const [mobile, setMobile] = useState(false)
  const loc = useLocation()
  useEffect(() => setMobile(false), [loc.pathname])
  useEffect(() => { try { localStorage.setItem('subsy.sidebar', collapsed ? '1' : '0') } catch { /* ignore */ } }, [collapsed])
  const groups = navFor(user!.role)

  const nav = (isCollapsed: boolean) => (
    <nav className="flex-1 space-y-4 overflow-y-auto px-3 py-4">
      {groups.map((g, i) => (
        <div key={i}>
          {g.section && !isCollapsed && <p className="mb-1 px-3 text-[10px] font-bold uppercase tracking-[.12em] text-ink-faint">{g.section}</p>}
          <div className="space-y-0.5">
            {g.items.map((it) => (
              <NavLink key={it.to} to={it.to} end={it.end} title={isCollapsed ? it.label : undefined}
                className={({ isActive }) => clsx('flex items-center gap-3 rounded-lg px-3 py-2 text-[14px] font-medium transition',
                  isCollapsed && 'justify-center px-0',
                  isActive ? 'bg-brand-50 text-brand-700 shadow-[inset_3px_0_0_#C62828]' : 'text-ink-soft hover:bg-gray-100 hover:text-ink')}>
                {it.icon}{!isCollapsed && <span>{it.label}</span>}
              </NavLink>
            ))}
          </div>
        </div>
      ))}
    </nav>
  )

  return (
    <div className="flex min-h-screen">
      <aside className={clsx('no-print sticky top-0 hidden h-screen shrink-0 flex-col border-r border-line bg-white transition-all md:flex', collapsed ? 'w-[72px]' : 'w-[248px]')}>
        <Link to={user!.role === 'customer' ? '/portal' : '/'} className={clsx('flex h-16 items-center border-b border-line', collapsed ? 'justify-center' : 'px-5')}><Wordmark collapsed={collapsed} /></Link>
        {nav(collapsed)}
        <button onClick={() => setCollapsed(!collapsed)} className="m-3 flex items-center justify-center gap-2 rounded-lg py-2 text-[12px] font-semibold text-ink-soft hover:bg-gray-100" aria-label="Toggle sidebar">
          {collapsed ? <ChevronsRight className="h-4 w-4" /> : <><ChevronsLeft className="h-4 w-4" />Collapse</>}
        </button>
      </aside>

      {mobile && (
        <div className="fixed inset-0 z-50 md:hidden" role="dialog">
          <div className="absolute inset-0 bg-gray-900/40" onClick={() => setMobile(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-72 flex-col bg-white shadow-pop animate-fade-in">
            <div className="flex h-16 items-center justify-between border-b border-line px-5"><Wordmark /><button onClick={() => setMobile(false)} aria-label="Close menu"><X className="h-5 w-5" /></button></div>
            {nav(false)}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="no-print sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-line bg-white/90 px-4 backdrop-blur md:px-6">
          <button className="grid h-9 w-9 place-items-center rounded-lg hover:bg-gray-100 md:hidden" onClick={() => setMobile(true)} aria-label="Open menu"><Menu className="h-5 w-5" /></button>
          <span className="md:hidden"><Wordmark collapsed /></span>
          {user!.role !== 'customer' ? <SearchBox /> : <p className="hidden text-ink-soft md:block">Customer portal</p>}
          <div className="ml-auto flex items-center gap-1"><Notifications /><ProfileMenu /></div>
        </header>
        <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 md:px-8 md:py-8"><Outlet /></main>
      </div>
    </div>
  )
}
