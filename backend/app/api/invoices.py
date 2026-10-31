from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.api.serializers import inv_detail, inv_row
from app.api.util import Paging, page
from app.core import clock
from app.core.db import SessionLocal, get_db
from app.core.deps import any_user, internal
from app.models import (
    AutomationRun, BillingEvent, BillingEventStatus, Customer, Invoice, InvoiceState, Role, Subscription, User,
)
from app.schemas.business import ActionIn, BillingEventOut, InvoiceOut, InvoiceRow
from app.schemas.common import Msg, Page
from app.services import invoices as svc
from app.services.billing import retry_event, run_billing
from app.services.common import get_setting
from app.services.errors import NotFound
from app.services.pdf import invoice_pdf

router = APIRouter(tags=["invoices"])


def overdue_clause():
    return and_(Invoice.state == InvoiceState.confirmed, Invoice.due_date < clock.today(),
                Invoice.total > Invoice.amount_paid)


def get_invoice_for(db: Session, inv_id: int, user: User, *, for_update=False) -> Invoice:
    stmt = select(Invoice).where(Invoice.id == inv_id)
    if for_update and db.get_bind().dialect.name == "postgresql":
        stmt = stmt.with_for_update(of=Invoice)
    inv = db.scalars(stmt).first()
    # customers can only ever load their own invoices; others get a 404 (no existence leak)
    if not inv or (user.role == Role.customer and (not user.customer or inv.customer_id != user.customer.id)):
        raise NotFound("Invoice not found")
    return inv


@router.get("/invoices", response_model=Page[InvoiceRow])
def list_invoices(state: str | None = None, overdue: bool | None = None, customer_id: int | None = None,
                  subscription_id: int | None = None, q: str | None = None, date_from: date | None = None,
                  date_to: date | None = None, outstanding: bool | None = None, paging: Paging = Depends(),
                  _: User = Depends(internal), db: Session = Depends(get_db)):
    stmt = (select(Invoice).join(Customer)
            .options(joinedload(Invoice.customer), joinedload(Invoice.subscription)))
    if state:
        stmt = stmt.where(Invoice.state.in_([InvoiceState(s) for s in state.split(",")]))
    if overdue:
        stmt = stmt.where(overdue_clause())
    if outstanding:
        stmt = stmt.where(Invoice.state == InvoiceState.confirmed, Invoice.total > Invoice.amount_paid)
    if customer_id:
        stmt = stmt.where(Invoice.customer_id == customer_id)
    if subscription_id:
        stmt = stmt.where(Invoice.subscription_id == subscription_id)
    if date_from:
        stmt = stmt.where(Invoice.invoice_date >= date_from)
    if date_to:
        stmt = stmt.where(Invoice.invoice_date <= date_to)
    if q:
        stmt = stmt.where(or_(Invoice.number.ilike(f"%{q}%"), Customer.name.ilike(f"%{q}%")))
    total = db.scalar(select(func.count()).select_from(stmt.with_only_columns(Invoice.id).subquery()))
    rows = db.scalars(stmt.order_by(Invoice.invoice_date.desc(), Invoice.id.desc()).limit(paging.page_size)
                      .offset((paging.page - 1) * paging.page_size)).all()
    return page([inv_row(i) for i in rows], total, paging)


@router.get("/invoices/{inv_id}", response_model=InvoiceOut)
def get_invoice(inv_id: int, user: User = Depends(any_user), db: Session = Depends(get_db)):
    return inv_detail(get_invoice_for(db, inv_id, user), user)


@router.get("/invoices/{inv_id}/pdf")
def invoice_pdf_download(inv_id: int, user: User = Depends(any_user), db: Session = Depends(get_db)):
    inv = get_invoice_for(db, inv_id, user)
    if inv.state == InvoiceState.draft and user.role == Role.customer:
        raise NotFound("Invoice not found")
    data = invoice_pdf(inv, get_setting(db, "company_name"))
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{inv.number}.pdf"'})


@router.post("/invoices/{inv_id}/actions/{action}", response_model=InvoiceOut)
def invoice_action(inv_id: int, action: str, data: ActionIn | None = None, user: User = Depends(internal),
                   db: Session = Depends(get_db)):
    inv = get_invoice_for(db, inv_id, user, for_update=True)
    if action == "confirm":
        svc.confirm_invoice(db, user, inv)
    elif action == "cancel":
        svc.cancel_invoice(db, user, inv, (data.reason if data else None))
    else:
        raise HTTPException(404, f"Unknown action '{action}'")
    db.commit()
    db.refresh(inv)
    return inv_detail(inv, user)


@router.post("/invoices/{inv_id}/send", response_model=Msg)
def send(inv_id: int, user: User = Depends(internal), db: Session = Depends(get_db)):
    inv = get_invoice_for(db, inv_id, user)
    status = svc.send_invoice(db, user, inv)
    db.commit()
    if status == "sent":
        return Msg(message=f"Invoice {inv.number} emailed to {inv.customer.email}", detail={"email_status": status})
    return Msg(message="Email delivery is not configured on this server. The invoice email was recorded in the "
                       "outbox but was NOT sent — download the PDF to share it.", detail={"email_status": status})


# --------------- billing operations ---------------
@router.get("/billing/events", response_model=Page[BillingEventOut])
def billing_events(status: str | None = None, subscription_id: int | None = None, paging: Paging = Depends(),
                   _: User = Depends(internal), db: Session = Depends(get_db)):
    stmt = select(BillingEvent).order_by(BillingEvent.id.desc())
    if status:
        stmt = stmt.where(BillingEvent.status == BillingEventStatus(status))
    if subscription_id:
        stmt = stmt.where(BillingEvent.subscription_id == subscription_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.limit(paging.page_size).offset((paging.page - 1) * paging.page_size)).all()
    items = []
    for e in rows:
        o = BillingEventOut.model_validate(e)
        if e.invoice:
            o.invoice_id, o.invoice_number = e.invoice.id, e.invoice.number
        items.append(o)
    return page(items, total, paging)


@router.post("/billing/events/{event_id}/retry", response_model=Msg)
def retry(event_id: int, user: User = Depends(internal), db: Session = Depends(get_db)):
    r = retry_event(db, event_id, user)
    if r.failed:
        raise HTTPException(400, f"Retry failed: {r.error}")
    return Msg(message=f"Retry complete — {r.created} invoice(s) generated", detail={"created": r.created})


@router.post("/billing/run", response_model=Msg)
def run_now(user: User = Depends(internal)):
    """Run the billing engine immediately for everything due today (same code path as the nightly job)."""
    run: AutomationRun = run_billing(SessionLocal, clock.today(), trigger="manual", user_id=user.id)
    return Msg(message=run.message or run.status,
               detail={"status": run.status, "created": run.created, "processed": run.processed,
                       "failed": run.failed, "run_id": run.id})
