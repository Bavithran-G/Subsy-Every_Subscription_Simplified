from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.api.serializers import pay_out
from app.api.util import Paging, page
from app.core.db import get_db
from app.core.deps import admin_only, internal
from app.models import Customer, Payment, PaymentMethod, PaymentStatus, User
from app.schemas.business import PaymentIn, PaymentOut, VoidIn
from app.schemas.common import Page
from app.services import payments as svc

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("", response_model=Page[PaymentOut])
def list_payments(customer_id: int | None = None, invoice_id: int | None = None, method: str | None = None,
                  status: str | None = None, date_from: date | None = None, date_to: date | None = None,
                  q: str | None = None, paging: Paging = Depends(), _: User = Depends(internal),
                  db: Session = Depends(get_db)):
    stmt = (select(Payment).join(Customer)
            .options(joinedload(Payment.customer), joinedload(Payment.invoice), joinedload(Payment.recorded_by)))
    if customer_id:
        stmt = stmt.where(Payment.customer_id == customer_id)
    if invoice_id:
        stmt = stmt.where(Payment.invoice_id == invoice_id)
    if method:
        stmt = stmt.where(Payment.method == PaymentMethod(method))
    if status:
        stmt = stmt.where(Payment.status == PaymentStatus(status))
    if date_from:
        stmt = stmt.where(Payment.payment_date >= date_from)
    if date_to:
        stmt = stmt.where(Payment.payment_date <= date_to)
    if q:
        stmt = stmt.where(or_(Payment.reference.ilike(f"%{q}%"), Customer.name.ilike(f"%{q}%")))
    total = db.scalar(select(func.count()).select_from(stmt.with_only_columns(Payment.id).subquery()))
    rows = db.scalars(stmt.order_by(Payment.payment_date.desc(), Payment.id.desc()).limit(paging.page_size)
                      .offset((paging.page - 1) * paging.page_size)).all()
    return page([pay_out(p) for p in rows], total, paging)


@router.post("", response_model=PaymentOut, status_code=201)
def record(data: PaymentIn, user: User = Depends(internal), db: Session = Depends(get_db)):
    p = svc.record_payment(db, user, invoice_id=data.invoice_id, amount=data.amount,
                           method=PaymentMethod(data.method), payment_date=data.payment_date, note=data.note,
                           reference=data.reference, customer_id=data.customer_id)
    db.commit()
    db.refresh(p)
    return pay_out(p)


@router.post("/{payment_id}/void", response_model=PaymentOut)
def void(payment_id: int, data: VoidIn, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    p = svc.void_payment(db, user, payment_id, data.reason)
    db.commit()
    db.refresh(p)
    return pay_out(p)
