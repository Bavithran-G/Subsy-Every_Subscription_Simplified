from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import ORM


class SubLineIn(BaseModel):
    product_id: int
    variant_id: int | None = None
    quantity: int = Field(ge=1, le=1_000_000)
    unit_price: Decimal | None = Field(default=None, ge=0)
    tax_id: int | None = None


class SubscriptionIn(BaseModel):
    customer_id: int
    plan_id: int
    template_id: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    payment_terms_days: int | None = Field(default=None, ge=0, le=365)
    valid_until: date | None = None
    notes: str | None = None
    lines: list[SubLineIn] = []


class SubscriptionUpdate(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    payment_terms_days: int | None = Field(default=None, ge=0, le=365)
    valid_until: date | None = None
    notes: str | None = None
    lines: list[SubLineIn] | None = None


class ActionIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    start_date: date | None = None
    days: int | None = Field(default=None, ge=1, le=365)


class SubLineOut(ORM):
    id: int
    product_id: int
    variant_id: int | None
    description: str
    quantity: int
    unit_price: Decimal
    tax_id: int | None
    tax_name: str | None = None
    subtotal: Decimal = Decimal(0)
    tax_amount: Decimal = Decimal(0)
    total: Decimal = Decimal(0)


class HistoryOut(ORM):
    id: int
    from_state: str | None
    to_state: str
    action: str
    reason: str | None
    user_name: str | None = None
    created_at: datetime


class RenewalOut(ORM):
    id: int
    previous_end_date: date
    new_end_date: date
    created_at: datetime


class SubscriptionRow(ORM):
    id: int
    number: str | None
    state: str
    customer_id: int
    customer_name: str
    plan_id: int
    plan_name: str
    billing_period: str
    quotation_date: date
    valid_until: date | None
    start_date: date | None
    end_date: date | None
    next_invoice_date: date | None
    total: Decimal
    is_expired_quotation: bool = False
    is_demo: bool


class BillingEventOut(ORM):
    id: int
    period_index: int
    period_start: date
    period_end: date
    status: str
    attempts: int
    error: str | None
    source: str
    invoice_id: int | None = None
    invoice_number: str | None = None
    created_at: datetime


class SubscriptionOut(SubscriptionRow):
    template_id: int | None
    payment_terms_days: int
    notes: str | None
    untaxed: Decimal
    tax: Decimal
    lines: list[SubLineOut]
    history: list[HistoryOut]
    renewals: list[RenewalOut]
    billing_events: list[BillingEventOut] = []
    plan: dict
    allowed_actions: list[str] = []
    customer_email: str


class InvoiceLineOut(ORM):
    id: int
    product_id: int | None
    description: str
    quantity: int
    unit_price: Decimal
    gross_amount: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    tax_name: str | None
    tax_type: str | None
    tax_rate: Decimal
    tax_amount: Decimal
    total: Decimal


class PaymentOut(ORM):
    id: int
    reference: str
    customer_id: int
    customer_name: str | None = None
    invoice_id: int
    invoice_number: str | None = None
    method: str
    amount: Decimal
    payment_date: date
    note: str | None
    status: str
    voided_reason: str | None
    recorded_by_name: str | None = None
    created_at: datetime


class InvoiceRow(ORM):
    id: int
    number: str | None
    state: str
    customer_id: int
    customer_name: str
    subscription_id: int | None
    subscription_number: str | None
    invoice_date: date
    due_date: date
    period_start: date | None
    period_end: date | None
    total: Decimal
    amount_paid: Decimal
    amount_due: Decimal
    is_overdue: bool
    is_demo: bool


class InvoiceOut(InvoiceRow):
    untaxed_amount: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    notes: str | None
    lines: list[InvoiceLineOut]
    payments: list[PaymentOut]
    discounts: list[dict]
    customer: dict
    confirmed_at: datetime | None
    paid_at: datetime | None
    sent_at: datetime | None
    allowed_actions: list[str] = []


class DiscountIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    discount_type: str = Field(pattern="^(fixed|percentage)$")
    value: Decimal = Field(gt=0, le=100_000_000)
    scope: str = Field(pattern="^(products|subscription)$")
    min_purchase: Decimal = Field(default=Decimal(0), ge=0)
    min_quantity: int = Field(default=0, ge=0)
    start_date: date | None = None
    end_date: date | None = None
    max_usage: int | None = Field(default=None, ge=1)
    is_active: bool = True
    product_ids: list[int] = []
    subscription_ids: list[int] = []


class DiscountOut(ORM):
    id: int
    name: str
    discount_type: str
    value: Decimal
    scope: str
    min_purchase: Decimal
    min_quantity: int
    start_date: date | None
    end_date: date | None
    max_usage: int | None
    is_active: bool
    product_ids: list[int] = []
    subscription_ids: list[int] = []
    usage_consumed: int = 0
    usage_reserved: int = 0
    total_discounted: Decimal = Decimal(0)
    status: str = "active"


class PaymentIn(BaseModel):
    invoice_id: int
    customer_id: int | None = None
    method: str = Field(pattern="^(bank_transfer|upi|card|cash|cheque|other)$")
    amount: Decimal = Field(gt=0)
    payment_date: date
    note: str | None = Field(default=None, max_length=1000)
    reference: str | None = Field(default=None, min_length=3, max_length=60)


class VoidIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
