from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.serializers import inv_detail, sub_detail, sub_row, upcoming_window
from app.api.util import Paging, page
from app.core.db import get_db
from app.core.deps import internal
from app.core.money import ZERO
from app.models import (
    BillingPeriod, Customer, Plan, SubState, Subscription, SubscriptionLine, User,
)
from app.schemas.business import ActionIn, SubscriptionIn, SubscriptionOut, SubscriptionRow, SubscriptionUpdate
from app.schemas.business import InvoiceOut
from app.schemas.common import Page
from app.services import subscriptions as svc
from app.services.billing import bill_next_period_now

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


def _lines(data):
    return [svc.LineInput(l.product_id, l.variant_id, l.quantity, l.unit_price, l.tax_id) for l in data]


@router.get("", response_model=Page[SubscriptionRow])
def list_subscriptions(
    state: str | None = Query(None, description="comma-separated states"),
    customer_id: int | None = None, plan_id: int | None = None, billing_period: str | None = None,
    q: str | None = None, view: str | None = Query(None, description="quotations|renewals|expiring|expired"),
    start_from: date | None = None, start_to: date | None = None, demo: bool | None = None,
    paging: Paging = Depends(), _: User = Depends(internal), db: Session = Depends(get_db),
):
    stmt = (select(Subscription).join(Customer).join(Plan)
            .options(joinedload(Subscription.customer), joinedload(Subscription.plan),
                     selectinload(Subscription.lines).joinedload(SubscriptionLine.tax)))
    if state:
        stmt = stmt.where(Subscription.state.in_([SubState(s) for s in state.split(",")]))
    if view == "quotations":
        stmt = stmt.where(Subscription.state.in_([SubState.draft, SubState.quotation]))
    t0, t30 = upcoming_window(30)
    if view == "renewals":
        stmt = stmt.where(Subscription.state.in_([SubState.active, SubState.paused]),
                          Subscription.end_date.between(t0, t30))
    if view == "expiring":
        stmt = stmt.where(Subscription.state.in_([SubState.active, SubState.paused]),
                          Subscription.end_date.between(t0, upcoming_window(7)[1]))
    if view == "expired":
        stmt = stmt.where(Subscription.state.in_([SubState.active, SubState.paused]), Subscription.end_date < t0)
    if customer_id:
        stmt = stmt.where(Subscription.customer_id == customer_id)
    if plan_id:
        stmt = stmt.where(Subscription.plan_id == plan_id)
    if billing_period:
        stmt = stmt.where(Plan.billing_period == BillingPeriod(billing_period))
    if start_from:
        stmt = stmt.where(Subscription.start_date >= start_from)
    if start_to:
        stmt = stmt.where(Subscription.start_date <= start_to)
    if demo is not None:
        stmt = stmt.where(Subscription.is_demo.is_(demo))
    if q:
        stmt = stmt.where(or_(Subscription.number.ilike(f"%{q}%"), Customer.name.ilike(f"%{q}%"),
                              Plan.name.ilike(f"%{q}%")))
    total = db.scalar(select(func.count()).select_from(stmt.with_only_columns(Subscription.id).subquery()))
    rows = db.scalars(stmt.order_by(Subscription.id.desc()).limit(paging.page_size)
                      .offset((paging.page - 1) * paging.page_size)).unique().all()
    return page([sub_row(s) for s in rows], total, paging)


@router.post("", response_model=SubscriptionOut, status_code=201)
def create(data: SubscriptionIn, user: User = Depends(internal), db: Session = Depends(get_db)):
    sub = svc.create_subscription(
        db, user, customer_id=data.customer_id, plan_id=data.plan_id, lines=_lines(data.lines),
        template_id=data.template_id, start_date=data.start_date, end_date=data.end_date,
        payment_terms_days=data.payment_terms_days, valid_until=data.valid_until, notes=data.notes,
    )
    db.commit()
    db.refresh(sub)
    return sub_detail(db, sub, user)


@router.get("/{sub_id}", response_model=SubscriptionOut)
def get(sub_id: int, user: User = Depends(internal), db: Session = Depends(get_db)):
    return sub_detail(db, svc.get_subscription(db, sub_id), user)


@router.put("/{sub_id}", response_model=SubscriptionOut)
def update(sub_id: int, data: SubscriptionUpdate, user: User = Depends(internal), db: Session = Depends(get_db)):
    sub = svc.get_subscription(db, sub_id, for_update=True)
    fields = data.model_dump(exclude={"lines"}, exclude_unset=True)
    svc.update_subscription(db, user, sub, lines=_lines(data.lines) if data.lines is not None else None, **fields)
    db.commit()
    db.refresh(sub)
    return sub_detail(db, sub, user)


ACTIONS = {
    "send": lambda db, u, s, a: svc.send_quotation(db, u, s),
    "extend": lambda db, u, s, a: svc.extend_quotation(db, u, s, a.days or 30),
    "confirm": lambda db, u, s, a: svc.confirm(db, u, s),
    "activate": lambda db, u, s, a: svc.activate(db, u, s, a.start_date),
    "pause": lambda db, u, s, a: svc.pause(db, u, s, a.reason),
    "resume": lambda db, u, s, a: svc.resume(db, u, s),
    "close": lambda db, u, s, a: svc.close(db, u, s, a.reason),
    "cancel": lambda db, u, s, a: svc.cancel(db, u, s, a.reason),
    "renew": lambda db, u, s, a: svc.renew(db, u, s),
}


@router.post("/{sub_id}/actions/{action}", response_model=SubscriptionOut)
def act(sub_id: int, action: str, data: ActionIn | None = None, user: User = Depends(internal),
        db: Session = Depends(get_db)):
    if action not in ACTIONS:
        raise HTTPException(404, f"Unknown action '{action}'")
    sub = svc.get_subscription(db, sub_id, for_update=True)
    ACTIONS[action](db, user, sub, data or ActionIn())
    db.commit()
    db.refresh(sub)
    return sub_detail(db, sub, user)


@router.post("/{sub_id}/invoice-now", response_model=InvoiceOut)
def invoice_now(sub_id: int, user: User = Depends(internal), db: Session = Depends(get_db)):
    sub = svc.get_subscription(db, sub_id)
    inv = bill_next_period_now(db, sub, user)
    db.refresh(inv)
    return inv_detail(inv, user)
