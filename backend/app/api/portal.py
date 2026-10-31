"""Customer self-service. Every query here is scoped to the signed-in customer's own customer_id on the server."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.serializers import inv_row, pay_out, sub_detail, sub_row
from app.api.util import Paging, page
from app.core import clock
from app.core.db import get_db
from app.core.deps import require
from app.models import (
    Customer, Invoice, InvoiceState, Payment, PaymentStatus, Role, SubState, Subscription, User,
)
from app.schemas.business import ActionIn, InvoiceRow, PaymentOut, SubscriptionOut, SubscriptionRow
from app.schemas.common import CustomerOut, CustomerUpdate, Page
from app.services import subscriptions as svc
from app.services.common import audit
from app.services.errors import NotFound

router = APIRouter(prefix="/portal", tags=["portal"])
customer_only = require(Role.customer)
VISIBLE_SUB_STATES = [SubState.quotation, SubState.confirmed, SubState.active, SubState.paused, SubState.closed]
VISIBLE_INV_STATES = [InvoiceState.confirmed, InvoiceState.paid, InvoiceState.cancelled]


def me_customer(user: User) -> Customer:
    if not user.customer:
        raise HTTPException(404, "No customer profile is linked to this account")
    return user.customer


def own_sub(db: Session, user: User, sub_id: int, for_update=False) -> Subscription:
    sub = svc.get_subscription(db, sub_id, for_update=for_update)
    if sub.customer_id != me_customer(user).id or sub.state not in VISIBLE_SUB_STATES:
        raise NotFound("Subscription not found")
    return sub


@router.get("/profile", response_model=CustomerOut)
def profile(user: User = Depends(customer_only)):
    return me_customer(user)


@router.patch("/profile", response_model=CustomerOut)
def update_profile(data: CustomerUpdate, user: User = Depends(customer_only), db: Session = Depends(get_db)):
    c = me_customer(user)
    for k, v in data.model_dump(exclude_unset=True, exclude={"segment"}).items():
        setattr(c, k, v)
    audit(db, user.id, "portal.profile_update", "customer", c.id)
    db.commit()
    return c


@router.get("/summary")
def summary(user: User = Depends(customer_only), db: Session = Depends(get_db)):
    c = me_customer(user)
    t = clock.today()
    states = dict(db.execute(select(Subscription.state, func.count()).where(Subscription.customer_id == c.id)
                             .group_by(Subscription.state)).all())
    due_n, due_amt = db.execute(select(func.count(), func.coalesce(func.sum(Invoice.total - Invoice.amount_paid), 0))
                                .where(Invoice.customer_id == c.id, Invoice.state == InvoiceState.confirmed)).one()
    od_n = db.scalar(select(func.count()).select_from(Invoice).where(
        Invoice.customer_id == c.id, Invoice.state == InvoiceState.confirmed, Invoice.due_date < t,
        Invoice.total > Invoice.amount_paid))
    paid_total = db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(
        Payment.customer_id == c.id, Payment.status == PaymentStatus.posted))
    nxt = db.execute(select(Subscription.number, Subscription.end_date).where(
        Subscription.customer_id == c.id, Subscription.state.in_([SubState.active, SubState.paused]),
        Subscription.end_date >= t).order_by(Subscription.end_date).limit(1)).first()
    return {
        "customer": {"name": c.name, "company": c.company, "email": c.email},
        "active_subscriptions": states.get(SubState.active, 0),
        "paused_subscriptions": states.get(SubState.paused, 0),
        "pending_quotations": states.get(SubState.quotation, 0),
        "open_invoices": due_n, "outstanding": float(due_amt), "overdue_invoices": od_n,
        "total_paid": float(paid_total),
        "next_renewal": {"number": nxt[0], "end_date": nxt[1]} if nxt else None,
    }


@router.get("/subscriptions", response_model=list[SubscriptionRow])
def my_subscriptions(user: User = Depends(customer_only), db: Session = Depends(get_db)):
    c = me_customer(user)
    subs = db.scalars(select(Subscription).where(Subscription.customer_id == c.id,
                                                 Subscription.state.in_(VISIBLE_SUB_STATES))
                      .order_by(Subscription.id.desc())).all()
    return [sub_row(s) for s in subs]


@router.get("/subscriptions/{sub_id}", response_model=SubscriptionOut)
def my_subscription(sub_id: int, user: User = Depends(customer_only), db: Session = Depends(get_db)):
    return sub_detail(db, own_sub(db, user, sub_id), user)


PORTAL_ACTIONS = {"pause", "resume", "renew"}


@router.post("/subscriptions/{sub_id}/actions/{action}", response_model=SubscriptionOut)
def my_subscription_action(sub_id: int, action: str, data: ActionIn | None = None,
                           user: User = Depends(customer_only), db: Session = Depends(get_db)):
    if action not in PORTAL_ACTIONS:
        raise HTTPException(403, "This action is not available in the customer portal")
    sub = own_sub(db, user, sub_id, for_update=True)
    reason = (data.reason if data else None) or "Requested by customer via portal"
    if action == "pause":
        svc.pause(db, user, sub, reason)
    elif action == "resume":
        svc.resume(db, user, sub)
    else:
        svc.renew(db, user, sub)
    db.commit()
    db.refresh(sub)
    return sub_detail(db, sub, user)


@router.get("/invoices", response_model=Page[InvoiceRow])
def my_invoices(state: str | None = None, paging: Paging = Depends(), user: User = Depends(customer_only),
                db: Session = Depends(get_db)):
    c = me_customer(user)
    states = [InvoiceState(s) for s in state.split(",")] if state else VISIBLE_INV_STATES
    states = [s for s in states if s in VISIBLE_INV_STATES]  # draft invoices are internal
    stmt = select(Invoice).where(Invoice.customer_id == c.id, Invoice.state.in_(states))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Invoice.invoice_date.desc()).limit(paging.page_size)
                      .offset((paging.page - 1) * paging.page_size)).all()
    return page([inv_row(i) for i in rows], total, paging)


@router.get("/payments", response_model=list[PaymentOut])
def my_payments(user: User = Depends(customer_only), db: Session = Depends(get_db)):
    c = me_customer(user)
    rows = db.scalars(select(Payment).where(Payment.customer_id == c.id).order_by(Payment.payment_date.desc())
                      .limit(200)).all()
    return [pay_out(p) for p in rows]
