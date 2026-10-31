"""Scheduled jobs. Each job is idempotent, logged in automation_runs and safe to run repeatedly."""
import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core import clock
from app.core.config import get_settings
from app.models import (
    AutomationRun, DiscountRule, Invoice, InvoiceState, Plan, Role, SubState, Subscription, User,
)
from app.models.base import utcnow
from app.services import subscriptions as subsvc
from app.services.billing import run_billing
from app.services.common import notify
from app.services.discounts import reserved_usage

log = logging.getLogger("subsy.automation")


def _run(session_factory, job: str, trigger: str, fn) -> AutomationRun:
    db = session_factory()
    run = AutomationRun(job=job, trigger=trigger, status="running")
    db.add(run)
    db.commit()
    try:
        processed, created, msg = fn(db)
        db.commit()
        run.processed, run.created, run.status, run.message = processed, created, "success", msg
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        run.status, run.failed, run.message = "failed", 1, f"{type(exc).__name__}: {exc}"[:1000]
        log.exception("job %s failed", job)
    run.finished_at = utcnow()
    db.add(run)
    db.commit()
    db.close()
    return run


def _staff_ids(db) -> list[int]:
    return list(db.scalars(select(User.id).where(User.role.in_([Role.admin, Role.staff]), User.is_active)))


def renewal_reminders(session_factory, as_of: date | None = None, trigger="scheduler") -> AutomationRun:
    as_of = as_of or clock.today()
    horizon = as_of + timedelta(days=get_settings().renewal_reminder_days)

    def fn(db):
        subs = db.scalars(select(Subscription).where(
            Subscription.state.in_([SubState.active, SubState.paused]),
            Subscription.end_date.is_not(None), Subscription.end_date >= as_of, Subscription.end_date <= horizon,
        )).all()
        staff = _staff_ids(db)
        for s in subs:
            key = f"renew-{s.id}-{s.end_date}"
            msg = f"{s.number} ({s.customer.name}) expires on {s.end_date}"
            if s.customer.user_id:
                notify(db, s.customer.user_id, "renewal", f"Your subscription {s.number} expires soon",
                       msg + (" — you can renew it from the portal." if s.plan.renewable else "."),
                       f"/portal/subscriptions/{s.id}", dedupe_key=key + "-c")
            for uid in staff:
                notify(db, uid, "renewal", "Upcoming renewal", msg, f"/subscriptions/{s.id}",
                       dedupe_key=f"{key}-u{uid}")
        return len(subs), len(subs), f"{len(subs)} subscription(s) expiring by {horizon}"
    return _run(session_factory, "renewal_reminders", trigger, fn)


def auto_close(session_factory, as_of: date | None = None, trigger="scheduler") -> AutomationRun:
    as_of = as_of or clock.today()

    def fn(db):
        subs = db.scalars(select(Subscription).join(Plan).where(
            Subscription.state.in_([SubState.active, SubState.paused, SubState.confirmed]),
            Subscription.end_date.is_not(None), Subscription.end_date < as_of, Plan.auto_close.is_(True),
        )).all()
        closed = 0
        for s in subs:
            # never close while periods up to expiry are still unbilled
            if s.state == SubState.active and s.next_invoice_date and s.next_invoice_date <= s.end_date:
                continue
            subsvc.close(db, None, s, automatic=True)
            closed += 1
        # plans whose availability window ended and are set to auto-close become inactive for new sales
        plans = db.scalars(select(Plan).where(Plan.auto_close.is_(True), Plan.is_active.is_(True),
                                              Plan.end_date.is_not(None), Plan.end_date < as_of)).all()
        for p in plans:
            p.is_active = False
        return len(subs), closed, f"{closed} subscription(s) closed, {len(plans)} plan(s) deactivated"
    return _run(session_factory, "auto_close", trigger, fn)


def overdue_scan(session_factory, as_of: date | None = None, trigger="scheduler") -> AutomationRun:
    as_of = as_of or clock.today()

    def fn(db):
        invs = db.scalars(select(Invoice).where(Invoice.state == InvoiceState.confirmed,
                                                Invoice.due_date < as_of)).all()
        invs = [i for i in invs if i.amount_due > 0]
        for i in invs:
            if i.customer.user_id:
                notify(db, i.customer.user_id, "overdue", f"Invoice {i.number} is overdue",
                       f"INR {i.amount_due} was due on {i.due_date}", f"/portal/invoices/{i.id}",
                       dedupe_key=f"overdue-{i.id}")
        return len(invs), 0, f"{len(invs)} overdue invoice(s)"
    return _run(session_factory, "overdue_scan", trigger, fn)


def discount_housekeeping(session_factory, as_of: date | None = None, trigger="scheduler") -> AutomationRun:
    as_of = as_of or clock.today()

    def fn(db):
        n = 0
        for r in db.scalars(select(DiscountRule).where(DiscountRule.is_active.is_(True))).all():
            expired = r.end_date is not None and r.end_date < as_of
            exhausted = r.max_usage is not None and reserved_usage(db, r.id) >= r.max_usage
            if expired or exhausted:
                r.is_active = False
                n += 1
        return n, 0, f"{n} discount rule(s) deactivated (expired or usage limit reached)"
    return _run(session_factory, "discount_housekeeping", trigger, fn)


def billing(session_factory, as_of: date | None = None, trigger="scheduler", user_id=None) -> AutomationRun:
    return run_billing(session_factory, as_of, trigger, user_id)


JOBS = {
    "billing": billing,
    "auto_close": auto_close,
    "renewal_reminders": renewal_reminders,
    "overdue_scan": overdue_scan,
    "discount_housekeeping": discount_housekeeping,
}


def run_daily(session_factory, as_of: date | None = None, trigger="scheduler"):
    """Order matters: bill first, then close expired subscriptions, then reminders and scans."""
    return [JOBS[name](session_factory, as_of, trigger) for name in
            ("billing", "auto_close", "renewal_reminders", "overdue_scan", "discount_housekeeping")]
