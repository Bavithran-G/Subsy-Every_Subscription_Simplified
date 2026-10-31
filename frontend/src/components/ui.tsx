import { clsx } from 'clsx'
import { AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, Info, Loader2, X, XCircle } from 'lucide-react'
import {
  createContext, useCallback, useContext, useEffect, useRef, useState,
  type ButtonHTMLAttributes, type ReactNode,
} from 'react'
import { Link } from 'react-router-dom'
import { titleCase } from '../lib/format'

/* ---------------- Button ---------------- */
type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'success'
export function Button({ variant = 'secondary', size = 'md', loading, icon, children, className, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: 'sm' | 'md'; loading?: boolean; icon?: ReactNode }) {
  return (
    <button
      {...rest}
      disabled={rest.disabled || loading}
      className={clsx(
        'inline-flex items-center justify-center gap-1.5 rounded-lg font-semibold transition-all select-none whitespace-nowrap',
        'disabled:opacity-50 disabled:cursor-not-allowed active:scale-[.98]',
        size === 'sm' ? 'h-8 px-3 text-[13px]' : 'h-9 px-4 text-[14px]',
        variant === 'primary' && 'bg-brand-600 text-white hover:bg-brand-700 shadow-sm shadow-brand-900/10',
        variant === 'secondary' && 'bg-white text-ink border border-line hover:bg-canvas hover:border-gray-300',
        variant === 'ghost' && 'text-ink-soft hover:bg-gray-100 hover:text-ink',
        variant === 'danger' && 'bg-white text-bad border border-brand-200 hover:bg-brand-50',
        variant === 'success' && 'bg-ok text-white hover:brightness-95',
        className,
      )}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : icon}
      {children}
    </button>
  )
}

/* ---------------- Status badge ---------------- */
const tone: Record<string, string> = {
  green: 'bg-ok-soft text-ok ring-ok/20', amber: 'bg-warn-soft text-warn ring-warn/20', red: 'bg-bad-soft text-bad ring-bad/20',
  blue: 'bg-info-soft text-info ring-info/20', gray: 'bg-gray-100 text-ink-soft ring-gray-300/40', brand: 'bg-brand-100 text-brand-800 ring-brand-300/40',
}
const stateTone: Record<string, keyof typeof tone> = {
  draft: 'gray', quotation: 'blue', confirmed: 'brand', active: 'green', paused: 'amber', closed: 'gray', cancelled: 'gray',
  paid: 'green', overdue: 'red', invoiced: 'green', failed: 'red', pending: 'amber', posted: 'green', voided: 'gray',
  success: 'green', partial: 'amber', skipped: 'gray', running: 'blue', expired: 'red', exhausted: 'amber', scheduled: 'blue',
  inactive: 'gray', admin: 'brand', staff: 'blue', customer: 'gray', sent: 'green', not_sent: 'amber',
}
export function Badge({ children, color = 'gray', dot = true, className }: { children: ReactNode; color?: keyof typeof tone; dot?: boolean; className?: string }) {
  return (
    <span className={clsx('inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[12px] font-semibold ring-1 ring-inset whitespace-nowrap', tone[color], className)}>
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current opacity-80" />}
      {children}
    </span>
  )
}
export function Status({ state, label }: { state: string; label?: string }) {
  return <Badge color={stateTone[state] ?? 'gray'}>{label ?? titleCase(state)}</Badge>
}
export const DemoTag = () => <span title="Demonstration data" className="ml-1.5 rounded bg-gray-100 px-1 py-px text-[10px] font-bold uppercase tracking-wide text-ink-faint">demo</span>

/* ---------------- Layout pieces ---------------- */
export function PageHeader({ title, subtitle, actions, crumbs }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; crumbs?: { label: string; to?: string }[] }) {
  return (
    <div className="mb-6 animate-fade-in">
      {crumbs && (
        <nav className="mb-1.5 flex items-center gap-1 text-[12px] text-ink-soft" aria-label="Breadcrumb">
          {crumbs.map((c, i) => (
            <span key={i} className="flex items-center gap-1">
              {i > 0 && <ChevronRight className="h-3 w-3 text-ink-faint" />}
              {c.to ? <Link to={c.to} className="hover:text-brand-700">{c.label}</Link> : <span className="text-ink">{c.label}</span>}
            </span>
          ))}
        </nav>
      )}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-[22px] font-bold leading-tight">{title}</h1>
          {subtitle && <p className="mt-1 text-ink-soft">{subtitle}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </div>
  )
}

export function Card({ title, actions, children, className, pad = true }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; pad?: boolean }) {
  return (
    <section className={clsx('card animate-fade-in', className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-3.5">
          <h2 className="text-[15px] font-bold">{title}</h2>
          {actions}
        </header>
      )}
      <div className={clsx(pad && 'p-5')}>{children}</div>
    </section>
  )
}

export function Field({ label, error, hint, children, className }: { label: string; error?: string; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={clsx('block', className)}>
      <span className="label">{label}</span>
      {children}
      {error ? <span className="mt-1 block text-[12px] text-bad">{error}</span> : hint ? <span className="mt-1 block text-[12px] text-ink-soft">{hint}</span> : null}
    </label>
  )
}

export function Toggle({ checked, onChange, label, hint, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; hint?: string; disabled?: boolean }) {
  return (
    <label className={clsx('flex items-start gap-3 rounded-lg border border-line p-3 transition', checked && 'border-brand-200 bg-brand-50/50', disabled ? 'opacity-60' : 'cursor-pointer hover:border-gray-300')}>
      <button type="button" role="switch" aria-checked={checked} disabled={disabled} onClick={() => onChange(!checked)}
        className={clsx('relative mt-0.5 h-5 w-9 shrink-0 rounded-full transition', checked ? 'bg-brand-600' : 'bg-gray-300')}>
        <span className={clsx('absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all', checked ? 'left-[18px]' : 'left-0.5')} />
      </button>
      <span><span className="block font-semibold">{label}</span>{hint && <span className="block text-[12px] text-ink-soft">{hint}</span>}</span>
    </label>
  )
}

export function Skeleton({ className }: { className?: string }) { return <div className={clsx('skeleton', className)} /> }
export function TableSkeleton({ rows = 6, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-3 p-5">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-4">{Array.from({ length: cols }).map((_, j) => <Skeleton key={j} className="h-4 flex-1" />)}</div>
      ))}
    </div>
  )
}

export function Empty({ icon, title, body, action }: { icon?: ReactNode; title: string; body?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      <div className="mb-3 grid h-12 w-12 place-items-center rounded-full bg-brand-50 text-brand-600">{icon ?? <Info className="h-5 w-5" />}</div>
      <p className="font-display text-[15px] font-bold">{title}</p>
      {body && <p className="mt-1 max-w-sm text-ink-soft">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-brand-200 bg-brand-50 p-4 text-brand-900">
      <XCircle className="mt-0.5 h-5 w-5 shrink-0" />
      <div className="flex-1"><p className="font-semibold">Something went wrong</p><p className="text-[13px]">{(error as Error)?.message ?? String(error)}</p></div>
      {onRetry && <Button size="sm" onClick={onRetry}>Retry</Button>}
    </div>
  )
}

export function Pagination({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  if (total === 0) return null
  return (
    <div className="flex items-center justify-between gap-3 border-t border-line px-4 py-3 text-[13px] text-ink-soft">
      <span>{(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} of {total.toLocaleString('en-IN')}</span>
      <div className="flex items-center gap-1">
        <Button size="sm" variant="ghost" disabled={page <= 1} onClick={() => onPage(page - 1)} icon={<ChevronLeft className="h-4 w-4" />} aria-label="Previous page" />
        <span className="px-2">Page {page} of {pages}</span>
        <Button size="sm" variant="ghost" disabled={page >= pages} onClick={() => onPage(page + 1)} icon={<ChevronRight className="h-4 w-4" />} aria-label="Next page" />
      </div>
    </div>
  )
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: string; count?: number }[]; value: T; onChange: (t: T) => void }) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-line" role="tablist">
      {tabs.map((t) => (
        <button key={t.id} role="tab" aria-selected={value === t.id} onClick={() => onChange(t.id)}
          className={clsx('relative -mb-px whitespace-nowrap border-b-2 px-3 py-2.5 text-[13px] font-semibold transition',
            value === t.id ? 'border-brand-600 text-brand-700' : 'border-transparent text-ink-soft hover:text-ink')}>
          {t.label}{t.count !== undefined && <span className="ml-1.5 rounded-full bg-gray-100 px-1.5 text-[11px] text-ink-soft">{t.count}</span>}
        </button>
      ))}
    </div>
  )
}

/* ---------------- KPI ---------------- */
function useCountUp(target: number, ms = 600) {
  const [v, setV] = useState(0)
  useEffect(() => {
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (reduce) { setV(target); return }
    let raf = 0
    const start = performance.now()
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / ms)
      setV(target * (1 - Math.pow(1 - p, 3)))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, ms])
  return v
}
export function Kpi({ label, value, format = (n) => Math.round(n).toLocaleString('en-IN'), sub, to, tone: t = 'default', icon }:
  { label: string; value: number; format?: (n: number) => string; sub?: ReactNode; to?: string; tone?: 'default' | 'good' | 'warn' | 'bad'; icon?: ReactNode }) {
  const v = useCountUp(value)
  const body = (
    <div className={clsx('card group h-full p-4 transition', to && 'hover:-translate-y-px hover:border-brand-200 hover:shadow-pop')}>
      <div className="flex items-center justify-between text-[12px] font-semibold uppercase tracking-wide text-ink-soft">
        <span>{label}</span>
        <span className={clsx('grid h-7 w-7 place-items-center rounded-lg',
          t === 'good' ? 'bg-ok-soft text-ok' : t === 'warn' ? 'bg-warn-soft text-warn' : t === 'bad' ? 'bg-bad-soft text-bad' : 'bg-brand-50 text-brand-600')}>{icon}</span>
      </div>
      <div className="mt-2 font-display text-[24px] font-bold leading-none num">{format(v)}</div>
      {sub && <div className="mt-1.5 text-[12px] text-ink-soft">{sub}</div>}
    </div>
  )
  return to ? <Link to={to} className="block">{body}</Link> : body
}

/* ---------------- Modal ---------------- */
export function Modal({ open, onClose, title, children, footer, wide }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    ref.current?.querySelector<HTMLElement>('input,select,textarea,button')?.focus()
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-gray-900/40 p-0 backdrop-blur-[1px] sm:items-center sm:p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} role="dialog" aria-modal="true" className={clsx('flex max-h-[92vh] w-full flex-col rounded-t-2xl bg-white shadow-pop animate-fade-in sm:rounded-2xl', wide ? 'sm:max-w-3xl' : 'sm:max-w-lg')}>
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h3 className="text-[16px] font-bold">{title}</h3>
          <button onClick={onClose} className="rounded-md p-1 text-ink-soft hover:bg-gray-100" aria-label="Close"><X className="h-5 w-5" /></button>
        </div>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-line bg-canvas/60 px-5 py-3">{footer}</div>}
      </div>
    </div>
  )
}

/* ---------------- Toasts & confirm ---------------- */
type ToastKind = 'success' | 'error' | 'info' | 'warning'
interface ToastItem { id: number; kind: ToastKind; text: string }
interface ConfirmOpts { title: string; body?: ReactNode; confirmLabel?: string; danger?: boolean; reason?: { label: string; required?: boolean } }
interface UiCtx { toast: (kind: ToastKind, text: string) => void; confirm: (o: ConfirmOpts) => Promise<{ ok: boolean; reason?: string }> }
const Ui = createContext<UiCtx | null>(null)

export function UiProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const [dlg, setDlg] = useState<(ConfirmOpts & { resolve: (r: { ok: boolean; reason?: string }) => void }) | null>(null)
  const [reason, setReason] = useState('')
  const toast = useCallback((kind: ToastKind, text: string) => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t, { id, kind, text }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === 'error' ? 7000 : 4500)
  }, [])
  const confirm = useCallback((o: ConfirmOpts) => new Promise<{ ok: boolean; reason?: string }>((resolve) => { setReason(''); setDlg({ ...o, resolve }) }), [])
  const close = (ok: boolean) => { dlg?.resolve({ ok, reason: reason.trim() || undefined }); setDlg(null) }
  const icons = { success: <CheckCircle2 className="h-5 w-5 text-ok" />, error: <XCircle className="h-5 w-5 text-bad" />, info: <Info className="h-5 w-5 text-info" />, warning: <AlertTriangle className="h-5 w-5 text-warn" /> }
  return (
    <Ui.Provider value={{ toast, confirm }}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[min(380px,calc(100vw-2rem))] flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className="pointer-events-auto flex items-start gap-3 rounded-xl border border-line bg-white p-3.5 shadow-pop animate-fade-in">
            {icons[t.kind]}<p className="flex-1 text-[13px]">{t.text}</p>
            <button onClick={() => setToasts((x) => x.filter((y) => y.id !== t.id))} className="text-ink-faint hover:text-ink" aria-label="Dismiss"><X className="h-4 w-4" /></button>
          </div>
        ))}
      </div>
      <Modal open={!!dlg} onClose={() => close(false)} title={dlg?.title}
        footer={<>
          <Button onClick={() => close(false)}>Cancel</Button>
          <Button variant={dlg?.danger ? 'danger' : 'primary'} disabled={dlg?.reason?.required && !reason.trim()} onClick={() => close(true)}>{dlg?.confirmLabel ?? 'Confirm'}</Button>
        </>}>
        <div className="space-y-3 text-ink-soft">
          {dlg?.body}
          {dlg?.reason && <Field label={dlg.reason.label}><textarea className="input" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>}
        </div>
      </Modal>
    </Ui.Provider>
  )
}
export function useUi() {
  const c = useContext(Ui)
  if (!c) throw new Error('useUi outside UiProvider')
  return c
}
