import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Numeric
from sqlalchemy.orm import Mapped, mapped_column

Money = Numeric(14, 2)
Rate = Numeric(9, 4)


def utcnow() -> datetime:
    """Wall-clock UTC now — except when the business clock is frozen (tests, demo replay), in which case the
    frozen business date is used so timestamps line up with the business events they record."""
    from app.core import clock
    now = datetime.now(timezone.utc)
    if clock._frozen is not None:
        return datetime.combine(clock._frozen, now.timetz())
    return now


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class StrEnum(str, enum.Enum):
    def __str__(self) -> str:
        return self.value


class Role(StrEnum):
    admin = "admin"
    staff = "staff"
    customer = "customer"


class BillingPeriod(StrEnum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    yearly = "yearly"


class SubState(StrEnum):
    draft = "draft"
    quotation = "quotation"
    confirmed = "confirmed"
    active = "active"
    paused = "paused"
    closed = "closed"
    cancelled = "cancelled"


class InvoiceState(StrEnum):
    draft = "draft"
    confirmed = "confirmed"
    paid = "paid"
    cancelled = "cancelled"


class BillingEventStatus(StrEnum):
    pending = "pending"
    invoiced = "invoiced"
    failed = "failed"


class DiscountType(StrEnum):
    fixed = "fixed"
    percentage = "percentage"


class DiscountScope(StrEnum):
    products = "products"
    subscription = "subscription"


class TaxType(StrEnum):
    percentage = "percentage"
    fixed = "fixed"  # fixed amount per unit


class PaymentMethod(StrEnum):
    bank_transfer = "bank_transfer"
    upi = "upi"
    card = "card"
    cash = "cash"
    cheque = "cheque"
    other = "other"


class PaymentStatus(StrEnum):
    posted = "posted"
    voided = "voided"
