import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import internal
from app.models import User
from app.services import reports as rpt

router = APIRouter(prefix="/reports", tags=["reports"])

TABLES = {  # which list in each report is exported to CSV
    "subscriptions": "by_plan", "revenue": "monthly", "invoices": "top_overdue", "payments": "by_method",
    "discounts": "rules",
}


@router.get("/dashboard")
def dashboard(date_from: date | None = None, date_to: date | None = None, plan_id: int | None = None,
              customer_id: int | None = None, _: User = Depends(internal), db: Session = Depends(get_db)):
    return rpt.dashboard(db, date_from, date_to, plan_id, customer_id)


def _get(name, db, date_from, date_to, plan_id, customer_id):
    if name == "subscriptions":
        return rpt.report_subscriptions(db, date_from, date_to, plan_id, customer_id)
    if name == "revenue":
        return rpt.report_revenue(db, date_from, date_to, plan_id, customer_id)
    if name == "invoices":
        return rpt.report_invoices(db, date_from, date_to, plan_id, customer_id)
    if name == "payments":
        return rpt.report_payments(db, date_from, date_to, plan_id, customer_id)
    if name == "discounts":
        return rpt.report_discounts(db)
    raise HTTPException(404, "Unknown report")


@router.get("/{name}")
def report(name: str, date_from: date | None = None, date_to: date | None = None, plan_id: int | None = None,
           customer_id: int | None = None, _: User = Depends(internal), db: Session = Depends(get_db)):
    return _get(name, db, date_from, date_to, plan_id, customer_id)


@router.get("/{name}/csv")
def report_csv(name: str, table: str | None = None, date_from: date | None = None, date_to: date | None = None,
               plan_id: int | None = None, customer_id: int | None = None, _: User = Depends(internal),
               db: Session = Depends(get_db)):
    data = _get(name, db, date_from, date_to, plan_id, customer_id)
    key = table or TABLES[name]
    rows = data.get(key)
    if not isinstance(rows, list):
        raise HTTPException(404, f"Report '{name}' has no table '{key}'")
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="subsy-{name}-{key}.csv"'})
