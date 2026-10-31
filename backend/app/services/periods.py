"""Billing-period arithmetic.

Periods are always computed from the subscription's *anchor* date, never chained from the previous
period, so month-end dates don't drift: a subscription anchored on Jan 31 bills Jan 31, Feb 28/29,
Mar 31, Apr 30, ... and a yearly subscription anchored on Feb 29 bills Feb 28 in non-leap years and
Feb 29 again in leap years.
"""
import calendar
from datetime import date, timedelta

from app.models.base import BillingPeriod


def add_months(anchor: date, months: int) -> date:
    total = anchor.month - 1 + months
    year = anchor.year + total // 12
    month = total % 12 + 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def shift(anchor: date, period: BillingPeriod, steps: int) -> date:
    period = BillingPeriod(period)
    if period == BillingPeriod.daily:
        return anchor + timedelta(days=steps)
    if period == BillingPeriod.weekly:
        return anchor + timedelta(weeks=steps)
    if period == BillingPeriod.monthly:
        return add_months(anchor, steps)
    if period == BillingPeriod.yearly:
        return add_months(anchor, 12 * steps)
    raise ValueError(f"unknown billing period {period}")


def period_bounds(anchor: date, period: BillingPeriod, interval: int, index: int) -> tuple[date, date]:
    """Return (start, end) inclusive of billing period number `index` (0-based)."""
    start = shift(anchor, period, index * interval)
    end = shift(anchor, period, (index + 1) * interval) - timedelta(days=1)
    return start, end


def monthly_factor(period: BillingPeriod, interval: int) -> float:
    """How many of this period fit in one month — used to normalise recurring revenue to MRR."""
    per_month = {
        BillingPeriod.daily: 30.4375,
        BillingPeriod.weekly: 4.348125,
        BillingPeriod.monthly: 1.0,
        BillingPeriod.yearly: 1 / 12,
    }[BillingPeriod(period)]
    return per_month / interval
