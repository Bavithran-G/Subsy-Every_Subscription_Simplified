"""Discount eligibility and calculation.

Rules (documented in README):
* Percentage discount = eligible amount x value / 100.
* Fixed discount      = min(value, eligible amount).
* Eligible amount     = gross of the rule's products (scope=products) or of all lines (scope=subscription).
* min_purchase / min_quantity are checked against the eligible lines.
* Several rules may apply; each is capped so no line (and so no invoice) can go below zero.
* Usage: an application on a non-cancelled invoice counts against max_usage. Draft invoices reserve a slot,
  confirmed/paid invoices consume it, and cancelling the invoice releases it. Because applications are tied
  to an invoice and the invoice to a unique billing event, retried billing jobs cannot double-count usage.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.money import ZERO, D, r2
from app.models import DiscountApplication, DiscountRule, DiscountScope, DiscountType, Invoice, InvoiceState


@dataclass
class DraftLine:
    product_id: int | None
    quantity: int
    gross: Decimal
    discount: Decimal = ZERO


@dataclass
class AppliedDiscount:
    rule: DiscountRule
    amount: Decimal
    per_line: list[Decimal] = field(default_factory=list)


def reserved_usage(db: Session, rule_id: int) -> int:
    return db.scalar(
        select(func.count(DiscountApplication.id))
        .join(Invoice, Invoice.id == DiscountApplication.invoice_id)
        .where(DiscountApplication.discount_id == rule_id, Invoice.state != InvoiceState.cancelled)
    ) or 0


def consumed_usage(db: Session, rule_id: int) -> int:
    return db.scalar(
        select(func.count(DiscountApplication.id))
        .join(Invoice, Invoice.id == DiscountApplication.invoice_id)
        .where(DiscountApplication.discount_id == rule_id,
               Invoice.state.in_([InvoiceState.confirmed, InvoiceState.paid]))
    ) or 0


def rule_is_live(db: Session, rule: DiscountRule, on: date) -> bool:
    if not rule.is_active:
        return False
    if rule.start_date and on < rule.start_date:
        return False
    if rule.end_date and on > rule.end_date:
        return False
    if rule.max_usage is not None and reserved_usage(db, rule.id) >= rule.max_usage:
        return False
    return True


def candidate_rules(db: Session, on: date, *, lock: bool = False) -> list[DiscountRule]:
    stmt = select(DiscountRule).where(DiscountRule.is_active.is_(True)).order_by(DiscountRule.id)
    if lock and db.get_bind().dialect.name == "postgresql":
        stmt = stmt.with_for_update()
    return list(db.scalars(stmt))


def apply_discounts(db: Session, lines: list[DraftLine], *, on: date, subscription_id: int | None,
                    lock: bool = True) -> list[AppliedDiscount]:
    applied: list[AppliedDiscount] = []
    for rule in candidate_rules(db, on, lock=lock):
        if not rule_is_live(db, rule, on):
            continue
        if rule.subscriptions and subscription_id not in {s.id for s in rule.subscriptions}:
            continue
        if rule.scope == DiscountScope.products:
            product_ids = {p.id for p in rule.products}
            idx = [i for i, l in enumerate(lines) if l.product_id in product_ids]
        else:
            idx = list(range(len(lines)))
        if not idx:
            continue
        eligible = sum((lines[i].gross for i in idx), ZERO)
        qty = sum(lines[i].quantity for i in idx)
        if eligible <= 0 or qty < (rule.min_quantity or 0) or eligible < D(rule.min_purchase):
            continue
        remaining = sum((lines[i].gross - lines[i].discount for i in idx), ZERO)
        if remaining <= 0:
            continue
        if rule.discount_type == DiscountType.percentage:
            amount = r2(eligible * D(rule.value) / Decimal(100))
        else:
            amount = r2(D(rule.value))
        amount = min(amount, remaining)
        if amount <= 0:
            continue
        # distribute proportionally over eligible lines' remaining amounts; last line takes rounding residue
        per_line = [ZERO] * len(lines)
        left = amount
        for n, i in enumerate(idx):
            room = lines[i].gross - lines[i].discount
            share = left if n == len(idx) - 1 else min(room, r2(amount * room / remaining))
            share = min(share, room)
            per_line[i] = share
            left -= share
        for i in idx:
            lines[i].discount += per_line[i]
        applied.append(AppliedDiscount(rule, amount - left, per_line))
    return applied
