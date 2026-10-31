"""Payment recording. Policy: overpayment is rejected; partial payments are allowed.
outstanding = invoice.total - sum(posted payments). An invoice becomes Paid only when outstanding reaches 0."""
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import clock
from app.core.money import ZERO, D, r2
from app.models import Invoice, InvoiceState, Payment, PaymentMethod, PaymentStatus, User
from app.models.base import utcnow
from app.services.common import audit, make_number, notify
from app.services.errors import Conflict, DomainError, NotFound


def _lock_invoice(db: Session, invoice_id: int) -> Invoice:
    stmt = select(Invoice).where(Invoice.id == invoice_id)
    if db.get_bind().dialect.name == "postgresql":
        stmt = stmt.with_for_update(of=Invoice)
    inv = db.scalars(stmt).first()
    if not inv:
        raise NotFound("Invoice not found")
    return inv


def _recompute(db: Session, inv: Invoice):
    paid = db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(
        Payment.invoice_id == inv.id, Payment.status == PaymentStatus.posted)) or ZERO
    inv.amount_paid = r2(paid)
    if inv.state in (InvoiceState.confirmed, InvoiceState.paid):
        if D(inv.amount_paid) >= D(inv.total):
            if inv.state != InvoiceState.paid:
                inv.state, inv.paid_at = InvoiceState.paid, utcnow()
        else:
            inv.state, inv.paid_at = InvoiceState.confirmed, None


def record_payment(db: Session, user: User, *, invoice_id: int, amount, method: PaymentMethod,
                   payment_date: date, note: str | None = None, reference: str | None = None,
                   customer_id: int | None = None) -> Payment:
    inv = _lock_invoice(db, invoice_id)
    if customer_id is not None and customer_id != inv.customer_id:
        raise DomainError("Invoice does not belong to the selected customer")
    if inv.state != InvoiceState.confirmed:
        raise DomainError(f"Payments can only be recorded against confirmed, unpaid invoices (invoice is {inv.state})")
    amount = r2(amount)
    if amount <= 0:
        raise DomainError("Payment amount must be positive")
    if payment_date > clock.today():
        raise DomainError("Payment date cannot be in the future")
    due = r2(D(inv.total) - D(inv.amount_paid))
    if amount > due:
        raise DomainError(f"Amount exceeds the outstanding balance of INR {due} (overpayments are not accepted)")
    if reference and db.scalar(select(Payment.id).where(Payment.reference == reference)):
        raise Conflict(f"Payment reference '{reference}' already exists")
    pay = Payment(reference=reference or f"TMP-{uuid.uuid4().hex}", customer_id=inv.customer_id,
                  invoice_id=inv.id, method=method, amount=amount, payment_date=payment_date, note=note,
                  recorded_by_id=user.id, status=PaymentStatus.posted, is_demo=inv.is_demo)
    try:
        with db.begin_nested():
            db.add(pay)
            db.flush()
    except IntegrityError:
        raise Conflict("Duplicate payment reference") from None
    if not reference:
        pay.reference = make_number("PAY", pay.id)
    _recompute(db, inv)
    audit(db, user.id, "payment.record", "payment", pay.id, invoice=inv.number, amount=str(amount),
          method=str(method))
    if inv.customer.user_id:
        notify(db, inv.customer.user_id, "payment", f"Payment received for {inv.number}",
               f"INR {amount} received. Outstanding: INR {inv.amount_due}", f"/portal/invoices/{inv.id}")
    return pay


def void_payment(db: Session, user: User, payment_id: int, reason: str) -> Payment:
    pay = db.get(Payment, payment_id)
    if not pay:
        raise NotFound("Payment not found")
    if pay.status == PaymentStatus.voided:
        raise DomainError("Payment is already voided")
    if not reason:
        raise DomainError("A reason is required to void a payment")
    inv = _lock_invoice(db, pay.invoice_id)
    pay.status, pay.voided_reason = PaymentStatus.voided, reason
    db.flush()
    _recompute(db, inv)
    audit(db, user.id, "payment.void", "payment", pay.id, reason=reason)
    return pay


def outstanding(inv: Invoice) -> Decimal:
    return r2(D(inv.total) - D(inv.amount_paid))
