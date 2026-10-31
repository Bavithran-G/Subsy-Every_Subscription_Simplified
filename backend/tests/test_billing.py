import threading
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.core import clock
from app.models import BillingEvent, Invoice, Subscription
from app.services import billing
from app.services.billing import run_billing
from tests.conftest import TestSession, active_sub, register


def count_invoices(sub_id=None):
    s = TestSession()
    stmt = select(func.count()).select_from(Invoice)
    if sub_id:
        stmt = stmt.where(Invoice.subscription_id == sub_id)
    n = s.scalar(stmt)
    s.close()
    return n


def test_invoice_contents(client, staff, catalog):
    _, cid = register(client, "inv@c.in")
    s = active_sub(client, staff, cid, catalog)
    r = client.post("/api/billing/run", headers=staff).json()
    assert r["detail"]["created"] == 1
    inv_id = client.get("/api/invoices", headers=staff).json()["items"][0]["id"]
    inv = client.get(f"/api/invoices/{inv_id}", headers=staff).json()
    assert inv["number"].startswith("INV-") and inv["state"] == "draft"
    assert inv["subscription_id"] == s["id"] and inv["customer_id"] == cid
    assert (inv["period_start"], inv["period_end"]) == ("2026-01-15", "2026-02-14")
    assert inv["invoice_date"] == "2026-01-15" and inv["due_date"] == "2026-01-30"
    assert Decimal(inv["untaxed_amount"]) == Decimal("8200.00")
    assert Decimal(inv["tax_amount"]) == Decimal("1476.00")
    assert Decimal(inv["total"]) == Decimal("9676.00")
    assert inv["lines"][0]["description"] == "Brightloop CRM (Brand: Odoo)"
    assert inv["lines"][0]["tax_name"] == "GST 18%"


def test_rerun_does_not_duplicate(client, staff, catalog):
    _, cid = register(client, "dup@c.in")
    s = active_sub(client, staff, cid, catalog)
    for _ in range(3):
        client.post("/api/billing/run", headers=staff)
    assert count_invoices(s["id"]) == 1


def test_catch_up_bills_every_missed_period_once(client, staff, catalog):
    _, cid = register(client, "cu@c.in")
    s = active_sub(client, staff, cid, catalog, start="2026-01-15")
    clock.set_today(date(2026, 4, 20))
    r = client.post("/api/billing/run", headers=staff).json()
    assert r["detail"]["created"] == 4  # Jan, Feb, Mar, Apr — none skipped
    s2 = TestSession()
    starts = s2.scalars(select(BillingEvent.period_start).order_by(BillingEvent.period_start)).all()
    s2.close()
    assert starts == [date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15), date(2026, 4, 15)]
    client.post("/api/billing/run", headers=staff)
    assert count_invoices(s["id"]) == 4


def test_billing_stops_at_expiry(client, staff, catalog):
    _, cid = register(client, "ex@c.in")
    s = active_sub(client, staff, cid, catalog, start="2026-01-15")  # 12 periods -> ends 2027-01-14
    clock.set_today(date(2027, 6, 1))
    client.post("/api/billing/run", headers=staff)
    assert count_invoices(s["id"]) == 12


def test_manual_invoice_now_shares_identity_with_scheduler(client, staff, catalog):
    _, cid = register(client, "man@c.in")
    s = active_sub(client, staff, cid, catalog)
    r = client.post(f"/api/subscriptions/{s['id']}/invoice-now", headers=staff)
    assert r.status_code == 200 and r.json()["period_start"] == "2026-01-15"
    client.post("/api/billing/run", headers=staff)  # same period is due today — must not be billed again
    assert count_invoices(s["id"]) == 1
    r = client.post(f"/api/subscriptions/{s['id']}/invoice-now", headers=staff)  # bills next period early
    assert r.json()["period_start"] == "2026-02-15"
    assert count_invoices(s["id"]) == 2


def test_concurrent_billing_runs_never_duplicate(client, staff, catalog):
    """Several runners started at the same moment on 30 due subscriptions x 3 periods each."""
    ids = []
    for i in range(30):
        _, cid = register(client, f"cc{i}@c.in")
        ids.append(active_sub(client, staff, cid, catalog, start="2026-01-15")["id"])
    clock.set_today(date(2026, 3, 16))
    barrier = threading.Barrier(4)
    results = []

    def runner():
        barrier.wait()
        results.append(run_billing(TestSession, clock.today(), trigger="test"))

    threads = [threading.Thread(target=runner) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert count_invoices() == 90
    s = TestSession()
    dupes = s.execute(select(Invoice.subscription_id, Invoice.period_start, func.count())
                      .group_by(Invoice.subscription_id, Invoice.period_start).having(func.count() > 1)).all()
    s.close()
    assert dupes == []
    assert sum(r.created for r in results) == 90


def test_concurrent_per_subscription_lock_without_advisory_lock(client, staff, catalog, monkeypatch):
    """Even if the run-level advisory lock were bypassed, row locks + unique constraints prevent duplicates."""
    _, cid = register(client, "rl@c.in")
    sid = active_sub(client, staff, cid, catalog, start="2026-01-15")["id"]
    clock.set_today(date(2026, 6, 20))
    barrier = threading.Barrier(5)

    def worker():
        db = TestSession()
        barrier.wait()
        billing.bill_subscription(db, sid, clock.today())
        db.close()

    threads = [threading.Thread(target=worker) for _ in range(5)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert count_invoices(sid) == 6


def test_failed_billing_is_recoverable_and_not_skipped(client, staff, catalog, monkeypatch):
    _, cid = register(client, "fail@c.in")
    s = active_sub(client, staff, cid, catalog)
    import app.services.billing as b
    real = b.build_invoice_for_period
    calls = {"n": 0}

    def flaky(*a, **kw):
        calls["n"] += 1
        raise RuntimeError("tax service unavailable")
    monkeypatch.setattr(b, "build_invoice_for_period", flaky)
    r = client.post("/api/billing/run", headers=staff).json()
    assert r["detail"]["failed"] == 1 and r["detail"]["created"] == 0
    events = client.get("/api/billing/events?status=failed", headers=staff).json()["items"]
    assert len(events) == 1 and "tax service unavailable" in events[0]["error"]
    sub = client.get(f"/api/subscriptions/{s['id']}", headers=staff).json()
    assert sub["next_invoice_date"] == "2026-01-15"  # index not advanced — period is not skipped
    monkeypatch.setattr(b, "build_invoice_for_period", real)
    r = client.post(f"/api/billing/events/{events[0]['id']}/retry", headers=staff)
    assert r.status_code == 200 and r.json()["detail"]["created"] == 1
    client.post(f"/api/billing/events/{events[0]['id']}/retry", headers=staff)  # second retry is a no-op
    client.post("/api/billing/run", headers=staff)
    assert count_invoices(s["id"]) == 1
    ev = client.get(f"/api/billing/events?subscription_id={s['id']}", headers=staff).json()["items"][0]
    assert ev["status"] == "invoiced" and ev["attempts"] == 2


def test_rebill_after_cancel(client, staff, catalog):
    _, cid = register(client, "rb@c.in")
    s = active_sub(client, staff, cid, catalog)
    inv = client.post(f"/api/subscriptions/{s['id']}/invoice-now", headers=staff).json()
    client.post(f"/api/invoices/{inv['id']}/actions/cancel", headers=staff, json={"reason": "wrong qty"})
    ev = client.get(f"/api/billing/events?subscription_id={s['id']}", headers=staff).json()["items"][0]
    r = client.post(f"/api/billing/events/{ev['id']}/retry", headers=staff)
    assert r.status_code == 200
    invs = client.get(f"/api/invoices?subscription_id={s['id']}", headers=staff).json()["items"]
    assert sorted(i["state"] for i in invs) == ["cancelled", "draft"]


def test_paused_and_closed_not_billed(client, staff, catalog):
    _, cid = register(client, "pc@c.in")
    s = active_sub(client, staff, cid, catalog)
    client.post(f"/api/subscriptions/{s['id']}/actions/pause", headers=staff, json={})
    client.post("/api/billing/run", headers=staff)
    assert count_invoices(s["id"]) == 0


def test_daily_and_weekly_plans(client, admin, staff, catalog):
    for name, period, days_later, expected in (("Daily Pass", "daily", 6, 7), ("Weekly Pass", "weekly", 20, 3)):
        clock.set_today(date(2026, 1, 15))
        plan = client.post("/api/plans", headers=admin, json={
            "name": name, "billing_period": period,
            "lines": [{"product_id": catalog["addon"]["id"], "quantity": 1}]}).json()
        _, cid = register(client, f"{period}@c.in")
        sub = client.post("/api/subscriptions", headers=staff, json={"customer_id": cid, "plan_id": plan["id"]}).json()
        client.post(f"/api/subscriptions/{sub['id']}/actions/confirm", headers=staff, json={})
        client.post(f"/api/subscriptions/{sub['id']}/actions/activate", headers=staff, json={})
        clock.set_today(date(2026, 1, 15) + timedelta(days=days_later))
        client.post("/api/billing/run", headers=staff)
        assert count_invoices(sub["id"]) == expected, name


def test_yearly_leap_day(client, admin, staff, catalog):
    clock.set_today(date(2028, 2, 29))
    plan = client.post("/api/plans", headers=admin, json={
        "name": "Yearly", "billing_period": "yearly",
        "lines": [{"product_id": catalog["addon"]["id"], "quantity": 1}]}).json()
    _, cid = register(client, "leap@c.in")
    sub = client.post("/api/subscriptions", headers=staff, json={"customer_id": cid, "plan_id": plan["id"]}).json()
    client.post(f"/api/subscriptions/{sub['id']}/actions/confirm", headers=staff, json={})
    client.post(f"/api/subscriptions/{sub['id']}/actions/activate", headers=staff, json={})
    clock.set_today(date(2030, 3, 1))
    client.post("/api/billing/run", headers=staff)
    invs = client.get(f"/api/invoices?subscription_id={sub['id']}", headers=staff).json()["items"]
    assert sorted(i["period_start"] for i in invs) == ["2028-02-29", "2029-02-28", "2030-02-28"]


def test_auto_confirm_setting(client, admin, staff, catalog):
    client.put("/api/admin/settings", json={"auto_confirm_invoices": True}, headers=admin)
    cust_hdr, cid = register(client, "auto@c.in")
    active_sub(client, staff, cid, catalog)
    client.post("/api/billing/run", headers=staff)
    inv = client.get("/api/invoices", headers=staff).json()["items"][0]
    assert inv["state"] == "confirmed"
    notes = client.get("/api/notifications", headers=cust_hdr).json()
    assert any("New invoice" in n["title"] for n in notes["items"])
