"""The 20-step acceptance journey from the build brief (section 29), run in order through the HTTP API
against PostgreSQL with persistent, connected records."""
from datetime import date
from decimal import Decimal

from app.core import clock
from tests.conftest import PW, make_user, login
from app.models import Role


def test_acceptance_journey(client):
    make_user("admin@brightloop.io", Role.admin, "Admin")
    admin = login(client, "admin@brightloop.io")
    client.post("/api/users/staff", headers=admin, json={"full_name": "Rep", "email": "rep@brightloop.io", "password": PW})
    staff = login(client, "rep@brightloop.io")

    # 1-2. customer registers with a valid unique email + password, then logs in
    r = client.post("/api/auth/register", json={"full_name": "Shop Owner", "email": "owner@shop.in", "password": PW, "company": "Shop"})
    assert r.status_code == 201
    cust_id = r.json()["user"]["customer_id"]
    assert client.post("/api/auth/register", json={"full_name": "Dup", "email": "owner@shop.in", "password": PW}).status_code == 409
    cust = login(client, "owner@shop.in")

    # 3-4. admin creates a product with a configurable variant price adjustment
    tax = client.post("/api/taxes", headers=admin, json={"name": "GST 18%", "tax_type": "percentage", "rate": "18"}).json()
    prod = client.post("/api/products", headers=admin, json={
        "name": "Suite", "product_type": "software", "sales_price": "1000", "cost_price": "200", "tax_id": tax["id"],
        "variants": [{"attribute": "Brand", "value": "Odoo", "price_extra": "560"}]}).json()
    odoo = prod["variants"][0]["id"]

    # 5. admin creates a plan
    plan = client.post("/api/plans", headers=admin, json={
        "name": "Suite Monthly", "billing_period": "monthly", "min_quantity": 2, "term_periods": 12, "pausable": True,
        "lines": [{"product_id": prod["id"], "variant_id": odoo, "quantity": 2}]}).json()
    assert Decimal(plan["price"]) == Decimal("3120.00")

    # discount rule (admin only) that should land on the invoice automatically
    client.post("/api/discounts", headers=admin, json={"name": "Launch 10%", "discount_type": "percentage", "value": "10",
                                                       "scope": "subscription", "max_usage": 5})

    # 6-7. staff creates a quotation from a template; it is tied to the right customer and plan
    tmpl = client.post("/api/templates", headers=staff, json={
        "name": "Suite offer", "plan_id": plan["id"], "validity_days": 14, "payment_terms_days": 10,
        "lines": [{"product_id": prod["id"], "variant_id": odoo, "quantity": 4}]}).json()
    q = client.post("/api/subscriptions", headers=staff, json={"customer_id": cust_id, "plan_id": plan["id"],
                                                               "template_id": tmpl["id"]}).json()
    assert (q["customer_id"], q["plan_id"], q["state"]) == (cust_id, plan["id"], "draft")

    # 8. confirmed   9-10. subscription lines/dates correct; lifecycle Draft -> Quotation -> Confirmed -> Active
    for a in ("send", "confirm"):
        q = client.post(f"/api/subscriptions/{q['id']}/actions/{a}", headers=staff, json={}).json()
    sub = client.post(f"/api/subscriptions/{q['id']}/actions/activate", headers=staff, json={"start_date": "2026-01-15"}).json()
    assert sub["state"] == "active" and sub["lines"][0]["quantity"] == 4
    assert Decimal(sub["lines"][0]["unit_price"]) == Decimal("1560.00")
    assert (sub["start_date"], sub["end_date"]) == ("2026-01-15", "2027-01-14")
    assert [h["to_state"] for h in sub["history"]] == ["draft", "quotation", "confirmed", "active"]

    # 11-12. billing engine finds the subscription and generates the invoice with lines, tax and discount
    run = client.post("/api/billing/run", headers=staff).json()
    assert run["detail"]["created"] == 1
    inv_id = client.get(f"/api/invoices?subscription_id={sub['id']}", headers=staff).json()["items"][0]["id"]
    inv = client.get(f"/api/invoices/{inv_id}", headers=staff).json()
    # 4 x 1560 = 6240; -10% = 624 -> 5616; GST 18% = 1010.88; total 6626.88
    assert Decimal(inv["untaxed_amount"]) == Decimal("6240.00")
    assert Decimal(inv["discount_amount"]) == Decimal("624.00")
    assert Decimal(inv["tax_amount"]) == Decimal("1010.88")
    assert Decimal(inv["total"]) == Decimal("6626.88")

    # 13. reprocessing the same billing event does not create another invoice
    assert client.post("/api/billing/run", headers=staff).json()["detail"]["created"] == 0
    assert client.get(f"/api/invoices?subscription_id={sub['id']}", headers=staff).json()["total"] == 1

    # 14. customer can view their own (confirmed) invoice
    client.post(f"/api/invoices/{inv_id}/actions/confirm", headers=staff)
    assert client.get(f"/api/invoices/{inv_id}", headers=cust).status_code == 200
    assert [i["id"] for i in client.get("/api/portal/invoices", headers=cust).json()["items"]] == [inv_id]

    # 15-17. staff records payments; balance recalculated; Paid only when fully settled
    clock.set_today(date(2026, 1, 20))
    client.post("/api/payments", headers=staff, json={"invoice_id": inv_id, "method": "upi", "amount": "3000", "payment_date": "2026-01-18"})
    inv = client.get(f"/api/invoices/{inv_id}", headers=staff).json()
    assert inv["state"] == "confirmed" and Decimal(inv["amount_due"]) == Decimal("3626.88")
    client.post("/api/payments", headers=staff, json={"invoice_id": inv_id, "method": "bank_transfer", "amount": "3626.88", "payment_date": "2026-01-20"})
    inv = client.get(f"/api/invoices/{inv_id}", headers=staff).json()
    assert inv["state"] == "paid" and Decimal(inv["amount_due"]) == 0

    # 18-19. dashboard and reports reconcile with the invoices and payments
    k = client.get("/api/reports/dashboard", headers=staff).json()["kpis"]
    assert k["active_subscriptions"] == 1 and k["paid_invoices"] == 1
    assert Decimal(str(k["revenue_invoiced"])) == Decimal("6626.88") == Decimal(str(k["revenue_collected"]))
    assert k["outstanding_amount"] == 0
    pay = client.get("/api/reports/payments", headers=staff).json()
    assert pay["summary"]["payments"] == 2 and Decimal(str(pay["summary"]["amount"])) == Decimal("6626.88")

    # 20. unauthorised users cannot reach restricted operations or other customers' records
    client.post("/api/auth/register", json={"full_name": "Other", "email": "other@shop.in", "password": PW})
    other = login(client, "other@shop.in")
    assert client.get(f"/api/invoices/{inv_id}", headers=other).status_code == 404
    assert client.get(f"/api/portal/subscriptions/{sub['id']}", headers=other).status_code == 404
    assert client.get("/api/invoices", headers=cust).status_code == 403
    assert client.post("/api/discounts", headers=staff, json={"name": "x", "discount_type": "fixed", "value": "1",
                                                              "scope": "subscription"}).status_code == 403
    assert client.post("/api/users/staff", headers=staff, json={"full_name": "x y", "email": "x@y.io", "password": PW}).status_code == 403
