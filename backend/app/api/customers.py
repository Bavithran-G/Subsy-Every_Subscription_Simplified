from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.api.util import Paging, page
from app.core.db import get_db
from app.core.deps import admin_only, internal
from app.models import Customer, Invoice, InvoiceState, SubState, Subscription, User
from app.schemas.common import CustomerIn, CustomerOut, CustomerRow, CustomerUpdate, Page
from app.services.common import audit

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=Page[CustomerRow])
def list_customers(q: str | None = None, segment: str | None = None, paging: Paging = Depends(),
                   _: User = Depends(internal), db: Session = Depends(get_db)):
    active_subs = (select(Subscription.customer_id, func.count().label("n"))
                   .where(Subscription.state == SubState.active).group_by(Subscription.customer_id).subquery())
    outstanding = (select(Invoice.customer_id, func.sum(Invoice.total - Invoice.amount_paid).label("due"))
                   .where(Invoice.state == InvoiceState.confirmed).group_by(Invoice.customer_id).subquery())
    stmt = (select(Customer, func.coalesce(active_subs.c.n, 0), func.coalesce(outstanding.c.due, 0))
            .outerjoin(active_subs, active_subs.c.customer_id == Customer.id)
            .outerjoin(outstanding, outstanding.c.customer_id == Customer.id))
    if q:
        stmt = stmt.where(or_(Customer.name.ilike(f"%{q}%"), Customer.email.ilike(f"%{q}%"),
                              Customer.company.ilike(f"%{q}%")))
    if segment:
        stmt = stmt.where(Customer.segment == segment)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(Customer.name).limit(paging.page_size)
                      .offset((paging.page - 1) * paging.page_size)).all()
    items = []
    for c, n, due in rows:
        r = CustomerRow.model_validate(c)
        r.active_subscriptions, r.outstanding = n, Decimal(due)
        items.append(r)
    return page(items, total, paging)


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: int, _: User = Depends(internal), db: Session = Depends(get_db)):
    c = db.get(Customer, customer_id)
    if not c:
        raise HTTPException(404, "Customer not found")
    return c


@router.post("", response_model=CustomerOut, status_code=201)
def create_customer(data: CustomerIn, user: User = Depends(internal), db: Session = Depends(get_db)):
    email = data.email.lower()
    if db.scalar(select(Customer.id).where(func.lower(Customer.email) == email)):
        raise HTTPException(409, "A customer with this email already exists")
    c = Customer(**data.model_dump(exclude={"email"}), email=email)
    db.add(c)
    db.flush()
    audit(db, user.id, "customer.create", "customer", c.id)
    db.commit()
    return c


@router.patch("/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: int, data: CustomerUpdate, user: User = Depends(internal),
                    db: Session = Depends(get_db)):
    c = db.get(Customer, customer_id)
    if not c:
        raise HTTPException(404, "Customer not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    audit(db, user.id, "customer.update", "customer", c.id)
    db.commit()
    return c
