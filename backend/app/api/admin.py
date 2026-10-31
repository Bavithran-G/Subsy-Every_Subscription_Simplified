from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.util import Paging, page
from app.automation import jobs
from app.core import clock
from app.core.config import get_settings
from app.core.db import SessionLocal, get_db
from app.core.deps import admin_only, any_user, internal
from app.models import AuditLog, AutomationRun, EmailOutbox, Notification, User
from app.services.common import SETTING_DEFAULTS, audit, get_setting, set_setting

router = APIRouter(tags=["admin"])


class SettingsIn(BaseModel):
    auto_confirm_invoices: bool | None = None
    company_name: str | None = None


@router.get("/admin/settings")
def get_settings_(_: User = Depends(internal), db: Session = Depends(get_db)):
    s = get_settings()
    return {
        "auto_confirm_invoices": get_setting(db, "auto_confirm_invoices") == "true",
        "company_name": get_setting(db, "company_name"),
        "currency": get_setting(db, "currency"),
        "email_delivery": "smtp" if s.smtp_host else "outbox (SMTP not configured — emails are not sent)",
        "scheduler_enabled": s.scheduler_enabled,
        "billing_time": f"{s.billing_cron_hour:02d}:00 Asia/Kolkata daily",
        "business_date": clock.today(),
    }


@router.put("/admin/settings")
def put_settings(data: SettingsIn, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    if data.auto_confirm_invoices is not None:
        set_setting(db, "auto_confirm_invoices", "true" if data.auto_confirm_invoices else "false")
    if data.company_name:
        set_setting(db, "company_name", data.company_name.strip()[:120])
    audit(db, user.id, "settings.update", "settings", None, **data.model_dump(exclude_none=True))
    db.commit()
    return get_settings_(user, db)


@router.get("/admin/automation/runs")
def automation_runs(job: str | None = None, paging: Paging = Depends(), _: User = Depends(internal),
                    db: Session = Depends(get_db)):
    stmt = select(AutomationRun).order_by(AutomationRun.id.desc())
    if job:
        stmt = stmt.where(AutomationRun.job == job)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.limit(paging.page_size).offset((paging.page - 1) * paging.page_size)).all()
    return page([{c.name: getattr(r, c.name) for c in AutomationRun.__table__.columns} for r in rows], total, paging)


@router.post("/admin/automation/{job}/run")
def run_job(job: str, user: User = Depends(admin_only)):
    if job not in jobs.JOBS and job != "all":
        raise HTTPException(404, "Unknown job")
    runs = jobs.run_daily(SessionLocal, trigger="manual") if job == "all" else \
        [jobs.JOBS[job](SessionLocal, None, "manual")]
    return [{"job": r.job, "status": r.status, "message": r.message, "created": r.created} for r in runs]


@router.get("/admin/audit")
def audit_log(action: str | None = None, paging: Paging = Depends(), _: User = Depends(admin_only),
              db: Session = Depends(get_db)):
    stmt = select(AuditLog, User.full_name).outerjoin(User, User.id == AuditLog.user_id).order_by(AuditLog.id.desc())
    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"{action}%"))
    total = db.scalar(select(func.count()).select_from(stmt.with_only_columns(AuditLog.id).subquery()))
    rows = db.execute(stmt.limit(paging.page_size).offset((paging.page - 1) * paging.page_size)).all()
    return page([{"id": a.id, "action": a.action, "entity": a.entity, "entity_id": a.entity_id, "detail": a.detail,
                  "user": n or "System", "created_at": a.created_at} for a, n in rows], total, paging)


@router.get("/admin/outbox")
def outbox(paging: Paging = Depends(), _: User = Depends(admin_only), db: Session = Depends(get_db)):
    stmt = select(EmailOutbox).order_by(EmailOutbox.id.desc())
    total = db.scalar(select(func.count()).select_from(EmailOutbox))
    rows = db.scalars(stmt.limit(paging.page_size).offset((paging.page - 1) * paging.page_size)).all()
    return page([{c.name: getattr(r, c.name) for c in EmailOutbox.__table__.columns} for r in rows], total, paging)


# ---------------- notifications (any signed-in user, own only) ----------------
@router.get("/notifications")
def my_notifications(user: User = Depends(any_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Notification).where(Notification.user_id == user.id)
                      .order_by(Notification.id.desc()).limit(30)).all()
    unread = db.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id == user.id, Notification.is_read.is_(False)))
    return {"unread": unread, "items": [{"id": n.id, "kind": n.kind, "title": n.title, "body": n.body,
                                         "link": n.link, "is_read": n.is_read, "created_at": n.created_at}
                                        for n in rows]}


@router.post("/notifications/read-all")
def read_all(user: User = Depends(any_user), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(Notification.user_id == user.id).values(is_read=True))
    db.commit()
    return {"message": "ok"}
