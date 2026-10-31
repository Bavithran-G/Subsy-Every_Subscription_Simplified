"""Reporting. Every figure is aggregated in SQL from persisted records.
Invoiced revenue (confirmed + paid invoices, by invoice date) is always kept separate from collected revenue
(posted payments, by payment date). Outstanding = confirmed invoices' total - amount_paid."""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.money import ZERO, r2
from app.models import (
    AuditLog, BillingEvent, Customer, DiscountApplication, DiscountRule, Invoice, InvoiceLine, InvoiceState, Payment,
    PaymentStatus, Plan, Product, SubState, Subscription, SubscriptionLine, User,
)
from app.services.periods import add_months, monthly_factor

LIVE = (SubState.active, SubState.paused)
BILLED = (InvoiceState.confirmed, InvoiceState.paid)


def month_key(db: Session, col):
    if db.get_bind().dialect.name == "postgresql":
        return func.to_char(col, "YYYY-MM")
    return func.strftime("%Y-%m", col)


def months_between(start: date, end: date) -> list[str]:
    out, cur = [], date(start.year, start.month, 1)
    while cur <= end:
        out.append(cur.strftime("%Y-%m"))
        cur = add_months(cur, 1)
    return out


def default_range(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    t = clock.today()
    date_to = date_to or t
    date_from = date_from or date(add_months(date_to, -11).year, add_months(date_to, -11).month, 1)
    return date_from, date_to


def _f(v) -> float:
    return float(r2(v or 0))


def _sub_filters(stmt, plan_id=None, customer_id=None):
    if plan_id:
        stmt = stmt.where(Subscription.plan_id == plan_id)
    if customer_id:
        stmt = stmt.where(Subscription.customer_id == customer_id)
    return stmt


def _inv_filters(stmt, plan_id=None, customer_id=None):
    if customer_id:
        stmt = stmt.where(Invoice.customer_id == customer_id)
    if plan_id:
        stmt = stmt.where(Invoice.subscription_id.in_(select(Subscription.id).where(Subscription.plan_id == plan_id)))
    return stmt


def mrr(db: Session, plan_id=None, customer_id=None) -> float:
    stmt = (select(Plan.billing_period, Plan.billing_interval,
                   func.sum(SubscriptionLine.quantity * SubscriptionLine.unit_price))
            .select_from(SubscriptionLine).join(Subscription).join(Plan)
            .where(Subscription.state == SubState.active).group_by(Plan.billing_period, Plan.billing_interval))
    stmt = _sub_filters(stmt, plan_id, customer_id)
    return round(sum(float(amt or 0) * monthly_factor(p, i) for p, i, amt in db.execute(stmt)), 2)


def outstanding_q(db: Session, plan_id=None, customer_id=None):
    t = clock.today()
    stmt = select(
        func.count(Invoice.id),
        func.coalesce(func.sum(Invoice.total - Invoice.amount_paid), 0),
        func.count(case((Invoice.due_date < t, Invoice.id))),
        func.coalesce(func.sum(case((Invoice.due_date < t, Invoice.total - Invoice.amount_paid), else_=0)), 0),
    ).where(Invoice.state == InvoiceState.confirmed, Invoice.total > Invoice.amount_paid)
    return db.execute(_inv_filters(stmt, plan_id, customer_id)).one()


def dashboard(db: Session, date_from=None, date_to=None, plan_id=None, customer_id=None) -> dict:
    t = clock.today()
    date_from, date_to = default_range(date_from, date_to)

    sub_states = dict(db.execute(_sub_filters(
        select(Subscription.state, func.count()).group_by(Subscription.state), plan_id, customer_id)).all())
    inv_states = dict(db.execute(_inv_filters(
        select(Invoice.state, func.count()).group_by(Invoice.state), plan_id, customer_id)).all())
    renew30 = db.scalar(_sub_filters(select(func.count()).select_from(Subscription).where(
        Subscription.state.in_(LIVE), Subscription.end_date.between(t, t + timedelta(days=30))), plan_id, customer_id))
    expiring7 = db.scalar(_sub_filters(select(func.count()).select_from(Subscription).where(
        Subscription.state.in_(LIVE), Subscription.end_date.between(t, t + timedelta(days=7))), plan_id, customer_id))
    out_n, out_amt, od_n, od_amt = outstanding_q(db, plan_id, customer_id)

    pay_stmt = select(func.coalesce(func.sum(Payment.amount), 0)).where(
        Payment.status == PaymentStatus.posted, Payment.payment_date.between(date_from, date_to))
    if customer_id:
        pay_stmt = pay_stmt.where(Payment.customer_id == customer_id)
    if plan_id:
        pay_stmt = pay_stmt.join(Invoice, Invoice.id == Payment.invoice_id).join(
            Subscription, Subscription.id == Invoice.subscription_id).where(Subscription.plan_id == plan_id)
    collected = db.scalar(pay_stmt)
    invoiced = db.scalar(_inv_filters(select(func.coalesce(func.sum(Invoice.total), 0)).where(
        Invoice.state.in_(BILLED), Invoice.invoice_date.between(date_from, date_to)), plan_id, customer_id))
    disc_amt, disc_n = db.execute(_inv_filters(
        select(func.coalesce(func.sum(DiscountApplication.amount), 0), func.count(DiscountApplication.id))
        .join(Invoice, Invoice.id == DiscountApplication.invoice_id)
        .where(Invoice.state.in_(BILLED), Invoice.invoice_date.between(date_from, date_to)),
        plan_id, customer_id)).one()

    kpis = {
        "total_customers": db.scalar(select(func.count()).select_from(Customer)) if not customer_id else 1,
        "total_subscriptions": sum(sub_states.values()),
        "active_subscriptions": sub_states.get(SubState.active, 0),
        "paused_subscriptions": sub_states.get(SubState.paused, 0),
        "draft_subscriptions": sub_states.get(SubState.draft, 0),
        "awaiting_confirmation": sub_states.get(SubState.quotation, 0),
        "confirmed_subscriptions": sub_states.get(SubState.confirmed, 0),
        "closed_subscriptions": sub_states.get(SubState.closed, 0),
        "upcoming_renewals": renew30,
        "expiring_subscriptions": expiring7,
        "total_invoices": sum(inv_states.values()),
        "draft_invoices": inv_states.get(InvoiceState.draft, 0),
        "confirmed_invoices": inv_states.get(InvoiceState.confirmed, 0),
        "paid_invoices": inv_states.get(InvoiceState.paid, 0),
        "cancelled_invoices": inv_states.get(InvoiceState.cancelled, 0),
        "outstanding_invoices": out_n,
        "overdue_invoices": od_n,
        "revenue_collected": _f(collected),
        "revenue_invoiced": _f(invoiced),
        "outstanding_amount": _f(out_amt),
        "overdue_amount": _f(od_amt),
        "mrr": mrr(db, plan_id, customer_id),
        "discount_amount": _f(disc_amt),
        "discount_applications": disc_n,
    }
    months = months_between(date_from, date_to)
    return {
        "range": {"from": date_from, "to": date_to},
        "kpis": kpis,
        "monthly": monthly_series(db, date_from, date_to, months, plan_id, customer_id),
        "subscription_status": [{"state": str(k), "count": v} for k, v in sub_states.items()],
        "invoice_status": [{"state": str(k), "count": v} for k, v in inv_states.items()],
        "aging": aging(db, plan_id, customer_id),
        "renewals": renewal_overview(db, plan_id, customer_id),
        "billing_activity": billing_activity(db, t - timedelta(days=29), t),
        "top_overdue": top_overdue(db, plan_id, customer_id),
        "recent_activity": recent_activity(db),
    }


def monthly_series(db: Session, date_from, date_to, months, plan_id=None, customer_id=None) -> list[dict]:
    mk_i = month_key(db, Invoice.invoice_date)
    invoiced = dict(db.execute(_inv_filters(
        select(mk_i, func.sum(Invoice.total)).where(Invoice.state.in_(BILLED),
                                                    Invoice.invoice_date.between(date_from, date_to))
        .group_by(mk_i), plan_id, customer_id)).all())
    mk_p = month_key(db, Payment.payment_date)
    pstmt = (select(mk_p, func.sum(Payment.amount)).join(Invoice, Invoice.id == Payment.invoice_id)
             .where(Payment.status == PaymentStatus.posted, Payment.payment_date.between(date_from, date_to))
             .group_by(mk_p))
    collected = dict(db.execute(_inv_filters(pstmt, plan_id, customer_id)).all())
    mk_s = month_key(db, Subscription.start_date)
    new_subs = dict(db.execute(_sub_filters(
        select(mk_s, func.count()).where(Subscription.start_date.between(date_from, date_to),
                                         Subscription.state.in_([*LIVE, SubState.closed])).group_by(mk_s),
        plan_id, customer_id)).all())
    # active subscriptions at each month end — derived from start/closed dates
    rows = []
    for m in months:
        y, mo = map(int, m.split("-"))
        month_end = add_months(date(y, mo, 1), 1) - timedelta(days=1)
        active = db.scalar(_sub_filters(select(func.count()).select_from(Subscription).where(
            Subscription.state.in_([*LIVE, SubState.closed]), Subscription.start_date <= month_end,
            or_(Subscription.closed_at.is_(None), func.date(Subscription.closed_at) > month_end)),
            plan_id, customer_id))
        rows.append({"month": m, "invoiced": _f(invoiced.get(m)), "collected": _f(collected.get(m)),
                     "new_subscriptions": new_subs.get(m, 0), "active_subscriptions": active})
    return rows


def aging(db: Session, plan_id=None, customer_id=None) -> list[dict]:
    t = clock.today()
    due = Invoice.total - Invoice.amount_paid
    days = (t - Invoice.due_date) if db.get_bind().dialect.name == "postgresql" else \
        (func.julianday(t) - func.julianday(Invoice.due_date))
    buckets = [("Not yet due", Invoice.due_date >= t),
               ("1–30 days", and_(Invoice.due_date < t, days <= 30)),
               ("31–60 days", and_(days > 30, days <= 60)),
               ("61–90 days", and_(days > 60, days <= 90)),
               ("90+ days", days > 90)]
    out = []
    base = (Invoice.state == InvoiceState.confirmed, Invoice.total > Invoice.amount_paid)
    for label, cond in buckets:
        n, amt = db.execute(_inv_filters(select(func.count(), func.coalesce(func.sum(due), 0))
                                         .where(*base, cond), plan_id, customer_id)).one()
        out.append({"bucket": label, "count": n, "amount": _f(amt)})
    return out


def renewal_overview(db: Session, plan_id=None, customer_id=None) -> list[dict]:
    t = clock.today()

    def c(*conds):
        return db.scalar(_sub_filters(select(func.count()).select_from(Subscription).where(*conds),
                                      plan_id, customer_id))
    live = Subscription.state.in_(LIVE)
    return [
        {"label": "Expired, not renewed", "count": c(live, Subscription.end_date < t), "view": "expired"},
        {"label": "Next 7 days", "count": c(live, Subscription.end_date.between(t, t + timedelta(days=7))),
         "view": "expiring"},
        {"label": "8–30 days", "count": c(live, Subscription.end_date.between(t + timedelta(days=8),
                                                                              t + timedelta(days=30))),
         "view": "renewals"},
        {"label": "31–90 days", "count": c(live, Subscription.end_date.between(t + timedelta(days=31),
                                                                               t + timedelta(days=90))),
         "view": None},
        {"label": "No expiry (evergreen)", "count": c(live, Subscription.end_date.is_(None)), "view": None},
        {"label": "Renewed (all time)", "count": db.scalar(select(func.count(func.distinct(
            Subscription.id))).select_from(Subscription).join(Subscription.renewals)), "view": None},
    ]


def billing_activity(db: Session, start: date, end: date) -> list[dict]:
    rows = db.execute(select(BillingEvent.period_start, BillingEvent.status, func.count())
                      .where(BillingEvent.period_start.between(start, end))
                      .group_by(BillingEvent.period_start, BillingEvent.status)).all()
    by_day: dict[date, dict] = {}
    for d, status, n in rows:
        by_day.setdefault(d, {"invoiced": 0, "failed": 0, "pending": 0})[str(status)] = n
    out, d = [], start
    while d <= end:
        out.append({"date": d.isoformat(), **by_day.get(d, {"invoiced": 0, "failed": 0, "pending": 0})})
        d += timedelta(days=1)
    return out


def top_overdue(db: Session, plan_id=None, customer_id=None, limit=6) -> list[dict]:
    t = clock.today()
    stmt = (select(Invoice).where(Invoice.state == InvoiceState.confirmed, Invoice.due_date < t,
                                  Invoice.total > Invoice.amount_paid).order_by(Invoice.due_date).limit(limit))
    return [{"id": i.id, "number": i.number, "customer": i.customer.name, "due_date": i.due_date,
             "days_overdue": (t - i.due_date).days, "amount_due": _f(i.amount_due)}
            for i in db.scalars(_inv_filters(stmt, plan_id, customer_id)).all()]


def recent_activity(db: Session, limit=10) -> list[dict]:
    rows = db.execute(select(AuditLog, User.full_name).outerjoin(User, User.id == AuditLog.user_id)
                      .order_by(AuditLog.id.desc()).limit(limit)).all()
    return [{"id": a.id, "action": a.action, "entity": a.entity, "entity_id": a.entity_id,
             "user": name or "System", "at": a.created_at} for a, name in rows]


# ---------------- detailed reports ----------------
def report_subscriptions(db: Session, date_from=None, date_to=None, plan_id=None, customer_id=None) -> dict:
    by_plan = db.execute(_sub_filters(
        select(Plan.name, Plan.billing_period, func.count(Subscription.id),
               func.count(case((Subscription.state == SubState.active, 1))))
        .join(Plan).group_by(Plan.name, Plan.billing_period).order_by(func.count(Subscription.id).desc()),
        plan_id, customer_id)).all()
    by_freq = db.execute(_sub_filters(
        select(Plan.billing_period, func.count(Subscription.id)).join(Plan)
        .where(Subscription.state.in_(LIVE)).group_by(Plan.billing_period), plan_id, customer_id)).all()
    d = dashboard(db, date_from, date_to, plan_id, customer_id)
    return {
        "summary": {k: d["kpis"][k] for k in ("total_subscriptions", "active_subscriptions", "paused_subscriptions",
                                              "closed_subscriptions", "upcoming_renewals", "awaiting_confirmation")},
        "mrr": d["kpis"]["mrr"],
        "by_plan": [{"plan": n, "billing_period": str(p), "total": tot, "active": act} for n, p, tot, act in by_plan],
        "by_frequency": [{"billing_period": str(p), "count": n} for p, n in by_freq],
        "monthly": d["monthly"],
        "renewals": d["renewals"],
    }


def report_revenue(db: Session, date_from=None, date_to=None, plan_id=None, customer_id=None) -> dict:
    date_from, date_to = default_range(date_from, date_to)
    rng = (Invoice.state.in_(BILLED), Invoice.invoice_date.between(date_from, date_to))
    by_plan = db.execute(_inv_filters(
        select(Plan.name, func.sum(Invoice.total), func.sum(Invoice.amount_paid))
        .join(Subscription, Subscription.id == Invoice.subscription_id).join(Plan)
        .where(*rng).group_by(Plan.name).order_by(func.sum(Invoice.total).desc()), plan_id, customer_id)).all()
    by_product = db.execute(_inv_filters(
        select(Product.name, func.sum(InvoiceLine.taxable_amount), func.sum(InvoiceLine.quantity))
        .join(Invoice, Invoice.id == InvoiceLine.invoice_id).join(Product, Product.id == InvoiceLine.product_id)
        .where(*rng).group_by(Product.name).order_by(func.sum(InvoiceLine.taxable_amount).desc()),
        plan_id, customer_id)).all()
    by_customer = db.execute(_inv_filters(
        select(Customer.name, func.sum(Invoice.total), func.sum(Invoice.amount_paid))
        .join(Customer, Customer.id == Invoice.customer_id).where(*rng)
        .group_by(Customer.name).order_by(func.sum(Invoice.total).desc()).limit(25), plan_id, customer_id)).all()
    d = dashboard(db, date_from, date_to, plan_id, customer_id)
    k = d["kpis"]
    return {
        "range": d["range"],
        "summary": {"revenue_invoiced": k["revenue_invoiced"], "revenue_collected": k["revenue_collected"],
                    "outstanding_amount": k["outstanding_amount"], "overdue_amount": k["overdue_amount"],
                    "mrr": k["mrr"], "discount_amount": k["discount_amount"]},
        "monthly": d["monthly"],
        "by_plan": [{"plan": n, "invoiced": _f(t), "collected_on_these": _f(p)} for n, t, p in by_plan],
        "by_product": [{"product": n, "net_revenue": _f(t), "units": int(q or 0)} for n, t, q in by_product],
        "by_customer": [{"customer": n, "invoiced": _f(t), "paid": _f(p)} for n, t, p in by_customer],
    }


def report_invoices(db: Session, date_from=None, date_to=None, plan_id=None, customer_id=None) -> dict:
    d = dashboard(db, date_from, date_to, plan_id, customer_id)
    k = d["kpis"]
    return {"summary": {x: k[x] for x in ("total_invoices", "draft_invoices", "confirmed_invoices", "paid_invoices",
                                          "cancelled_invoices", "outstanding_invoices", "overdue_invoices",
                                          "outstanding_amount", "overdue_amount")},
            "status": d["invoice_status"], "aging": d["aging"], "top_overdue": top_overdue(db, plan_id,
                                                                                            customer_id, 25)}


def report_payments(db: Session, date_from=None, date_to=None, plan_id=None, customer_id=None) -> dict:
    date_from, date_to = default_range(date_from, date_to)
    base = [Payment.status == PaymentStatus.posted, Payment.payment_date.between(date_from, date_to)]
    if customer_id:
        base.append(Payment.customer_id == customer_id)
    by_method = db.execute(select(Payment.method, func.count(), func.sum(Payment.amount)).where(*base)
                           .group_by(Payment.method)).all()
    by_customer = db.execute(select(Customer.name, func.count(Payment.id), func.sum(Payment.amount))
                             .join(Customer, Customer.id == Payment.customer_id).where(*base)
                             .group_by(Customer.name).order_by(func.sum(Payment.amount).desc()).limit(25)).all()
    mk = month_key(db, Payment.payment_date)
    by_month = dict(db.execute(select(mk, func.sum(Payment.amount)).where(*base).group_by(mk)).all())
    alloc = db.execute(select(Invoice.state, func.count(), func.sum(Invoice.amount_paid), func.sum(Invoice.total))
                       .where(Invoice.state.in_(BILLED)).group_by(Invoice.state)).all()
    partial = db.scalar(select(func.count()).select_from(Invoice).where(
        Invoice.state == InvoiceState.confirmed, Invoice.amount_paid > 0))
    total_n, total_amt = db.execute(select(func.count(), func.coalesce(func.sum(Payment.amount), 0)).where(*base)).one()
    voided = db.scalar(select(func.count()).select_from(Payment).where(Payment.status == PaymentStatus.voided))
    return {
        "range": {"from": date_from, "to": date_to},
        "summary": {"payments": total_n, "amount": _f(total_amt), "voided": voided,
                    "partially_paid_invoices": partial},
        "by_method": [{"method": str(m), "count": n, "amount": _f(a)} for m, n, a in by_method],
        "by_customer": [{"customer": c, "count": n, "amount": _f(a)} for c, n, a in by_customer],
        "by_month": [{"month": m, "amount": _f(by_month.get(m))} for m in months_between(date_from, date_to)],
        "allocation": [{"state": str(s), "invoices": n, "allocated": _f(p), "invoiced": _f(t)}
                       for s, n, p, t in alloc],
    }


def report_discounts(db: Session) -> dict:
    from app.services.discounts import consumed_usage, reserved_usage
    t = clock.today()
    rules = db.scalars(select(DiscountRule).order_by(DiscountRule.id)).all()
    rows = []
    for r in rules:
        consumed, reserved = consumed_usage(db, r.id), reserved_usage(db, r.id)
        amt = db.scalar(select(func.coalesce(func.sum(DiscountApplication.amount), 0))
                        .join(Invoice, Invoice.id == DiscountApplication.invoice_id)
                        .where(DiscountApplication.discount_id == r.id, Invoice.state.in_(BILLED)))
        expired = r.end_date is not None and r.end_date < t
        rows.append({"id": r.id, "name": r.name, "type": str(r.discount_type), "value": _f(r.value),
                     "status": "expired" if expired else ("active" if r.is_active else "inactive"),
                     "used": consumed, "reserved": reserved, "max_usage": r.max_usage,
                     "remaining": (r.max_usage - reserved) if r.max_usage is not None else None,
                     "total_discounted": _f(amt), "end_date": r.end_date})
    return {"summary": {"active": sum(1 for r in rows if r["status"] == "active"),
                        "expired": sum(1 for r in rows if r["status"] == "expired"),
                        "total_discounted": round(sum(r["total_discounted"] for r in rows), 2),
                        "applications": sum(r["used"] for r in rows)},
            "rules": rows}
