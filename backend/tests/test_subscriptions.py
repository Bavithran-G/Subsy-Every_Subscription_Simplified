from datetime import date
from decimal import Decimal

from app.core import clock
from tests.conftest import active_sub, register


def new_quote(client, hdr, cid, catalog, **extra):
    r = client.post("/api/subscriptions", headers=hdr, json={
        "customer_id": cid, "plan_id": catalog["plan"]["id"], "template_id": catalog["template"]["id"], **extra})
    assert r.status_code == 201, r.text
    return r.json()


def act(client, hdr, sid, action, **body):
    return client.post(f"/api/subscriptions/{sid}/actions/{action}", headers=hdr, json=body)


def test_quotation_from_template(client, staff, catalog):
    _, cid = register(client, "q@c.in")
    q = new_quote(client, staff, cid, catalog)
    assert q["state"] == "draft" and q["number"].startswith("SUB-")
    assert q["customer_id"] == cid and q["plan_id"] == catalog["plan"]["id"]
    assert q["valid_until"] == "2026-02-14" and q["payment_terms_days"] == 15
    # 5 x 1560 + 2 x 200 = 8200; GST 18% = 1476
    assert Decimal(q["untaxed"]) == Decimal("8200.00") and Decimal(q["tax"]) == Decimal("1476.00")
    assert [l["quantity"] for l in q["lines"]] == [5, 2]


def test_full_lifecycle_and_history(client, staff, catalog):
    _, cid = register(client, "l@c.in")
    q = new_quote(client, staff, cid, catalog)
    sid = q["id"]
    assert act(client, staff, sid, "send").json()["state"] == "quotation"
    assert act(client, staff, sid, "confirm").json()["state"] == "confirmed"
    s = act(client, staff, sid, "activate", start_date="2026-01-15").json()
    assert s["state"] == "active" and s["start_date"] == "2026-01-15"
    assert s["end_date"] == "2027-01-14"  # 12 monthly periods
    assert s["next_invoice_date"] == "2026-01-15"
    s = act(client, staff, sid, "close", reason="Customer request").json()
    assert s["state"] == "closed"
    assert [h["to_state"] for h in s["history"]] == ["draft", "quotation", "confirmed", "active", "closed"]
    assert s["history"][-1]["reason"] == "Customer request" and s["history"][-1]["user_name"] == "Sam Staff"


def test_invalid_transitions_rejected(client, staff, catalog):
    _, cid = register(client, "i@c.in")
    sid = new_quote(client, staff, cid, catalog)["id"]
    assert act(client, staff, sid, "activate").status_code == 400   # draft -> active not allowed
    assert act(client, staff, sid, "pause").status_code in (400, 403)
    act(client, staff, sid, "confirm")
    assert act(client, staff, sid, "confirm").status_code == 400
    assert act(client, staff, sid, "cancel").status_code == 400     # confirmed can't be cancelled
    assert act(client, staff, sid, "teleport").status_code == 404


def test_expired_quotation_cannot_confirm_until_extended(client, staff, catalog):
    _, cid = register(client, "e@c.in")
    sid = new_quote(client, staff, cid, catalog)["id"]
    clock.set_today(date(2026, 3, 1))
    r = act(client, staff, sid, "confirm")
    assert r.status_code == 400 and "expired" in r.json()["detail"]
    assert act(client, staff, sid, "extend", days=10).json()["valid_until"] == "2026-03-11"
    assert act(client, staff, sid, "confirm").json()["state"] == "confirmed"


def test_confirmed_quotation_not_editable(client, staff, catalog):
    _, cid = register(client, "ed@c.in")
    sid = new_quote(client, staff, cid, catalog)["id"]
    r = client.put(f"/api/subscriptions/{sid}", headers=staff, json={"lines": [
        {"product_id": catalog["crm"]["id"], "quantity": 3}]})
    assert r.status_code == 200 and len(r.json()["lines"]) == 1
    act(client, staff, sid, "confirm")
    r = client.put(f"/api/subscriptions/{sid}", headers=staff, json={"notes": "x"})
    assert r.status_code == 400


def test_min_quantity_enforced(client, admin, staff, catalog):
    plan = catalog["plan"]
    body = {k: plan[k] for k in ("name", "billing_period", "billing_interval", "term_periods", "pausable",
                                 "renewable", "closable", "auto_close")}
    body["min_quantity"] = 10
    body["lines"] = [{"product_id": l["product_id"], "variant_id": l["variant_id"], "quantity": 1}
                     for l in plan["lines"]]
    assert client.put(f"/api/plans/{plan['id']}", json=body, headers=admin).status_code == 200
    _, cid = register(client, "m@c.in")
    sid = new_quote(client, staff, cid, catalog)["id"]
    r = act(client, staff, sid, "confirm")
    assert r.status_code == 400 and "minimum quantity" in r.json()["detail"]


def test_plan_permissions_enforced(client, admin, staff, catalog):
    plan = catalog["plan"]
    body = {k: plan[k] for k in ("name", "billing_period", "billing_interval", "term_periods", "min_quantity",
                                 "auto_close")}
    body.update(pausable=False, renewable=False, closable=False,
                lines=[{"product_id": l["product_id"], "variant_id": l["variant_id"], "quantity": 1}
                       for l in plan["lines"]])
    client.put(f"/api/plans/{plan['id']}", json=body, headers=admin)
    _, cid = register(client, "p@c.in")
    s = active_sub(client, staff, cid, catalog)
    assert s["allowed_actions"] == ["invoice"]
    assert act(client, staff, s["id"], "pause").status_code == 403
    assert act(client, staff, s["id"], "renew").status_code == 403
    assert act(client, staff, s["id"], "close").status_code == 403   # early closure not permitted


def test_plan_availability_window(client, admin, staff, catalog):
    plan = catalog["plan"]
    body = {k: plan[k] for k in ("name", "billing_period", "billing_interval", "term_periods", "min_quantity",
                                 "auto_close", "pausable", "renewable", "closable")}
    body.update(end_date="2026-01-10", lines=[])
    client.put(f"/api/plans/{plan['id']}", json=body, headers=admin)
    _, cid = register(client, "av@c.in")
    sid = new_quote(client, staff, cid, catalog)["id"]
    r = act(client, staff, sid, "confirm")
    assert r.status_code == 400 and "no longer available" in r.json()["detail"]


def test_pause_resume_skips_paused_periods(client, staff, catalog):
    _, cid = register(client, "pr@c.in")
    s = active_sub(client, staff, cid, catalog, start="2026-01-15")
    sid = s["id"]
    client.post("/api/billing/run", headers=staff)  # bills Jan 15 period
    clock.set_today(date(2026, 1, 20))
    assert act(client, staff, sid, "pause", reason="Seasonal").json()["state"] == "paused"
    clock.set_today(date(2026, 4, 1))
    r = client.post("/api/billing/run", headers=staff).json()
    assert r["detail"]["created"] == 0  # nothing billed while paused
    s = act(client, staff, sid, "resume").json()
    assert s["state"] == "active"
    # Feb 15 and Mar 15 started while paused -> skipped; next is Apr 15
    assert s["next_invoice_date"] == "2026-04-15"
    assert "2 billing period(s) skipped" in s["history"][-1]["reason"]


def test_renewal_extends_once_per_term(client, staff, catalog):
    _, cid = register(client, "rn@c.in")
    s = active_sub(client, staff, cid, catalog)
    assert s["end_date"] == "2027-01-14"
    s2 = act(client, staff, s["id"], "renew").json()
    assert s2["end_date"] == "2028-01-14" and len(s2["renewals"]) == 1
    s3 = act(client, staff, s["id"], "renew").json()  # renewing the *new* term is a different term
    assert s3["end_date"] == "2029-01-14" and len(s3["renewals"]) == 2


def test_auto_close_after_expiry(client, admin, staff, catalog):
    from app.automation import jobs
    from tests.conftest import TestSession
    plan = catalog["plan"]
    body = {k: plan[k] for k in ("name", "billing_period", "billing_interval", "min_quantity", "pausable",
                                 "renewable", "closable")}
    body.update(auto_close=True, term_periods=2,
                lines=[{"product_id": l["product_id"], "variant_id": l["variant_id"], "quantity": 1}
                       for l in plan["lines"]])
    client.put(f"/api/plans/{plan['id']}", json=body, headers=admin)
    _, cid = register(client, "ac@c.in")
    s = active_sub(client, staff, cid, catalog, start="2026-01-15")
    assert s["end_date"] == "2026-03-14"
    clock.set_today(date(2026, 3, 20))
    runs = jobs.run_daily(TestSession, trigger="manual")
    assert runs[0].created == 2  # Jan + Feb periods billed first
    s = client.get(f"/api/subscriptions/{s['id']}", headers=staff).json()
    assert s["state"] == "closed" and s["history"][-1]["user_name"] == "System"
