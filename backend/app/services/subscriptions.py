"""Subscription / quotation lifecycle. All state changes go through `_transition` so every change is
validated and written to the subscription's history."""
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Customer, Plan, Product, ProductVariant, QuotationTemplate, Role, SubState, Subscription, SubscriptionHistory,
    SubscriptionLine, SubscriptionRenewal, Tax, User,
)
from app.core import clock
from app.services.common import audit, make_number, notify, send_email
from app.services.errors import Conflict, DomainError, Forbidden, NotFound
from app.services.periods import period_bounds, shift
from app.services.pricing import catalog_unit_price, line_amounts

ALLOWED = {
    "send": ({SubState.draft}, SubState.quotation),
    "confirm": ({SubState.draft, SubState.quotation}, SubState.confirmed),
    "activate": ({SubState.confirmed}, SubState.active),
    "pause": ({SubState.active}, SubState.paused),
    "resume": ({SubState.paused}, SubState.active),
    "close": ({SubState.confirmed, SubState.active, SubState.paused}, SubState.closed),
    "cancel": ({SubState.draft, SubState.quotation}, SubState.cancelled),
}
EDITABLE = {SubState.draft, SubState.quotation}


@dataclass
class LineInput:
    product_id: int
    variant_id: int | None
    quantity: int
    unit_price: object | None = None  # override
    tax_id: int | None = None  # override; None -> product default


def today() -> date:
    return clock.today()


def get_subscription(db: Session, sub_id: int, *, for_update: bool = False) -> Subscription:
    stmt = select(Subscription).where(Subscription.id == sub_id)
    if for_update and db.get_bind().dialect.name == "postgresql":
        stmt = stmt.with_for_update()
    sub = db.scalars(stmt).first()
    if not sub:
        raise NotFound("Subscription not found")
    return sub


def is_expired_quotation(sub: Subscription, on: date | None = None) -> bool:
    return sub.state in EDITABLE and sub.valid_until is not None and sub.valid_until < (on or today())


def _build_line(db: Session, li: LineInput) -> SubscriptionLine:
    product = db.get(Product, li.product_id)
    if not product or not product.is_active:
        raise DomainError(f"Product {li.product_id} is not available")
    variant = None
    if li.variant_id:
        variant = db.get(ProductVariant, li.variant_id)
        if not variant or not variant.is_active:
            raise DomainError("Selected variant is not available")
    if li.quantity < 1:
        raise DomainError("Quantity must be at least 1")
    price = catalog_unit_price(product, variant) if li.unit_price is None else li.unit_price
    if price is not None and float(price) < 0:
        raise DomainError("Unit price cannot be negative")
    tax_id = li.tax_id if li.tax_id is not None else product.tax_id
    if tax_id and not db.get(Tax, tax_id):
        raise DomainError("Tax not found")
    desc = product.name + (f" ({variant.attribute}: {variant.value})" if variant else "")
    return SubscriptionLine(product_id=product.id, variant_id=variant.id if variant else None, description=desc,
                            quantity=li.quantity, unit_price=price, tax_id=tax_id)


def _history(db: Session, sub: Subscription, from_state, to_state, action: str, user: User | None, reason=None):
    sub.history.append(SubscriptionHistory(
        from_state=str(from_state) if from_state else None, to_state=str(to_state), action=action,
        reason=reason, user_id=user.id if user else None,
    ))


def create_subscription(db: Session, user: User, *, customer_id: int, plan_id: int, lines: list[LineInput],
                        template_id: int | None = None, start_date: date | None = None,
                        end_date: date | None = None, payment_terms_days: int | None = None,
                        valid_until: date | None = None, notes: str | None = None) -> Subscription:
    customer = db.get(Customer, customer_id)
    if not customer:
        raise NotFound("Customer not found")
    plan = db.get(Plan, plan_id)
    if not plan or not plan.is_active:
        raise DomainError("Plan is not available")
    template = None
    if template_id:
        template = db.get(QuotationTemplate, template_id)
        if not template or not template.is_active:
            raise DomainError("Quotation template not available")
        if template.plan_id != plan_id:
            raise DomainError("Template belongs to a different plan")
    if not lines:
        if template:
            lines = [LineInput(l.product_id, l.variant_id, l.quantity, l.unit_price) for l in template.lines]
        else:
            lines = [LineInput(l.product_id, l.variant_id, l.quantity, l.unit_price) for l in plan.lines]
    if not lines:
        raise DomainError("A subscription needs at least one product line")
    if start_date and end_date and end_date < start_date:
        raise DomainError("Expiry date cannot be before start date")

    qdate = today()
    validity = template.validity_days if template else 30
    sub = Subscription(
        customer_id=customer_id, plan_id=plan_id, template_id=template_id, state=SubState.draft,
        quotation_date=qdate, valid_until=valid_until or (qdate + timedelta(days=validity)),
        start_date=start_date, end_date=end_date,
        payment_terms_days=payment_terms_days if payment_terms_days is not None
        else (template.payment_terms_days if template else 15),
        notes=notes or (template.notes if template else None), created_by_id=user.id,
    )
    for li in lines:
        sub.lines.append(_build_line(db, li))
    db.add(sub)
    db.flush()
    sub.number = make_number("SUB", sub.id)
    _history(db, sub, None, SubState.draft, "create", user,
             f"Created from template '{template.name}'" if template else None)
    audit(db, user.id, "subscription.create", "subscription", sub.id, template_id=template_id)
    return sub


def update_subscription(db: Session, user: User, sub: Subscription, *, lines: list[LineInput] | None = None,
                        **fields) -> Subscription:
    if sub.state not in EDITABLE:
        raise DomainError("Only draft quotations can be edited")
    for key in ("start_date", "end_date", "payment_terms_days", "valid_until", "notes"):
        if key in fields and fields[key] is not None:
            setattr(sub, key, fields[key])
    if sub.start_date and sub.end_date and sub.end_date < sub.start_date:
        raise DomainError("Expiry date cannot be before start date")
    if lines is not None:
        if not lines:
            raise DomainError("A subscription needs at least one product line")
        sub.lines.clear()
        db.flush()
        for li in lines:
            sub.lines.append(_build_line(db, li))
    audit(db, user.id, "subscription.update", "subscription", sub.id)
    return sub


def _transition(db: Session, sub: Subscription, action: str, user: User | None, reason: str | None = None):
    sources, target = ALLOWED[action]
    if sub.state not in sources:
        raise DomainError(f"Cannot {action} a subscription in state '{sub.state}'")
    previous = sub.state
    sub.state = target
    _history(db, sub, previous, target, action, user, reason)
    audit(db, user.id if user else None, f"subscription.{action}", "subscription", sub.id,
          from_state=str(previous), to_state=str(target), reason=reason)


def send_quotation(db: Session, user: User, sub: Subscription):
    if is_expired_quotation(sub):
        raise DomainError("Quotation has expired — extend its validity first")
    _transition(db, sub, "send", user)
    total = sum(line_amounts(l.quantity, l.unit_price, l.tax).total for l in sub.lines)
    send_email(db, sub.customer.email, f"Quotation {sub.number} from Brightloop Software",
               f"Dear {sub.customer.name},\n\nPlease find quotation {sub.number} for plan '{sub.plan.name}'.\n"
               f"Total per billing period: INR {total}\nValid until: {sub.valid_until}\n")


def extend_quotation(db: Session, user: User, sub: Subscription, days: int = 30):
    if sub.state not in EDITABLE:
        raise DomainError("Only open quotations can be extended")
    if days < 1 or days > 365:
        raise DomainError("Extension must be between 1 and 365 days")
    sub.valid_until = today() + timedelta(days=days)
    _history(db, sub, sub.state, sub.state, "extend", user, f"Valid until {sub.valid_until}")


def confirm(db: Session, user: User, sub: Subscription):
    if is_expired_quotation(sub):
        raise DomainError("Quotation has expired — extend its validity before confirming")
    plan = sub.plan
    if not plan.is_active:
        raise DomainError("Plan is inactive")
    t = today()
    if plan.end_date and plan.end_date < t:
        raise DomainError("Plan is no longer available (availability ended)")
    if plan.start_date and plan.start_date > (sub.start_date or t):
        raise DomainError(f"Plan is only available from {plan.start_date}")
    if not sub.lines:
        raise DomainError("Cannot confirm a subscription without lines")
    for line in sub.lines:
        if line.quantity < plan.min_quantity:
            raise DomainError(f"Plan '{plan.name}' requires a minimum quantity of {plan.min_quantity} per line")
    _transition(db, sub, "confirm", user)
    sub.confirmed_at = utcnow_dt()
    if sub.customer.user_id:
        notify(db, sub.customer.user_id, "subscription", f"Subscription {sub.number} confirmed",
               f"Your subscription to {plan.name} is confirmed.", f"/portal/subscriptions/{sub.id}")


def activate(db: Session, user: User | None, sub: Subscription, start_date: date | None = None):
    _transition(db, sub, "activate", user)
    plan = sub.plan
    sub.start_date = start_date or sub.start_date or today()
    if sub.end_date is None and plan.term_periods:
        sub.end_date = shift(sub.start_date, plan.billing_period, plan.term_periods * plan.billing_interval) \
            - timedelta(days=1)
    if sub.end_date and sub.end_date < sub.start_date:
        raise DomainError("Expiry date cannot be before start date")
    sub.billing_anchor = sub.start_date
    sub.next_period_index = 0
    sub.next_invoice_date = sub.start_date


def pause(db: Session, user: User, sub: Subscription, reason: str | None = None):
    if not sub.plan.pausable:
        raise Forbidden(f"Plan '{sub.plan.name}' does not allow pausing")
    _transition(db, sub, "pause", user, reason)
    sub.paused_on = today()


def resume(db: Session, user: User, sub: Subscription):
    if not sub.plan.pausable:
        raise Forbidden(f"Plan '{sub.plan.name}' does not allow pausing/resuming")
    t = today()
    skipped = 0
    # Periods that *started* while paused are not billed; earlier unbilled periods stay due.
    while sub.next_invoice_date and sub.paused_on and sub.paused_on <= sub.next_invoice_date < t:
        sub.next_period_index += 1
        sub.next_invoice_date, _ = period_bounds(sub.billing_anchor, sub.plan.billing_period,
                                                 sub.plan.billing_interval, sub.next_period_index)
        skipped += 1
    _transition(db, sub, "resume", user, f"{skipped} billing period(s) skipped while paused" if skipped else None)
    sub.paused_on = None


def close(db: Session, user: User | None, sub: Subscription, reason: str | None = None, *, automatic=False):
    t = today()
    early = sub.end_date is None or t < sub.end_date
    if early and not automatic and not sub.plan.closable:
        raise Forbidden(f"Plan '{sub.plan.name}' does not allow closing before the expiry date")
    _transition(db, sub, "close", user, reason or ("Automatic closure at expiry" if automatic else None))
    sub.closed_at = utcnow_dt()
    sub.next_invoice_date = None
    if sub.customer.user_id:
        notify(db, sub.customer.user_id, "subscription", f"Subscription {sub.number} closed", reason,
               f"/portal/subscriptions/{sub.id}")


def cancel(db: Session, user: User, sub: Subscription, reason: str | None = None):
    _transition(db, sub, "cancel", user, reason)


def renew(db: Session, user: User, sub: Subscription) -> SubscriptionRenewal:
    plan = sub.plan
    if not plan.renewable:
        raise Forbidden(f"Plan '{plan.name}' does not allow renewal")
    if sub.state not in (SubState.active, SubState.paused):
        raise DomainError("Only active or paused subscriptions can be renewed")
    if not sub.end_date:
        raise DomainError("Subscription has no expiry date — it renews automatically every period")
    steps = (plan.term_periods or 1) * plan.billing_interval
    first_day = sub.end_date + timedelta(days=1)
    new_end = shift(first_day, plan.billing_period, steps) - timedelta(days=1)
    renewal = SubscriptionRenewal(subscription_id=sub.id, previous_end_date=sub.end_date, new_end_date=new_end,
                                  user_id=user.id if user else None)
    try:
        with db.begin_nested():
            db.add(renewal)
            db.flush()
    except IntegrityError:
        raise Conflict("This term has already been renewed") from None
    previous = sub.end_date
    sub.end_date = new_end
    _history(db, sub, sub.state, sub.state, "renew", user, f"Expiry {previous} → {new_end}")
    audit(db, user.id if user else None, "subscription.renew", "subscription", sub.id,
          previous_end=previous, new_end=new_end)
    return renewal


def assert_customer_can_act(user: User, sub: Subscription):
    if user.role == Role.customer and (not user.customer or user.customer.id != sub.customer_id):
        raise NotFound("Subscription not found")


def utcnow_dt():
    from app.models.base import utcnow
    return utcnow()
