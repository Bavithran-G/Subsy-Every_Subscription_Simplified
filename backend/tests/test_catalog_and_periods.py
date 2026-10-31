from datetime import date
from decimal import Decimal

import pytest

from app.models import BillingPeriod
from app.services.periods import period_bounds, shift


def test_variant_price_adjustment(client, admin, catalog):
    plan = catalog["plan"]
    # CRM 1000 + Odoo brand 560
    assert Decimal(plan["lines"][0]["effective_price"]) == Decimal("1560.00")
    assert Decimal(plan["price"]) == Decimal("1560.00")


def test_duplicate_variant_rejected(client, admin):
    r = client.post("/api/products", headers=admin, json={
        "name": "P", "product_type": "software", "sales_price": "10",
        "variants": [{"attribute": "Brand", "value": "Odoo"}, {"attribute": "brand", "value": "odoo"}]})
    assert r.status_code == 422


def test_variant_must_belong_to_product(client, admin, catalog):
    r = client.post("/api/plans", headers=admin, json={
        "name": "Bad", "billing_period": "weekly",
        "lines": [{"product_id": catalog["addon"]["id"], "variant_id": catalog["odoo"]["id"]}]})
    assert r.status_code == 422


def test_plan_invalid_availability(client, admin):
    r = client.post("/api/plans", headers=admin, json={
        "name": "Bad dates", "billing_period": "daily", "start_date": "2026-05-01", "end_date": "2026-04-01"})
    assert r.status_code == 422


def test_plan_invalid_frequency(client, admin):
    r = client.post("/api/plans", headers=admin, json={"name": "Q", "billing_period": "quarterly"})
    assert r.status_code == 422


def test_archived_product_variants_kept(client, admin, catalog):
    crm = catalog["crm"]
    body = {k: crm[k] for k in ("name", "product_type", "sales_price", "cost_price", "notes", "tax_id")}
    body["is_active"] = False
    body["variants"] = [{"id": crm["variants"][0]["id"], "attribute": "Brand", "value": "Odoo", "price_extra": "600"}]
    p = client.put(f"/api/products/{crm['id']}", json=body, headers=admin).json()
    assert p["is_active"] is False
    by_val = {v["value"]: v for v in p["variants"]}
    assert Decimal(by_val["Odoo"]["price_extra"]) == 600 and by_val["Standard"]["is_active"] is False


@pytest.mark.parametrize("period,anchor,idx,expected_start,expected_end", [
    ("daily", date(2026, 3, 1), 3, date(2026, 3, 4), date(2026, 3, 4)),
    ("weekly", date(2026, 3, 1), 2, date(2026, 3, 15), date(2026, 3, 21)),
    ("monthly", date(2026, 1, 31), 1, date(2026, 2, 28), date(2026, 3, 30)),   # month-end clamp
    ("monthly", date(2026, 1, 31), 2, date(2026, 3, 31), date(2026, 4, 29)),   # no drift back from 28th
    ("monthly", date(2027, 12, 31), 2, date(2028, 2, 29), date(2028, 3, 30)),  # leap February
    ("yearly", date(2024, 2, 29), 1, date(2025, 2, 28), date(2026, 2, 27)),    # leap-day anchor
    ("yearly", date(2024, 2, 29), 4, date(2028, 2, 29), date(2029, 2, 27)),
])
def test_period_bounds(period, anchor, idx, expected_start, expected_end):
    assert period_bounds(anchor, BillingPeriod(period), 1, idx) == (expected_start, expected_end)


def test_interval_two_months():
    assert period_bounds(date(2026, 1, 10), BillingPeriod.monthly, 2, 1) == (date(2026, 3, 10), date(2026, 5, 9))


def test_shift_month_lengths():
    assert [shift(date(2026, 1, 30), BillingPeriod.monthly, i).day for i in range(4)] == [30, 28, 30, 30]
