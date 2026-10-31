from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.money import ZERO
from app.models import BillingEvent, Invoice, InvoiceState, Role, SubState, Subscription, User
from app.schemas.business import (
    BillingEventOut, HistoryOut, InvoiceLineOut, InvoiceOut, InvoiceRow, PaymentOut, RenewalOut, SubLineOut,
    SubscriptionOut, SubscriptionRow,
)
from app.services.pricing import line_amounts
from app.services.subscriptions import is_expired_quotation


def sub_totals(sub: Subscription):
    untaxed = tax = ZERO
    lines = []
    for l in sub.lines:
        a = line_amounts(l.quantity, l.unit_price, l.tax)
        o = SubLineOut.model_validate(l)
        o.tax_name, o.subtotal, o.tax_amount, o.total = (l.tax.name if l.tax else None), a.gross, a.tax, a.total
        lines.append(o)
        untaxed += a.gross
        tax += a.tax
    return lines, untaxed, tax


def sub_row(sub: Subscription, total: Decimal | None = None) -> SubscriptionRow:
    if total is None:
        _, untaxed, tax = sub_totals(sub)
        total = untaxed + tax
    return SubscriptionRow(
        id=sub.id, number=sub.number, state=str(sub.state), customer_id=sub.customer_id,
        customer_name=sub.customer.name, plan_id=sub.plan_id, plan_name=sub.plan.name,
        billing_period=str(sub.plan.billing_period), quotation_date=sub.quotation_date, valid_until=sub.valid_until,
        start_date=sub.start_date, end_date=sub.end_date, next_invoice_date=sub.next_invoice_date, total=total,
        is_expired_quotation=is_expired_quotation(sub), is_demo=sub.is_demo,
    )


def allowed_actions(sub: Subscription, user: User) -> list[str]:
    p, s, acts = sub.plan, sub.state, []
    t = clock.today()
    if user.role in (Role.admin, Role.staff):
        if s in (SubState.draft, SubState.quotation):
            acts += ["edit", "extend", "cancel"]
            if not is_expired_quotation(sub):
                acts += ["confirm"] + (["send"] if s == SubState.draft else [])
        if s == SubState.confirmed:
            acts += ["activate"]
        if s == SubState.active:
            acts += ["invoice"]
        if s in (SubState.confirmed, SubState.active, SubState.paused):
            if p.closable or (sub.end_date and sub.end_date <= t):
                acts += ["close"]
    if s == SubState.active and p.pausable:
        acts += ["pause"]
    if s == SubState.paused and p.pausable:
        acts += ["resume"]
    if s in (SubState.active, SubState.paused) and p.renewable and sub.end_date:
        acts += ["renew"]
    return acts


def sub_detail(db: Session, sub: Subscription, user: User) -> SubscriptionOut:
    lines, untaxed, tax = sub_totals(sub)
    row = sub_row(sub, untaxed + tax)
    events = []
    if user.role != Role.customer:
        for e in db.scalars(select(BillingEvent).where(BillingEvent.subscription_id == sub.id)
                            .order_by(BillingEvent.period_start.desc())).all():
            o = BillingEventOut.model_validate(e)
            if e.invoice:
                o.invoice_id, o.invoice_number = e.invoice.id, e.invoice.number
            events.append(o)
    history = []
    for h in sub.history:
        o = HistoryOut.model_validate(h)
        o.user_name = h.user.full_name if h.user else "System"
        history.append(o)
    p = sub.plan
    return SubscriptionOut(
        **row.model_dump(), template_id=sub.template_id, payment_terms_days=sub.payment_terms_days,
        notes=sub.notes, untaxed=untaxed, tax=tax, lines=lines, history=history,
        renewals=[RenewalOut.model_validate(r) for r in sub.renewals], billing_events=events,
        plan={"id": p.id, "name": p.name, "billing_period": str(p.billing_period),
              "billing_interval": p.billing_interval, "min_quantity": p.min_quantity, "auto_close": p.auto_close,
              "closable": p.closable, "pausable": p.pausable, "renewable": p.renewable,
              "term_periods": p.term_periods},
        allowed_actions=allowed_actions(sub, user), customer_email=sub.customer.email,
    )


def is_overdue(inv: Invoice, today: date | None = None) -> bool:
    today = today or clock.today()
    return inv.state == InvoiceState.confirmed and inv.due_date < today and inv.amount_due > 0


def inv_row(inv: Invoice) -> InvoiceRow:
    return InvoiceRow(
        id=inv.id, number=inv.number, state=str(inv.state), customer_id=inv.customer_id,
        customer_name=inv.customer.name, subscription_id=inv.subscription_id,
        subscription_number=inv.subscription.number if inv.subscription else None, invoice_date=inv.invoice_date,
        due_date=inv.due_date, period_start=inv.period_start, period_end=inv.period_end, total=inv.total,
        amount_paid=inv.amount_paid, amount_due=inv.amount_due, is_overdue=is_overdue(inv), is_demo=inv.is_demo,
    )


def pay_out(p) -> PaymentOut:
    o = PaymentOut.model_validate(p)
    o.customer_name = p.customer.name
    o.invoice_number = p.invoice.number
    o.recorded_by_name = p.recorded_by.full_name if p.recorded_by else None
    return o


def inv_detail(inv: Invoice, user: User) -> InvoiceOut:
    acts = []
    if user.role in (Role.admin, Role.staff):
        if inv.state == InvoiceState.draft:
            acts += ["confirm", "cancel"]
        if inv.state == InvoiceState.confirmed:
            acts += ["pay", "send"] + (["cancel"] if inv.amount_paid == 0 else [])
        if inv.state == InvoiceState.paid:
            acts += ["send"]
    acts += ["print"]
    c = inv.customer
    return InvoiceOut(
        **inv_row(inv).model_dump(), untaxed_amount=inv.untaxed_amount, discount_amount=inv.discount_amount,
        tax_amount=inv.tax_amount, notes=inv.notes,
        lines=[InvoiceLineOut.model_validate(l) for l in inv.lines],
        payments=[pay_out(p) for p in inv.payments],
        discounts=[{"name": a.discount.name, "type": str(a.discount.discount_type), "value": str(a.discount.value),
                    "amount": str(a.amount)} for a in inv.discount_applications],
        customer={"id": c.id, "name": c.name, "email": c.email, "company": c.company, "address": c.address,
                  "gstin": c.gstin},
        confirmed_at=inv.confirmed_at, paid_at=inv.paid_at, sent_at=inv.sent_at, allowed_actions=acts,
    )


def upcoming_window(days: int = 30) -> tuple[date, date]:
    t = clock.today()
    return t, t + timedelta(days=days)
