export type Role = 'admin' | 'staff' | 'customer'
export interface User { id: number; email: string; full_name: string; role: Role; is_active: boolean; is_demo: boolean; created_at: string; last_login_at: string | null; customer_id: number | null }
export interface Page<T> { items: T[]; total: number; page: number; page_size: number }
export interface Msg { message: string; detail?: Record<string, unknown> | null }

export interface Tax { id: number; name: string; tax_type: 'percentage' | 'fixed'; rate: string; applicability: string; description: string | null; is_active: boolean }
export interface Variant { id: number; attribute: string; value: string; price_extra: string; is_active: boolean }
export interface Product { id: number; name: string; product_type: string; sales_price: string; cost_price: string; notes: string | null; tax_id: number | null; tax: Tax | null; is_active: boolean; variants: Variant[]; created_at: string }
export interface Line { id: number; product_id: number; variant_id: number | null; quantity: number; unit_price: string | null; product_name: string; variant_label: string | null; effective_price: string }
export interface Plan {
  id: number; name: string; description: string | null; billing_period: string; billing_interval: number; min_quantity: number
  start_date: string | null; end_date: string | null; term_periods: number | null; auto_close: boolean; closable: boolean
  pausable: boolean; renewable: boolean; is_active: boolean; lines: Line[]; price: string; subscription_count: number
}
export interface Template { id: number; name: string; plan_id: number; plan_name: string; validity_days: number; payment_terms_days: number; notes: string | null; is_active: boolean; lines: Line[] }
export interface Customer { id: number; name: string; email: string; phone: string | null; company: string | null; segment: string; address: string | null; gstin: string | null; user_id: number | null; is_demo: boolean; created_at: string; active_subscriptions?: number; outstanding?: string }

export interface SubRow {
  id: number; number: string; state: string; customer_id: number; customer_name: string; plan_id: number; plan_name: string
  billing_period: string; quotation_date: string; valid_until: string | null; start_date: string | null; end_date: string | null
  next_invoice_date: string | null; total: string; is_expired_quotation: boolean; is_demo: boolean
}
export interface SubLine { id: number; product_id: number; variant_id: number | null; description: string; quantity: number; unit_price: string; tax_id: number | null; tax_name: string | null; subtotal: string; tax_amount: string; total: string }
export interface History { id: number; from_state: string | null; to_state: string; action: string; reason: string | null; user_name: string; created_at: string }
export interface BillingEvent { id: number; period_index: number; period_start: string; period_end: string; status: string; attempts: number; error: string | null; source: string; invoice_id: number | null; invoice_number: string | null; created_at: string }
export interface Subscription extends SubRow {
  template_id: number | null; payment_terms_days: number; notes: string | null; untaxed: string; tax: string
  lines: SubLine[]; history: History[]; renewals: { id: number; previous_end_date: string; new_end_date: string; created_at: string }[]
  billing_events: BillingEvent[]; allowed_actions: string[]; customer_email: string
  plan: { id: number; name: string; billing_period: string; billing_interval: number; min_quantity: number; auto_close: boolean; closable: boolean; pausable: boolean; renewable: boolean; term_periods: number | null }
}
export interface InvRow { id: number; number: string; state: string; customer_id: number; customer_name: string; subscription_id: number | null; subscription_number: string | null; invoice_date: string; due_date: string; period_start: string | null; period_end: string | null; total: string; amount_paid: string; amount_due: string; is_overdue: boolean; is_demo: boolean }
export interface InvLine { id: number; product_id: number | null; description: string; quantity: number; unit_price: string; gross_amount: string; discount_amount: string; taxable_amount: string; tax_name: string | null; tax_type: string | null; tax_rate: string; tax_amount: string; total: string }
export interface Payment { id: number; reference: string; customer_id: number; customer_name: string; invoice_id: number; invoice_number: string; method: string; amount: string; payment_date: string; note: string | null; status: string; voided_reason: string | null; recorded_by_name: string | null; created_at: string }
export interface Invoice extends InvRow {
  untaxed_amount: string; discount_amount: string; tax_amount: string; notes: string | null; lines: InvLine[]; payments: Payment[]
  discounts: { name: string; type: string; value: string; amount: string }[]
  customer: { id: number; name: string; email: string; company: string | null; address: string | null; gstin: string | null }
  confirmed_at: string | null; paid_at: string | null; sent_at: string | null; allowed_actions: string[]
}
export interface Discount {
  id: number; name: string; discount_type: 'fixed' | 'percentage'; value: string; scope: 'products' | 'subscription'
  min_purchase: string; min_quantity: number; start_date: string | null; end_date: string | null; max_usage: number | null
  is_active: boolean; product_ids: number[]; subscription_ids: number[]; usage_consumed: number; usage_reserved: number
  total_discounted: string; status: string
}
export interface Notification { id: number; kind: string; title: string; body: string | null; link: string | null; is_read: boolean; created_at: string }
