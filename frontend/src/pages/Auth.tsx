import { clsx } from 'clsx'
import { ArrowRight, Check, CheckCircle2, Mail, X } from 'lucide-react'
import { useState, type FormEvent, type ReactNode } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Wordmark } from '../components/Logo'
import { Button, Card, Field, PageHeader, useUi } from '../components/ui'
import { api } from '../lib/api'
import { PASSWORD_RULES, useAuth } from '../lib/auth'
import type { Msg, User } from '../lib/types'

function Shell({ title, subtitle, children }: { title: string; subtitle: ReactNode; children: ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      <div className="relative hidden overflow-hidden bg-brand-800 p-12 text-white lg:flex lg:flex-col">
        <div className="absolute -right-24 -top-24 h-96 w-96 rounded-full border-[40px] border-white/5" />
        <div className="absolute -bottom-32 -left-16 h-[28rem] w-[28rem] rounded-full border-[56px] border-brand-600/40" />
        <Wordmark light />
        <div className="relative mt-auto max-w-md">
          <p className="font-display text-[34px] font-extrabold leading-[1.1]">Plans, renewals, invoices and payments — finally in one place.</p>
          <ul className="mt-8 space-y-3 text-white/85">
            {['Recurring invoices generated automatically, never twice', 'Taxes and discounts applied by rule, not by memory', 'Customers manage their own subscriptions'].map((t) => (
              <li key={t} className="flex items-center gap-3"><span className="grid h-6 w-6 place-items-center rounded-full bg-white/15"><Check className="h-3.5 w-3.5" /></span>{t}</li>
            ))}
          </ul>
        </div>
        <p className="relative mt-12 text-[12px] text-white/50">Brightloop Software · powered by Subsy</p>
      </div>
      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-[400px] animate-fade-in">
          <div className="mb-8 lg:hidden"><Wordmark /></div>
          <h1 className="text-[26px] font-extrabold">{title}</h1>
          <p className="mb-7 mt-1 text-ink-soft">{subtitle}</p>
          {children}
        </div>
      </div>
    </div>
  )
}

export function PasswordChecklist({ pw }: { pw: string }) {
  return (
    <ul className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[12px]">
      {PASSWORD_RULES.map((r) => {
        const ok = r.test(pw)
        return <li key={r.label} className={clsx('flex items-center gap-1.5', ok ? 'text-ok' : 'text-ink-soft')}>{ok ? <Check className="h-3.5 w-3.5" /> : <X className="h-3.5 w-3.5 text-ink-faint" />}{r.label}</li>
      })}
    </ul>
  )
}
const pwValid = (p: string) => PASSWORD_RULES.every((r) => r.test(p))
const home = (u: User) => (u.role === 'customer' ? '/portal' : '/')

export function Login() {
  const { login } = useAuth()
  const nav = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setErr(''); setBusy(true)
    try { nav(home(await login(email, password))) } catch (x) { setErr((x as Error).message) } finally { setBusy(false) }
  }
  const demo = (e: string) => { setEmail(e); setPassword('Subsy@Demo2026') }
  return (
    <Shell title="Welcome back" subtitle="Sign in to your Subsy workspace.">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Email"><input className="input h-10" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
        <Field label="Password"><input className="input h-10" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
        {err && <p className="rounded-lg bg-brand-50 px-3 py-2 text-[13px] text-brand-800">{err}</p>}
        <div className="flex justify-end"><Link to="/forgot-password" className="link text-[13px]">Forgot password?</Link></div>
        <Button type="submit" variant="primary" loading={busy} className="h-10 w-full">Sign in <ArrowRight className="h-4 w-4" /></Button>
      </form>
      <p className="mt-6 text-center text-ink-soft">New to Brightloop? <Link to="/register" className="link">Create an account</Link></p>
      <div className="mt-8 rounded-xl border border-dashed border-line p-4">
        <p className="text-[11px] font-bold uppercase tracking-wider text-ink-faint">Demo accounts</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {[['Admin', 'admin@brightloop.demo'], ['Staff', 'staff@brightloop.demo'], ['Customer', 'priya@sparkshop.demo']].map(([l, e]) => (
            <button key={e} type="button" onClick={() => demo(e)} className="rounded-md bg-canvas px-2.5 py-1 text-[12px] font-semibold text-ink-soft hover:bg-brand-50 hover:text-brand-700">{l}</button>
          ))}
        </div>
        <p className="mt-2 text-[11px] text-ink-faint">Fills the form only. Available after running the demo seed.</p>
      </div>
    </Shell>
  )
}

export function Register() {
  const { register } = useAuth()
  const nav = useNavigate()
  const [f, setF] = useState({ full_name: '', email: '', company: '', phone: '', password: '', confirm: '' })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  const mismatch = f.confirm.length > 0 && f.confirm !== f.password
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setErr('')
    if (!pwValid(f.password)) return setErr('Password does not meet the requirements.')
    if (f.password !== f.confirm) return setErr('Passwords do not match.')
    setBusy(true)
    try {
      const u = await register({ full_name: f.full_name, email: f.email, password: f.password, company: f.company || undefined, phone: f.phone || undefined })
      nav(home(u))
    } catch (x) { setErr((x as Error).message) } finally { setBusy(false) }
  }
  return (
    <Shell title="Create your account" subtitle="View and manage your Brightloop subscriptions and invoices.">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Full name"><input className="input h-10" required minLength={2} value={f.full_name} onChange={set('full_name')} /></Field>
        <Field label="Email" hint="Each email can belong to only one account."><input className="input h-10" type="email" required value={f.email} onChange={set('email')} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Company"><input className="input h-10" value={f.company} onChange={set('company')} /></Field>
          <Field label="Phone"><input className="input h-10" value={f.phone} onChange={set('phone')} /></Field>
        </div>
        <Field label="Password"><input className="input h-10" type="password" autoComplete="new-password" required value={f.password} onChange={set('password')} /><PasswordChecklist pw={f.password} /></Field>
        <Field label="Confirm password" error={mismatch ? 'Passwords do not match' : undefined}><input className="input h-10" type="password" autoComplete="new-password" required value={f.confirm} onChange={set('confirm')} /></Field>
        {err && <p className="rounded-lg bg-brand-50 px-3 py-2 text-[13px] text-brand-800">{err}</p>}
        <Button type="submit" variant="primary" loading={busy} disabled={!pwValid(f.password) || mismatch} className="h-10 w-full">Create account</Button>
      </form>
      <p className="mt-6 text-center text-ink-soft">Already have an account? <Link to="/login" className="link">Sign in</Link></p>
    </Shell>
  )
}

export function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [res, setRes] = useState<Msg | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErr('')
    try { setRes(await api<Msg>('/auth/forgot-password', { body: { email } })) } catch (x) { setErr((x as Error).message) } finally { setBusy(false) }
  }
  return (
    <Shell title="Reset your password" subtitle="We'll issue a reset link for your registered email address.">
      {res ? (
        <div className="space-y-4">
          <div className="flex gap-3 rounded-xl bg-ok-soft p-4 text-ok"><Mail className="h-5 w-5 shrink-0" /><p className="text-[13px] font-medium">{res.message}</p></div>
          {res.detail?.email_delivery === 'outbox' && (
            <p className="rounded-xl border border-warn/30 bg-warn-soft p-4 text-[13px] text-[#8a4b05]">
              <b>Email delivery is not configured on this server</b>, so no email was actually sent. An administrator can find the reset link in <b>Administration → Email outbox</b>, or in the server log.
            </p>
          )}
          <Link to="/login" className="link block text-center">Back to sign in</Link>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <Field label="Email"><input className="input h-10" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
          {err && <p className="text-[13px] text-bad">{err}</p>}
          <Button type="submit" variant="primary" loading={busy} className="h-10 w-full">Send reset link</Button>
          <Link to="/login" className="link block text-center text-[13px]">Back to sign in</Link>
        </form>
      )}
    </Shell>
  )
}

export function ResetPassword() {
  const [sp] = useSearchParams()
  const token = sp.get('token') ?? ''
  const [pw, setPw] = useState('')
  const [done, setDone] = useState(false)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErr('')
    try { await api('/auth/reset-password', { body: { token, password: pw } }); setDone(true) } catch (x) { setErr((x as Error).message) } finally { setBusy(false) }
  }
  return (
    <Shell title="Choose a new password" subtitle="Reset links expire after 30 minutes and work once.">
      {done ? (
        <div className="space-y-4"><div className="flex gap-3 rounded-xl bg-ok-soft p-4 text-ok"><CheckCircle2 className="h-5 w-5" /><p className="font-medium">Password updated.</p></div><Link to="/login" className="link block text-center">Sign in</Link></div>
      ) : !token ? <p className="text-bad">This link is missing its reset token.</p> : (
        <form onSubmit={submit} className="space-y-4">
          <Field label="New password"><input className="input h-10" type="password" required value={pw} onChange={(e) => setPw(e.target.value)} /><PasswordChecklist pw={pw} /></Field>
          {err && <p className="rounded-lg bg-brand-50 px-3 py-2 text-[13px] text-brand-800">{err}</p>}
          <Button type="submit" variant="primary" loading={busy} disabled={!pwValid(pw)} className="h-10 w-full">Update password</Button>
        </form>
      )}
    </Shell>
  )
}

export function Account() {
  const { setSession } = useAuth()
  const { toast } = useUi()
  const [cur, setCur] = useState('')
  const [pw, setPw] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true)
    try {
      const r = await api<{ access_token: string; user: User }>('/auth/change-password', { body: { current_password: cur, new_password: pw } })
      setSession(r.access_token, r.user); setCur(''); setPw('')
      toast('success', 'Password changed. Other sessions have been signed out.')
    } catch (x) { toast('error', (x as Error).message) } finally { setBusy(false) }
  }
  return (
    <>
      <PageHeader title="Account security" subtitle="Change your password. All other sessions are signed out." />
      <Card className="max-w-lg">
        <form onSubmit={submit} className="space-y-4">
          <Field label="Current password"><input className="input" type="password" required value={cur} onChange={(e) => setCur(e.target.value)} /></Field>
          <Field label="New password"><input className="input" type="password" required value={pw} onChange={(e) => setPw(e.target.value)} /><PasswordChecklist pw={pw} /></Field>
          <Button variant="primary" type="submit" loading={busy} disabled={!pwValid(pw)}>Update password</Button>
        </form>
      </Card>
    </>
  )
}
