"""Recurring billing engine.

Duplicate-billing protection is layered:
1. UNIQUE(billing_events.subscription_id, period_start) — a period can only ever have one billing event.
2. UNIQUE(invoices.billing_event_id) — a billing event can only ever have one invoice.
3. Per-subscription row lock (SELECT ... FOR UPDATE SKIP LOCKED) so concurrent runners never work on the
   same subscription at the same time; the second runner simply skips it.
4. A Postgres advisory lock so only one scheduled billing run executes at a time.
5. The subscription's `next_period_index` only advances after its invoice is committed. A failure leaves the
   event in `failed` state and the index untouched, so the next run (or a manual retry) picks up exactly the
   same period — nothing is skipped and nothing is billed twice.
"""
import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy import or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core import clock
from app.models import (
    AutomationRun, BillingEvent, BillingEventStatus, Invoice, InvoiceState, SubState, Subscription, User,
)
from app.models.base import utcnow
from app.services.errors import DomainError, NotFound
from app.services.invoices import build_invoice_for_period
from app.services.periods import period_bounds

log = logging.getLogger("subsy.billing")
BILLING_LOCK_KEY = 7_311_001
MAX_PERIODS_PER_RUN = 400  # safety valve for very old daily subscriptions


@dataclass
class SubResult:
    created: int = 0
    failed: bool = False
    skipped_locked: bool = False
    error: str | None = None


def _lock_subscription(db: Session, sub_id: int) -> Subscription | None:
    stmt = select(Subscription).where(Subscription.id == sub_id)
    if db.get_bind().dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True, of=Subscription)
    return db.scalars(stmt).first()


def _billable(sub: Subscription, as_of: date) -> bool:
    return (sub.state == SubState.active and sub.next_invoice_date is not None
            and sub.next_invoice_date <= as_of
            and (sub.end_date is None or sub.next_invoice_date <= sub.end_date))


def _get_or_create_event(db: Session, sub: Subscription, start: date, end: date, source: str) -> BillingEvent:
    event = db.scalars(select(BillingEvent).where(
        BillingEvent.subscription_id == sub.id, BillingEvent.period_start == start)).first()
    if event:
        return event
    event = BillingEvent(subscription_id=sub.id, period_index=sub.next_period_index, period_start=start,
                         period_end=end, status=BillingEventStatus.pending, source=source)
    try:
        with db.begin_nested():
            db.add(event)
            db.flush()
    except IntegrityError:
        # someone else inserted it concurrently — use theirs
        event = db.scalars(select(BillingEvent).where(
            BillingEvent.subscription_id == sub.id, BillingEvent.period_start == start)).one()
    return event


def _advance(sub: Subscription):
    sub.next_period_index += 1
    start, _ = period_bounds(sub.billing_anchor, sub.plan.billing_period, sub.plan.billing_interval,
                             sub.next_period_index)
    sub.next_invoice_date = start


def bill_subscription(db: Session, sub_id: int, as_of: date, *, user: User | None = None, source="scheduler",
                      max_periods: int = MAX_PERIODS_PER_RUN, commit: bool = True) -> SubResult:
    """Bill every due period of one subscription up to `as_of`. Commits per subscription."""
    res = SubResult()
    sub = _lock_subscription(db, sub_id)
    if sub is None:
        res.skipped_locked = True
        db.rollback()
        return res
    while _billable(sub, as_of) and res.created < max_periods:
        start, end = period_bounds(sub.billing_anchor, sub.plan.billing_period, sub.plan.billing_interval,
                                   sub.next_period_index)
        if sub.end_date and end > sub.end_date:
            end = sub.end_date
        event = _get_or_create_event(db, sub, start, end, source)
        if event.status == BillingEventStatus.invoiced and event.invoice is not None:
            _advance(sub)  # already billed earlier (e.g. index not advanced after a crash) — never re-bill
            continue
        event.attempts += 1
        try:
            with db.begin_nested():
                build_invoice_for_period(db, sub, event, user)
                event.status, event.error = BillingEventStatus.invoiced, None
                db.flush()
        except Exception as exc:  # noqa: BLE001 — record any failure and stop this subscription
            event.status = BillingEventStatus.failed
            event.error = f"{type(exc).__name__}: {exc}"[:1000]
            res.failed, res.error = True, event.error
            log.warning("billing failed for %s period %s: %s", sub.number, start, exc)
            break
        _advance(sub)
        res.created += 1
    if commit:
        db.commit()
    else:
        db.flush()
    return res


def bill_next_period_now(db: Session, sub: Subscription, user: User) -> Invoice:
    """Staff 'Create invoice' action: bill the subscription's next period immediately (even if not yet due).
    Uses the same billing-event identity, so it can never duplicate a scheduled invoice."""
    if sub.state != SubState.active:
        raise DomainError("Only active subscriptions can be invoiced")
    if sub.end_date and sub.next_invoice_date and sub.next_invoice_date > sub.end_date:
        raise DomainError("All periods up to the expiry date are already invoiced — renew to bill further")
    target = sub.next_invoice_date
    res = bill_subscription(db, sub.id, target, user=user, source="manual", max_periods=1)
    if res.skipped_locked:
        raise DomainError("Subscription is being billed by another process — try again shortly")
    if res.failed:
        raise DomainError(f"Billing failed: {res.error}")
    inv = db.scalars(select(Invoice).join(BillingEvent, Invoice.billing_event_id == BillingEvent.id)
                     .where(BillingEvent.subscription_id == sub.id, BillingEvent.period_start == target)).first()
    if not inv:
        raise DomainError("No invoice was generated")
    return inv


def retry_event(db: Session, event_id: int, user: User) -> SubResult:
    event = db.get(BillingEvent, event_id)
    if not event:
        raise NotFound("Billing event not found")
    if event.status == BillingEventStatus.invoiced:
        inv = event.invoice
        if inv and inv.state == InvoiceState.cancelled:
            # re-bill a period whose invoice was cancelled: detach the cancelled invoice (kept for history)
            inv.billing_event_id = None
            inv.notes = ((inv.notes or "") + "\nSuperseded by re-billing").strip()
            db.flush()
            event.status = BillingEventStatus.pending
            sub = event.subscription
            try:
                with db.begin_nested():
                    event.attempts += 1
                    build_invoice_for_period(db, sub, event, user)
                    event.status = BillingEventStatus.invoiced
                    db.flush()
            except Exception as exc:  # noqa: BLE001
                event.status, event.error = BillingEventStatus.failed, str(exc)[:1000]
                db.commit()
                return SubResult(failed=True, error=event.error)
            db.commit()
            return SubResult(created=1)
        raise DomainError("This billing period is already invoiced")
    # pending/failed: the subscription's next index still points at this period, so a normal run retries it
    return bill_subscription(db, event.subscription_id, max(event.period_start, clock.today()), user=user,
                             source="retry")


def due_subscription_ids(db: Session, as_of: date) -> list[int]:
    return list(db.scalars(
        select(Subscription.id).where(
            Subscription.state == SubState.active,
            Subscription.next_invoice_date <= as_of,
            or_(Subscription.end_date.is_(None), Subscription.next_invoice_date <= Subscription.end_date),
        ).order_by(Subscription.id)
    ))


def run_billing(session_factory: sessionmaker, as_of: date | None = None, trigger: str = "scheduler",
                user_id: int | None = None) -> AutomationRun:
    as_of = as_of or clock.today()
    control = session_factory()
    run = AutomationRun(job="billing", trigger=trigger, status="running")
    control.add(run)
    control.commit()
    locked = True
    is_pg = control.get_bind().dialect.name == "postgresql"
    try:
        if is_pg:
            locked = control.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": BILLING_LOCK_KEY}).scalar()
        if not locked:
            run.status, run.message = "skipped", "Another billing run is in progress"
            return run
        ids = due_subscription_ids(control, as_of)
        errors = []
        for sub_id in ids:
            db = session_factory()
            try:
                user = db.get(User, user_id) if user_id else None
                r = bill_subscription(db, sub_id, as_of, user=user, source=trigger)
                run.processed += 0 if r.skipped_locked else 1
                run.created += r.created
                if r.failed:
                    run.failed += 1
                    errors.append(f"sub#{sub_id}: {r.error}")
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                run.failed += 1
                errors.append(f"sub#{sub_id}: {exc}")
            finally:
                db.close()
        run.status = "success" if not run.failed else ("partial" if run.created or run.processed > run.failed
                                                       else "failed")
        run.message = f"Billing as of {as_of}: {run.created} invoice(s) from {run.processed} subscription(s)" + (
            f"; failures: {'; '.join(errors[:10])}" if errors else "")
        return run
    finally:
        if is_pg and locked:
            control.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": BILLING_LOCK_KEY})
        run.finished_at = utcnow()
        control.commit()
        control.close()
