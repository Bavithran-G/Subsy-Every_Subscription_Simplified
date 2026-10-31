import { Loader2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import AppLayout from './layouts/AppLayout'
import { LogoMark } from './components/Logo'
import { Empty } from './components/ui'
import { useAuth } from './lib/auth'
import type { Role } from './lib/types'
import Admin from './pages/Admin'
import { Account, ForgotPassword, Login, Register, ResetPassword } from './pages/Auth'
import { Discounts, InvoiceDetail, Invoices, Payments } from './pages/Billing'
import { Plans, Products } from './pages/Catalog'
import Customers, { CustomerDetail } from './pages/Customers'
import Overview from './pages/Overview'
import { PortalHome, PortalInvoices, PortalPayments, PortalProfile, PortalSubscriptions } from './pages/Portal'
import Reports from './pages/Reports'
import { EditQuotation, NewQuotation, SubscriptionDetail, SubscriptionList } from './pages/Subscriptions'

function Splash() {
  return <div className="grid min-h-screen place-items-center"><div className="flex flex-col items-center gap-3"><LogoMark size={44} /><Loader2 className="h-5 w-5 animate-spin text-brand-600" /></div></div>
}

/** UX guard only — every API endpoint enforces the same role on the server. */
function Guard({ roles, children }: { roles?: Role[]; children: ReactNode }) {
  const { user, loading } = useAuth()
  const loc = useLocation()
  if (loading) return <Splash />
  if (!user) return <Navigate to="/login" state={{ from: loc }} replace />
  if (roles && !roles.includes(user.role)) return <Navigate to={user.role === 'customer' ? '/portal' : '/'} replace />
  return <>{children}</>
}
function PublicOnly({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <Splash />
  if (user) return <Navigate to={user.role === 'customer' ? '/portal' : '/'} replace />
  return <>{children}</>
}

const internal: Role[] = ['admin', 'staff']

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<PublicOnly><Login /></PublicOnly>} />
      <Route path="/register" element={<PublicOnly><Register /></PublicOnly>} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route element={<Guard><AppLayout /></Guard>}>
        <Route path="/account" element={<Account />} />
        <Route element={<Guard roles={internal}><OutletPass /></Guard>}>
          <Route path="/" element={<Overview />} />
          <Route path="/customers" element={<Customers />} />
          <Route path="/customers/:id" element={<CustomerDetail />} />
          <Route path="/products" element={<Products />} />
          <Route path="/plans" element={<Plans />} />
          <Route path="/quotations" element={<SubscriptionList mode="quotations" />} />
          <Route path="/quotations/new" element={<NewQuotation />} />
          <Route path="/quotations/:id" element={<SubscriptionDetail />} />
          <Route path="/quotations/:id/edit" element={<EditQuotation />} />
          <Route path="/subscriptions" element={<SubscriptionList mode="subscriptions" />} />
          <Route path="/subscriptions/:id" element={<SubscriptionDetail />} />
          <Route path="/invoices" element={<Invoices />} />
          <Route path="/invoices/:id" element={<InvoiceDetail />} />
          <Route path="/payments" element={<Payments />} />
          <Route path="/discounts" element={<Discounts />} />
          <Route path="/reports" element={<Reports />} />
        </Route>
        <Route path="/admin" element={<Guard roles={['admin']}><Admin /></Guard>} />
        <Route element={<Guard roles={['customer']}><OutletPass /></Guard>}>
          <Route path="/portal" element={<PortalHome />} />
          <Route path="/portal/subscriptions" element={<PortalSubscriptions />} />
          <Route path="/portal/subscriptions/:id" element={<SubscriptionDetail portal />} />
          <Route path="/portal/invoices" element={<PortalInvoices />} />
          <Route path="/portal/invoices/:id" element={<InvoiceDetail portal />} />
          <Route path="/portal/payments" element={<PortalPayments />} />
          <Route path="/portal/profile" element={<PortalProfile />} />
        </Route>
        <Route path="*" element={<Empty title="Page not found" body="The page you're looking for doesn't exist." />} />
      </Route>
    </Routes>
  )
}

function OutletPass() { return <Outlet /> }
