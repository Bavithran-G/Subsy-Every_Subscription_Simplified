from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.money import ZERO, D, r2
from app.models import (
    BillingEvent, DiscountApplication, Invoice, InvoiceLine, InvoiceState, Subscription, User,
)
from app.models.base import utcnow
from app.services.common import audit, get_setting, make_number, notify, send_email
from app.services.discounts import DraftLine, apply_discounts
from app.services.errors import DomainError
from app.services.pricing import line_amounts


def build_invoice_for_period(db: Session, sub: Subscription, event: BillingEvent, user: User | None) -> Invoice:
    """Create one invoice for one billing event. Lines are copied from the subscription (prices are the
    snapshot agreed in the quotation), discounts are applied automatically, taxes come from the tax rules."""
    if not sub.lines:
        raise DomainError(f"Subscription {sub.number} has no lines to bill")
    invoice_date = event.period_start
    drafts = [DraftLine(l.product_id, l.quantity, r2(D(l.unit_price) * l.quantity)) for l in sub.lines]
    applied = apply_discounts(db, drafts, on=invoice_date, subscription_id=sub.id)

    inv = Invoice(
        customer_id=sub.customer_id, subscription_id=sub.id, billing_event_id=event.id,
        state=InvoiceState.draft, invoice_date=invoice_date,
        due_date=invoice_date + timedelta(days=sub.payment_terms_days),
        period_start=event.period_start, period_end=event.period_end, is_demo=sub.is_demo,
    )
    untaxed = discount = tax_total = ZERO
    for sl, dl in zip(sub.lines, drafts):
        a = line_amounts(sl.quantity, sl.unit_price, sl.tax, dl.discount)
        inv.lines.append(InvoiceLine(
            product_id=sl.product_id, variant_id=sl.variant_id, description=sl.description,
            quantity=sl.quantity, unit_price=sl.unit_price, gross_amount=a.gross, discount_amount=a.discount,
            taxable_amount=a.taxable, tax_id=sl.tax_id, tax_name=sl.tax.name if sl.tax else None,
            tax_type=str(sl.tax.tax_type) if sl.tax else None, tax_rate=sl.tax.rate if sl.tax else 0,
            tax_amount=a.tax, total=a.total,
        ))
        untaxed += a.gross
        discount += a.discount
        tax_total += a.tax
    inv.untaxed_amount, inv.discount_amount, inv.tax_amount = untaxed, discount, tax_total
    inv.total = untaxed - discount + tax_total
    if inv.total < 0:  # defensive; discounts are capped per line so this cannot happen
        raise DomainError("Invoice total cannot be negative")
    db.add(inv)
    db.flush()
    inv.number = make_number("INV", inv.id)
    for ad in applied:
        db.add(DiscountApplication(discount_id=ad.rule.id, invoice_id=inv.id, amount=ad.amount))
    audit(db, user.id if user else None, "invoice.generate", "invoice", inv.id,
          subscription=sub.number, period=f"{event.period_start}..{event.period_end}")
    if get_setting(db, "auto_confirm_invoices") == "true":
        confirm_invoice(db, user, inv)
    elif sub.customer.user_id:
        pass  # customers are notified when the invoice is confirmed (drafts are internal)
    return inv


def confirm_invoice(db: Session, user: User | None, inv: Invoice):
    if inv.state != InvoiceState.draft:
        raise DomainError(f"Only draft invoices can be confirmed (invoice is {inv.state})")
    if not inv.lines:
        raise DomainError("Cannot confirm an empty invoice")
    inv.state = InvoiceState.confirmed
    inv.confirmed_at = utcnow()
    if inv.total == 0:
        inv.state, inv.paid_at = InvoiceState.paid, utcnow()
    audit(db, user.id if user else None, "invoice.confirm", "invoice", inv.id, total=str(inv.total))
    if inv.customer.user_id:
        notify(db, inv.customer.user_id, "invoice", f"New invoice {inv.number}",
               f"Amount due INR {inv.amount_due} by {inv.due_date}", f"/portal/invoices/{inv.id}",
               dedupe_key=f"inv-confirmed-{inv.id}")


def cancel_invoice(db: Session, user: User, inv: Invoice, reason: str | None = None):
    if inv.state not in (InvoiceState.draft, InvoiceState.confirmed):
        raise DomainError(f"Invoice in state '{inv.state}' cannot be cancelled")
    if D(inv.amount_paid) > 0:
        raise DomainError("Invoice has payments recorded — void the payments before cancelling")
    inv.state = InvoiceState.cancelled
    inv.cancelled_at = utcnow()
    inv.notes = ((inv.notes or "") + f"\nCancelled: {reason}").strip() if reason else inv.notes
    audit(db, user.id, "invoice.cancel", "invoice", inv.id, reason=reason)


def send_invoice(db: Session, user: User, inv: Invoice) -> str:
    if inv.state not in (InvoiceState.confirmed, InvoiceState.paid):
        raise DomainError("Confirm the invoice before sending it")
    row = send_email(db, inv.customer.email, f"Invoice {inv.number} from Brightloop Software",
                     f"Dear {inv.customer.name},\n\nInvoice {inv.number} for INR {inv.total} "
                     f"is due on {inv.due_date}.\nAmount outstanding: INR {inv.amount_due}\n")
    if row.status == "sent":
        inv.sent_at = utcnow()
    audit(db, user.id, "invoice.send", "invoice", inv.id, email_status=row.status)
    return row.status


def is_overdue(inv: Invoice, today: date) -> bool:
    return inv.state == InvoiceState.confirmed and inv.due_date < today and inv.amount_due > 0
