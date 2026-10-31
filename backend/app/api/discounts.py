from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.db import get_db
from app.core.deps import admin_only, internal
from app.models import DiscountApplication, DiscountRule, DiscountType, Invoice, InvoiceState, Product, Subscription, User
from app.schemas.business import DiscountIn, DiscountOut
from app.services.common import audit
from app.services.discounts import consumed_usage, reserved_usage

router = APIRouter(prefix="/discounts", tags=["discounts"])


def disc_out(db: Session, r: DiscountRule) -> DiscountOut:
    o = DiscountOut.model_validate(r)
    o.product_ids = [p.id for p in r.products]
    o.subscription_ids = [s.id for s in r.subscriptions]
    o.usage_consumed = consumed_usage(db, r.id)
    o.usage_reserved = reserved_usage(db, r.id)
    o.total_discounted = db.scalar(
        select(func.coalesce(func.sum(DiscountApplication.amount), 0))
        .join(Invoice, Invoice.id == DiscountApplication.invoice_id)
        .where(DiscountApplication.discount_id == r.id,
               Invoice.state.in_([InvoiceState.confirmed, InvoiceState.paid]))) or Decimal(0)
    t = clock.today()
    if not r.is_active:
        o.status = "inactive"
    elif r.end_date and r.end_date < t:
        o.status = "expired"
    elif r.start_date and r.start_date > t:
        o.status = "scheduled"
    elif r.max_usage is not None and o.usage_reserved >= r.max_usage:
        o.status = "exhausted"
    else:
        o.status = "active"
    return o


def _apply(db: Session, r: DiscountRule, data: DiscountIn):
    if data.discount_type == "percentage" and data.value > 100:
        raise HTTPException(422, "Percentage discount cannot exceed 100")
    if data.start_date and data.end_date and data.end_date < data.start_date:
        raise HTTPException(422, "End date must be on or after the start date")
    if data.scope == "products" and not data.product_ids:
        raise HTTPException(422, "Select at least one product for a product-scoped discount")
    for k, v in data.model_dump(exclude={"product_ids", "subscription_ids"}).items():
        setattr(r, k, v)
    r.products = list(db.scalars(select(Product).where(Product.id.in_(data.product_ids)))) if data.product_ids else []
    r.subscriptions = (list(db.scalars(select(Subscription).where(Subscription.id.in_(data.subscription_ids))))
                       if data.subscription_ids else [])
    if len(r.products) != len(set(data.product_ids)):
        raise HTTPException(422, "Unknown product in discount")
    if len(r.subscriptions) != len(set(data.subscription_ids)):
        raise HTTPException(422, "Unknown subscription in discount")


@router.get("", response_model=list[DiscountOut])
def list_discounts(_: User = Depends(internal), db: Session = Depends(get_db)):
    return [disc_out(db, r) for r in db.scalars(select(DiscountRule).order_by(DiscountRule.id.desc())).all()]


@router.post("", response_model=DiscountOut, status_code=201)
def create(data: DiscountIn, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    if db.scalar(select(DiscountRule.id).where(func.lower(DiscountRule.name) == data.name.lower())):
        raise HTTPException(409, "A discount with this name already exists")
    r = DiscountRule()
    _apply(db, r, data)
    db.add(r)
    db.flush()
    audit(db, user.id, "discount.create", "discount", r.id, type=data.discount_type, value=str(data.value))
    db.commit()
    return disc_out(db, r)


@router.put("/{rule_id}", response_model=DiscountOut)
def update(rule_id: int, data: DiscountIn, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    r = db.get(DiscountRule, rule_id)
    if not r:
        raise HTTPException(404, "Discount not found")
    if data.max_usage is not None and data.max_usage < consumed_usage(db, r.id):
        raise HTTPException(422, "Maximum usage cannot be lower than the usage already consumed")
    _apply(db, r, data)
    audit(db, user.id, "discount.update", "discount", r.id)
    db.commit()
    return disc_out(db, r)
