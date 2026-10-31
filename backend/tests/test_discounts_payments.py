from datetime import date
from decimal import Decimal

from app.core import clock
from tests.conftest import active_sub, register


def disc(client, admin, **kw):
    body = {"name": "D", "discount_type": "percentage", "value": "10", "scope": "subscription", **kw}
    r = client.post("/api/discounts", json=body, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


def bill(client, staff, sub_id):
    r = client.post(f"/api/subscriptions/{sub_id}/invoice-now", headers=staff)
    assert r.status_code == 200, r.text
    return r.json()


def test_percentage_discount_on_whole_subscription(client, admin, staff, catalog):
    disc(client, admin, name="10% off")
    _, cid = register(client, "d1@c.in")
    inv = bill(client, staff, active_sub(client, staff, cid, catalog)["id"])
    # gross 8200, -10% = 820 discount, taxable 7380, GST 18% = 1328.40, total 8708.40
    assert Decimal(inv["discount_amount"]) == Decimal("820.00")
    assert Decimal(inv["tax_amount"]) == Decimal("1328.40")
    assert Decimal(inv["total"]) == Decimal("8708.40")
    assert inv["discounts"][0]["name"] == "10% off"


def test_fixed_discount_on_specific_product(client, admin, staff, catalog):
    disc(client, admin, name="Storage 150 off", discount_type="fixed", value="150", scope="products",
         product_ids=[catalog["addon"]["id"]])
    _, cid = register(client, "d2@c.in")
    inv = bill(client, staff, active_sub(client, staff, cid, catalog)["id"])
    addon_line = next(l for l in inv["lines"] if l["description"] == "Extra Storage")
    crm_line = next(l for l in inv["lines"] if l["description"].startswith("Brightloop CRM"))
    assert Decimal(addon_line["discount_amount"]) == Decimal("150.00")
    assert Decimal(crm_line["discount_amount"]) == 0


def test_fixed_discount_never_negative(client, admin, staff, catalog):
    disc(client, admin, name="Huge", discount_type="fixed", value="999999", scope="subscription")
    _, cid = register(client, "d3@c.in")
    inv = bill(client, staff, active_sub(client, staff, cid, catalog)["id"])
    assert Decimal(inv["total"]) == 0 and Decimal(inv["discount_amount"]) == Decimal("8200.00")


def test_min_purchase_and_min_quantity(client, admin, staff, catalog):
    disc(client, admin, name="Big spender", min_purchase="10000")  # gross is 8200 -> not eligible
    disc(client, admin, name="Seats 5+", min_quantity=7, scope="products", product_ids=[catalog["crm"]["id"]])
    _, cid = register(client, "d4@c.in")
    inv = bill(client, staff, active_sub(client, staff, cid, catalog)["id"])
    assert inv["discounts"] == []


def test_discount_date_window(client, admin, staff, catalog):
    disc(client, admin, name="Future", start_date="2026-02-01")
    disc(client, admin, name="Past", end_date="2026-01-01")
    _, cid = register(client, "d5@c.in")
    sid = active_sub(client, staff, cid, catalog)["id"]
    assert bill(client, staff, sid)["discounts"] == []           # Jan 15 period
    assert len(bill(client, staff, sid)["discounts"]) == 1        # Feb 15 period: "Future" now live


def test_usage_limit_and_cancel_releases(client, admin, staff, catalog):
    d = disc(client, admin, name="First 2", max_usage=2)
    subs = []
    for i in range(3):
        _, cid = register(client, f"u{i}@c.in")
        subs.append(active_sub(client, staff, cid, catalog)["id"])
    i1, i2, i3 = (bill(client, staff, s) for s in subs)
    assert [len(i["discounts"]) for i in (i1, i2, i3)] == [1, 1, 0]
    client.post(f"/api/invoices/{i1['id']}/actions/confirm", headers=staff)
    rule = next(r for r in client.get("/api/discounts", headers=admin).json() if r["id"] == d["id"])
    assert (rule["usage_consumed"], rule["usage_reserved"], rule["status"]) == (1, 2, "exhausted")
    client.post(f"/api/invoices/{i2['id']}/actions/cancel", headers=staff, json={})
    rule = next(r for r in client.get("/api/discounts", headers=admin).json() if r["id"] == d["id"])
    assert rule["usage_reserved"] == 1  # cancelled invoice released its slot
    assert len(bill(client, staff, subs[2])["discounts"]) == 1


def test_discount_limited_to_subscription(client, admin, staff, catalog):
    _, c1 = register(client, "s1@c.in")
    _, c2 = register(client, "s2@c.in")
    s1 = active_sub(client, staff, c1, catalog)["id"]
    s2 = active_sub(client, staff, c2, catalog)["id"]
    disc(client, admin, name="Only s1", subscription_ids=[s1])
    assert len(bill(client, staff, s1)["discounts"]) == 1
    assert bill(client, staff, s2)["discounts"] == []


def test_discount_validation(client, admin):
    bad = {"name": "X", "discount_type": "percentage", "value": "150", "scope": "subscription"}
    assert client.post("/api/discounts", json=bad, headers=admin).status_code == 422
    bad = {"name": "Y", "discount_type": "fixed", "value": "10", "scope": "products"}
    assert client.post("/api/discounts", json=bad, headers=admin).status_code == 422


# ---------------- payments ----------------
def confirmed_invoice(client, staff, catalog, email):
    _, cid = register(client, email)
    inv = bill(client, staff, active_sub(client, staff, cid, catalog)["id"])
    return client.post(f"/api/invoices/{inv['id']}/actions/confirm", headers=staff).json()


def pay(client, hdr, inv, amount, **kw):
    body = {"invoice_id": inv["id"], "method": "upi", "amount": str(amount), "payment_date": "2026-01-15", **kw}
    return client.post("/api/payments", json=body, headers=hdr)


def test_partial_then_full_payment(client, staff, catalog):
    inv = confirmed_invoice(client, staff, catalog, "p1@c.in")
    assert Decimal(inv["total"]) == Decimal("9676.00")
    r = pay(client, staff, inv, "5000", note="first instalment")
    assert r.status_code == 201 and r.json()["reference"].startswith("PAY-")
    inv2 = client.get(f"/api/invoices/{inv['id']}", headers=staff).json()
    assert inv2["state"] == "confirmed" and Decimal(inv2["amount_due"]) == Decimal("4676.00")
    pay(client, staff, inv, "4676.00", method="bank_transfer")
    inv3 = client.get(f"/api/invoices/{inv['id']}", headers=staff).json()
    assert inv3["state"] == "paid" and Decimal(inv3["amount_due"]) == 0 and len(inv3["payments"]) == 2


def test_overpayment_rejected(client, staff, catalog):
    inv = confirmed_invoice(client, staff, catalog, "p2@c.in")
    r = pay(client, staff, inv, "9676.01")
    assert r.status_code == 400 and "outstanding" in r.json()["detail"]


def test_payment_validation(client, staff, catalog):
    inv = confirmed_invoice(client, staff, catalog, "p3@c.in")
    assert pay(client, staff, inv, "0").status_code == 422
    assert pay(client, staff, inv, "-5").status_code == 422
    assert pay(client, staff, inv, "10", payment_date="2026-12-31").status_code == 400  # future
    assert pay(client, staff, inv, "10", customer_id=inv["customer_id"] + 99).status_code == 400
    assert pay(client, staff, inv, "10", reference="UTR-123").status_code == 201
    assert pay(client, staff, inv, "10", reference="UTR-123").status_code == 409  # duplicate ref


def test_cannot_pay_draft_or_cancelled(client, staff, catalog):
    _, cid = register(client, "p4@c.in")
    inv = bill(client, staff, active_sub(client, staff, cid, catalog)["id"])
    assert pay(client, staff, inv, "10").status_code == 400
    client.post(f"/api/invoices/{inv['id']}/actions/cancel", headers=staff, json={})
    assert pay(client, staff, inv, "10").status_code == 400


def test_void_payment_reopens_invoice(client, admin, staff, catalog):
    inv = confirmed_invoice(client, staff, catalog, "p5@c.in")
    p = pay(client, staff, inv, inv["total"]).json()
    assert client.get(f"/api/invoices/{inv['id']}", headers=staff).json()["state"] == "paid"
    assert client.post(f"/api/payments/{p['id']}/void", json={"reason": "bounced"}, headers=staff).status_code == 403
    client.post(f"/api/payments/{p['id']}/void", json={"reason": "cheque bounced"}, headers=admin)
    inv2 = client.get(f"/api/invoices/{inv['id']}", headers=staff).json()
    assert inv2["state"] == "confirmed" and Decimal(inv2["amount_due"]) == Decimal(inv["total"])


def test_cannot_cancel_invoice_with_payment(client, staff, catalog):
    inv = confirmed_invoice(client, staff, catalog, "p6@c.in")
    pay(client, staff, inv, "100")
    assert client.post(f"/api/invoices/{inv['id']}/actions/cancel", headers=staff, json={}).status_code == 400


def test_overdue_detection(client, staff, catalog):
    inv = confirmed_invoice(client, staff, catalog, "od@c.in")
    assert inv["is_overdue"] is False  # due 2026-01-30
    clock.set_today(date(2026, 2, 5))
    rows = client.get("/api/invoices?overdue=true", headers=staff).json()["items"]
    assert [r["id"] for r in rows] == [inv["id"]] and rows[0]["is_overdue"]


def test_send_invoice_is_honest_without_smtp(client, staff, catalog):
    inv = confirmed_invoice(client, staff, catalog, "snd@c.in")
    r = client.post(f"/api/invoices/{inv['id']}/send", headers=staff).json()
    assert r["detail"]["email_status"] == "not_sent" and "NOT sent" in r["message"]
    assert client.get(f"/api/invoices/{inv['id']}", headers=staff).json()["sent_at"] is None


def test_invoice_pdf(client, staff, catalog):
    inv = confirmed_invoice(client, staff, catalog, "pdf@c.in")
    r = client.get(f"/api/invoices/{inv['id']}/pdf", headers=staff)
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
