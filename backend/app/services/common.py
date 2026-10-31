import json
import logging
import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AppSetting, AuditLog, EmailOutbox, Notification

log = logging.getLogger("subsy")


def audit(db: Session, user_id: int | None, action: str, entity: str, entity_id: int | None, **detail) -> None:
    db.add(AuditLog(user_id=user_id, action=action, entity=entity, entity_id=entity_id,
                    detail=json.dumps(detail, default=str) if detail else None))


def notify(db: Session, user_id: int, kind: str, title: str, body: str | None = None,
           link: str | None = None, dedupe_key: str | None = None) -> None:
    if dedupe_key and db.query(Notification.id).filter_by(dedupe_key=dedupe_key).first():
        return
    db.add(Notification(user_id=user_id, kind=kind, title=title, body=body, link=link, dedupe_key=dedupe_key))


def send_email(db: Session, to: str, subject: str, body: str) -> EmailOutbox:
    """Send via SMTP when configured. Otherwise record as not_sent (dev fallback) — never claim delivery."""
    s = get_settings()
    row = EmailOutbox(to_address=to, subject=subject, body=body, status="not_sent")
    if s.smtp_host:
        try:
            msg = EmailMessage()
            msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, subject
            msg.set_content(body)
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
                smtp.starttls()
                if s.smtp_user:
                    smtp.login(s.smtp_user, s.smtp_password)
                smtp.send_message(msg)
            row.status = "sent"
        except Exception as exc:  # noqa: BLE001
            row.status, row.error = "failed", str(exc)[:500]
    else:
        log.info("[email not sent — SMTP not configured] to=%s subject=%s\n%s", to, subject, body)
    db.add(row)
    return row


SETTING_DEFAULTS = {"auto_confirm_invoices": "false", "company_name": "Brightloop Software", "currency": "INR"}


def get_setting(db: Session, key: str) -> str:
    row = db.get(AppSetting, key)
    return row.value if row else SETTING_DEFAULTS.get(key, "")


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(AppSetting, key)
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))


def make_number(prefix: str, id_: int) -> str:
    return f"{prefix}-{id_:06d}"
