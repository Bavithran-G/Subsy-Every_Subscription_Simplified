"""Business clock. Billing runs on the business calendar day in the company time zone (Asia/Kolkata).
Tests can freeze the date with `set_today()`."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

BUSINESS_TZ = ZoneInfo("Asia/Kolkata")
_frozen: date | None = None


def today() -> date:
    return _frozen or datetime.now(BUSINESS_TZ).date()


def set_today(value: date | None) -> None:
    global _frozen
    _frozen = value
