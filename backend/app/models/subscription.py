from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import Money, SubState, TimestampMixin, utcnow


class Subscription(TimestampMixin, Base):
    """A subscription is the single aggregate that moves through the PS lifecycle:
    Draft -> Quotation -> Confirmed -> Active -> Closed (plus Paused, Cancelled).
    While in draft/quotation it *is* the quotation (with valid_until)."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint("end_date IS NULL OR start_date IS NULL OR end_date >= start_date", name="ck_sub_dates"),
        Index("ix_sub_billing_due", "state", "next_invoice_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True, nullable=False)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), index=True, nullable=False)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("quotation_templates.id"))
    state: Mapped[SubState] = mapped_column(Enum(SubState, name="sub_state"), default=SubState.draft, index=True)

    quotation_date: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, index=True)  # expiry date
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    # Billing schedule: period k starts at shift(billing_anchor, k * interval)
    billing_anchor: Mapped[date | None] = mapped_column(Date)
    next_period_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_invoice_date: Mapped[date | None] = mapped_column(Date)

    paused_on: Mapped[date | None] = mapped_column(Date)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    customer = relationship("Customer")
    plan = relationship("Plan")
    template = relationship("QuotationTemplate")
    lines = relationship(
        "SubscriptionLine", back_populates="subscription", cascade="all, delete-orphan",
        order_by="SubscriptionLine.id",
    )
    history = relationship(
        "SubscriptionHistory", back_populates="subscription", cascade="all, delete-orphan",
        order_by="SubscriptionHistory.id",
    )
    renewals = relationship(
        "SubscriptionRenewal", back_populates="subscription", cascade="all, delete-orphan",
        order_by="SubscriptionRenewal.id",
    )


class SubscriptionLine(Base):
    __tablename__ = "subscription_lines"
    __table_args__ = (
        CheckConstraint("quantity >= 1", name="ck_subline_qty"),
        CheckConstraint("unit_price >= 0", name="ck_subline_price"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("product_variants.id"))
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Money, nullable=False)  # snapshot incl. variant extra
    tax_id: Mapped[int | None] = mapped_column(ForeignKey("taxes.id"))

    subscription = relationship("Subscription", back_populates="lines")
    product = relationship("Product")
    variant = relationship("ProductVariant")
    tax = relationship("Tax")


class SubscriptionHistory(Base):
    __tablename__ = "subscription_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id", ondelete="CASCADE"), index=True)
    from_state: Mapped[str | None] = mapped_column(String(20))
    to_state: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    subscription = relationship("Subscription", back_populates="history")
    user = relationship("User")


class SubscriptionRenewal(Base):
    """One row per renewal; (subscription, previous_end_date) is unique so a renewal can't be applied twice."""

    __tablename__ = "subscription_renewals"
    __table_args__ = (UniqueConstraint("subscription_id", "previous_end_date", name="uq_renewal_once"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id", ondelete="CASCADE"), index=True)
    previous_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    new_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    subscription = relationship("Subscription", back_populates="renewals")
