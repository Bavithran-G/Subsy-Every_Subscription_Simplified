from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, DateTime, Enum, ForeignKey, Index, Integer, String, Table, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import (
    BillingEventStatus, DiscountScope, DiscountType, InvoiceState, Money, PaymentMethod, PaymentStatus, Rate,
    TimestampMixin, utcnow,
)


class BillingEvent(TimestampMixin, Base):
    """The immutable identity of one billing period of one subscription.
    UNIQUE(subscription_id, period_start) is what makes duplicate billing impossible."""

    __tablename__ = "billing_events"
    __table_args__ = (UniqueConstraint("subscription_id", "period_start", name="uq_billing_event_period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"), index=True, nullable=False)
    period_index: Mapped[int] = mapped_column(Integer, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[BillingEventStatus] = mapped_column(
        Enum(BillingEventStatus, name="billing_event_status"), default=BillingEventStatus.pending, index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), default="scheduler", nullable=False)  # scheduler | manual

    subscription = relationship("Subscription")
    invoice = relationship("Invoice", back_populates="billing_event", uselist=False)


class Invoice(TimestampMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint("amount_paid >= 0", name="ck_inv_paid_nonneg"),
        CheckConstraint("amount_paid <= total", name="ck_inv_no_overpay"),
        CheckConstraint("total >= 0", name="ck_inv_total_nonneg"),
        Index("ix_inv_state_due", "state", "due_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True, nullable=False)
    subscription_id: Mapped[int | None] = mapped_column(ForeignKey("subscriptions.id"), index=True)
    billing_event_id: Mapped[int | None] = mapped_column(ForeignKey("billing_events.id"), unique=True)
    state: Mapped[InvoiceState] = mapped_column(Enum(InvoiceState, name="invoice_state"), default=InvoiceState.draft)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    untaxed_amount: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)  # before discount
    discount_amount: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    total: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    customer = relationship("Customer")
    subscription = relationship("Subscription")
    billing_event = relationship("BillingEvent", back_populates="invoice")
    lines = relationship("InvoiceLine", back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceLine.id")
    payments = relationship("Payment", back_populates="invoice", order_by="Payment.id")
    discount_applications = relationship("DiscountApplication", back_populates="invoice", cascade="all, delete-orphan")

    @property
    def amount_due(self) -> Decimal:
        return (self.total or 0) - (self.amount_paid or 0)


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), index=True)
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("product_variants.id"))
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    gross_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)  # qty * unit_price
    discount_amount: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    taxable_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)  # gross - discount
    tax_id: Mapped[int | None] = mapped_column(ForeignKey("taxes.id"))
    tax_name: Mapped[str | None] = mapped_column(String(80))
    tax_type: Mapped[str | None] = mapped_column(String(20))
    tax_rate: Mapped[Decimal] = mapped_column(Rate, default=0, nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    total: Mapped[Decimal] = mapped_column(Money, nullable=False)

    invoice = relationship("Invoice", back_populates="lines")
    product = relationship("Product")


discount_products = Table(
    "discount_rule_products", Base.metadata,
    Column("discount_id", ForeignKey("discount_rules.id", ondelete="CASCADE"), primary_key=True),
    Column("product_id", ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
)
discount_subscriptions = Table(
    "discount_rule_subscriptions", Base.metadata,
    Column("discount_id", ForeignKey("discount_rules.id", ondelete="CASCADE"), primary_key=True),
    Column("subscription_id", ForeignKey("subscriptions.id", ondelete="CASCADE"), primary_key=True),
)


class DiscountRule(TimestampMixin, Base):
    __tablename__ = "discount_rules"
    __table_args__ = (
        CheckConstraint("value > 0", name="ck_disc_value_pos"),
        CheckConstraint("discount_type <> 'percentage' OR value <= 100", name="ck_disc_pct_max"),
        CheckConstraint("end_date IS NULL OR start_date IS NULL OR end_date >= start_date", name="ck_disc_dates"),
        CheckConstraint("max_usage IS NULL OR max_usage >= 1", name="ck_disc_max_usage"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    discount_type: Mapped[DiscountType] = mapped_column(Enum(DiscountType, name="discount_type"), nullable=False)
    value: Mapped[Decimal] = mapped_column(Money, nullable=False)
    scope: Mapped[DiscountScope] = mapped_column(Enum(DiscountScope, name="discount_scope"), nullable=False)
    min_purchase: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    min_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    max_usage: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    products = relationship("Product", secondary=discount_products)
    subscriptions = relationship("Subscription", secondary=discount_subscriptions)
    applications = relationship("DiscountApplication", back_populates="discount")


class DiscountApplication(Base):
    """A discount applied to one invoice. Usage is *consumed* only while the invoice is confirmed/paid;
    an application on a draft invoice reserves a slot; cancelling the invoice releases it."""

    __tablename__ = "discount_applications"
    __table_args__ = (UniqueConstraint("discount_id", "invoice_id", name="uq_discount_once_per_invoice"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    discount_id: Mapped[int] = mapped_column(ForeignKey("discount_rules.id"), index=True, nullable=False)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    discount = relationship("DiscountRule", back_populates="applications")
    invoice = relationship("Invoice", back_populates="discount_applications")


class Payment(TimestampMixin, Base):
    """A payment is allocated to exactly one invoice (1:1 allocation, the PS's 'against the right invoice')."""

    __tablename__ = "payments"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_payment_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True, nullable=False)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True, nullable=False)
    method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod, name="payment_method"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus, name="payment_status"), default=PaymentStatus.posted)
    recorded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    voided_reason: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    customer = relationship("Customer")
    invoice = relationship("Invoice", back_populates="payments")
    recorded_by = relationship("User")
