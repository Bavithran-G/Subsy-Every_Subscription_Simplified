import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.automation.jobs import run_daily
from app.core.clock import BUSINESS_TZ
from app.core.config import get_settings
from app.core.db import SessionLocal

log = logging.getLogger("subsy.scheduler")
_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> None:
    global _scheduler
    s = get_settings()
    if not s.scheduler_enabled or _scheduler:
        return
    _scheduler = BackgroundScheduler(timezone=BUSINESS_TZ)
    _scheduler.add_job(lambda: run_daily(SessionLocal), CronTrigger(hour=s.billing_cron_hour, minute=0, timezone=BUSINESS_TZ),
                       id="daily", max_instances=1, coalesce=True, misfire_grace_time=6 * 3600)
    _scheduler.start()
    log.info("Scheduler started — daily automation at %02d:00 Asia/Kolkata", s.billing_cron_hour)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
