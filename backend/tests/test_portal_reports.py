from decimal import Decimal

from tests.conftest import active_sub, register


def test_customer_data_isolation(client, staff, catalog):
    alice, a_id = register(client, "alice@c.in", "Alice")
    bob, b_id = register(client, "bob@c.in", "Bob")
    sa = active_sub(client, staff, a_id, catalog)
    sb = active_sub(client, staff, b_id, catalog)
    ia = client.post(f"/api/subscriptions/{sa['id']}/invoice-now", headers=staff).json()
    ib = client.post(f"/api/subscriptions/{sb['id']}/invoice-now", headers=staff).json()
    for i in (ia, ib):
        client.post(f"/api/invoices/{i['id']}/actions/confirm", headers=staff)

    assert [s["id"] for s in client.get("/api/portal/subscriptions", headers=alice).json()] == [sa["id"]]
    assert client.get(f"/api/portal/subscriptions/{sb['id']}", headers=alice).status_code == 404
    assert [i["id"] for i in client.get("/api/portal/invoices", headers=alice).json()["items"]] == [ia["id"]]
    assert client.get(f"/api/invoices/{ib['id']}", headers=alice).status_code == 404
    assert client.get(f"/api/invoices/{ib['id']}/pdf", headers=alice).status_code == 404
    assert client.get(f"/api/invoices/{ia['id']}", headers=alice).status_code == 200
    assert client.post(f"/api/portal/subscriptions/{sb['id']}/actions/pause", headers=alice).status_code == 404
    # internal-only actions are not exposed in the portal
    assert client.post(f"/api/portal/subscriptions/{sa['id']}/actions/close", headers=alice).status_code == 403
    assert client.post(f"/api/subscriptions/{sa['id']}/actions/close", headers=alice).status_code == 403
    # staff cannot use the customer portal
    assert client.get("/api/portal/subscriptions", headers=staff).status_code == 403


def test_customer_sees_no_drafts(client, staff, catalog):
    alice, a_id = register(client, "nd@c.in")
    s = active_sub(client, staff, a_id, catalog)
    inv = client.post(f"/api/subscriptions/{s['id']}/invoice-now", headers=staff).json()
    assert client.get("/api/portal/invoices", headers=alice).json()["total"] == 0
    assert client.get(f"/api/invoices/{inv['id']}/pdf", headers=alice).status_code == 404
    q = client.post("/api/subscriptions", headers=staff, json={
        "customer_id": a_id, "plan_id": catalog["plan"]["id"]}).json()
    assert q["id"] not in [x["id"] for x in client.get("/api/portal/subscriptions", headers=alice).json()]


def test_customer_self_service_pause_resume_renew(client, staff, catalog):
    alice, a_id = register(client, "ss@c.in")
    s = active_sub(client, staff, a_id, catalog)
    r = client.post(f"/api/portal/subscriptions/{s['id']}/actions/pause", headers=alice)
    assert r.status_code == 200 and r.json()["state"] == "paused"
    assert r.json()["billing_events"] == []  # internal billing data not exposed to customers
    assert client.post(f"/api/portal/subscriptions/{s['id']}/actions/resume", headers=alice).json()["state"] == "active"
    r = client.post(f"/api/portal/subscriptions/{s['id']}/actions/renew", headers=alice).json()
    assert r["end_date"] == "2028-01-14"


def test_dashboard_reconciles_with_records(client, staff, catalog):
    totals = []
    for i in range(3):
        _, cid = register(client, f"r{i}@c.in")
        s = active_sub(client, staff, cid, catalog)
        inv = client.post(f"/api/subscriptions/{s['id']}/invoice-now", headers=staff).json()
        inv = client.post(f"/api/invoices/{inv['id']}/actions/confirm", headers=staff).json()
        totals.append(Decimal(inv["total"]))
    inv_rows = client.get("/api/invoices", headers=staff).json()["items"]
    client.post("/api/payments", headers=staff, json={"invoice_id": inv_rows[0]["id"], "method": "card",
                                                      "amount": str(inv_rows[0]["total"]), "payment_date": "2026-01-15"})
    client.post("/api/payments", headers=staff, json={"invoice_id": inv_rows[1]["id"], "method": "cash",
                                                      "amount": "1000", "payment_date": "2026-01-15"})
    d = client.get("/api/reports/dashboard", headers=staff).json()
    k = d["kpis"]
    invoiced = sum(totals)
    collected = Decimal(inv_rows[0]["total"]) + 1000
    assert k["active_subscriptions"] == 3 and k["total_customers"] == 3
    assert Decimal(str(k["revenue_invoiced"])) == invoiced
    assert Decimal(str(k["revenue_collected"])) == collected
    assert Decimal(str(k["outstanding_amount"])) == invoiced - collected  # collected != invoiced
    assert k["paid_invoices"] == 1 and k["outstanding_invoices"] == 2
    jan = next(m for m in d["monthly"] if m["month"] == "2026-01")
    assert Decimal(str(jan["invoiced"])) == invoiced and Decimal(str(jan["collected"])) == collected
    # MRR: 3 active monthly subs x 8200 untaxed
    assert k["mrr"] == 3 * 8200.0
    pay_rep = client.get("/api/reports/payments", headers=staff).json()
    assert {m["method"] for m in pay_rep["by_method"]} == {"card", "cash"}
    assert pay_rep["summary"]["partially_paid_invoices"] == 1
    rev = client.get("/api/reports/revenue", headers=staff).json()
    assert Decimal(str(sum(p["invoiced"] for p in rev["by_plan"]))) == invoiced
    csv = client.get("/api/reports/revenue/csv", headers=staff)
    assert csv.status_code == 200 and csv.text.startswith("month,")


def test_all_reports_respond(client, staff, catalog):
    for name in ("subscriptions", "revenue", "invoices", "payments", "discounts"):
        assert client.get(f"/api/reports/{name}", headers=staff).status_code == 200, name
        assert client.get(f"/api/reports/{name}/csv", headers=staff).status_code == 200, name
