"""Brightloop Software demo data.

    python -m app.seed            # demo dataset (idempotent — safe to run repeatedly)
    python -m app.seed --bulk 5000  # additionally create N synthetic subscriptions for performance testing

The demo history is not inserted as finished numbers: it is *replayed* through the real services month by
month (quotation -> confirm -> activate -> billing engine -> confirm -> payments, pauses, closures, renewals),
so every dashboard figure is derived from records produced by the same code paths the app uses.
All demo records are flagged is_demo=true.
"""
import argparse
import random
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.automation import jobs
from app.core import clock
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import (
    AppSetting, Customer, DiscountRule, Invoice, InvoiceState, Payment, PaymentMethod, Plan, PlanLine, Product,
    ProductVariant, QuotationTemplate, QuotationTemplateLine, Role, SubState, Subscription, Tax, TaxType, User,
)
from app.services import invoices as invsvc
from app.services import payments as paysvc
from app.services import subscriptions as subsvc
from app.services.billing import bill_subscription
from app.services.periods import add_months

DEMO_PASSWORD = "Subsy@Demo2026"
MARKER = "demo_seeded_v1"


def _user(db, email, name, role):
    u = db.scalars(select(User).where(User.email == email)).first()
    if not u:
        u = User(email=email, full_name=name, role=role, password_hash=hash_password(DEMO_PASSWORD), is_demo=True)
        db.add(u)
        db.flush()
    return u


def seed(today: date | None = None):
    db = SessionLocal()
    if db.get(AppSetting, MARKER):
        print("Demo data already present — nothing to do.")
        db.close()
        return
    real_today = today or clock.today()
    rng = random.Random(2026)

    admin = _user(db, "admin@brightloop.demo", "Anika Rao (Admin)", Role.admin)
    staff = _user(db, "staff@brightloop.demo", "Vikram Menon (Staff)", Role.staff)
    _user(db, "finance@brightloop.demo", "Meera Iyer (Finance)", Role.staff)

    gst18 = Tax(name="GST 18%", tax_type=TaxType.percentage, rate=18, description="Standard GST on software")
    gst5 = Tax(name="GST 5%", tax_type=TaxType.percentage, rate=5, description="Reduced rate — training services")
    db.add_all([gst18, gst5])
    db.flush()

    def product(name, ptype, price, cost, tax, notes, variants=()):
        p = Product(name=name, product_type=ptype, sales_price=price, cost_price=cost, tax_id=tax.id, notes=notes)
        for attr, val, extra in variants:
            p.variants.append(ProductVariant(attribute=attr, value=val, price_extra=extra))
        db.add(p)
        db.flush()
        return p

    crm = product("Brightloop CRM", "software", 1000, 280, gst18, "Sales pipeline and contacts, per seat",
                  [("Brand", "Odoo", 560), ("Brand", "Standard", 0)])
    books = product("Brightloop Books", "software", 1800, 420, gst18, "Accounting and GST filing, per company",
                    [("Edition", "Professional", 0), ("Edition", "Enterprise", 1200)])
    desk = product("Brightloop Helpdesk", "software", 650, 150, gst18, "Ticketing, per agent")
    storage = product("Extra Storage 100 GB", "addon", 200, 40, gst18, "Add-on, switch on/off any time")
    support = product("Priority Support", "addon", 1500, 600, gst18, "4-hour response SLA")
    insights = product("Insights Day Pass", "service", 99, 10, gst18, "Analytics workspace, billed daily")
    training = product("Onboarding Workshop", "service", 2500, 900, gst5, "Weekly live training session")
    v = {(p.name, x.value): x for p in (crm, books) for x in p.variants}

    def plan(name, period, lines, **kw):
        p = Plan(name=name, billing_period=period, **kw)
        for prod, var, qty in lines:
            p.lines.append(PlanLine(product_id=prod.id, variant_id=var.id if var else None, quantity=qty))
        db.add(p)
        db.flush()
        return p

    p_crm_m = plan("CRM Monthly", "monthly", [(crm, v[("Brightloop CRM", "Odoo")], 1)], term_periods=12,
                   pausable=True, description="Month-to-month CRM, 12-month term, can pause")
    p_crm_y = plan("CRM Annual", "yearly", [(crm, v[("Brightloop CRM", "Standard")], 1)], term_periods=1,
                   closable=False, description="Annual contract — no early closure")
    p_books = plan("Books Monthly", "monthly", [(books, v[("Brightloop Books", "Professional")], 1)],
                   term_periods=12, pausable=True)
    p_ent = plan("Enterprise Suite Annual", "yearly", [(crm, v[("Brightloop CRM", "Odoo")], 10),
                                                       (desk, None, 10), (support, None, 1)],
                 min_quantity=1, term_periods=1, closable=False, description="Large-company yearly bundle")
    p_desk_w = plan("Helpdesk Weekly", "weekly", [(desk, None, 2)], pausable=True)
    p_daily = plan("Insights Daily Pass", "daily", [(insights, None, 1)], term_periods=30, auto_close=True,
                   renewable=False, description="30-day pass, closes automatically")
    p_train = plan("Onboarding Weekly", "weekly", [(training, None, 1)], term_periods=4, auto_close=True,
                   renewable=False)
    plan("Festive Offer Plan", "monthly", [(crm, v[("Brightloop CRM", "Standard")], 1)],
         start_date=date(2025, 10, 1), end_date=date(2025, 11, 30), is_active=False,
         description="Seasonal plan (availability ended)")

    def template(name, pl, lines, validity=30, terms=15):
        t = QuotationTemplate(name=name, plan_id=pl.id, validity_days=validity, payment_terms_days=terms)
        for prod, var, qty in lines:
            t.lines.append(QuotationTemplateLine(product_id=prod.id, variant_id=var.id if var else None, quantity=qty))
        db.add(t)
        db.flush()
        return t

    t_smb = template("SMB CRM Starter", p_crm_m, [(crm, v[("Brightloop CRM", "Odoo")], 3), (storage, None, 1)])
    t_ent = template("Enterprise Suite Offer", p_ent, [(crm, v[("Brightloop CRM", "Odoo")], 25), (desk, None, 12),
                                                      (support, None, 1)], validity=45, terms=30)
    t_books = template("Books for Growing Teams", p_books, [(books, v[("Brightloop Books", "Enterprise")], 1),
                                                           (storage, None, 2)])
    template("Annual CRM Contract", p_crm_y, [(crm, v[("Brightloop CRM", "Standard")], 10)], validity=60, terms=30)

    d_vol = DiscountRule(name="Volume 10% (10+ CRM seats)", discount_type="percentage", value=10, scope="products",
                         min_quantity=10, start_date=date(2025, 11, 1))
    d_vol.products = [crm]
    d_welcome = DiscountRule(name="Welcome ₹500 off", discount_type="fixed", value=500, scope="subscription",
                             min_purchase=2000, max_usage=12, start_date=date(2026, 3, 1))
    d_diwali = DiscountRule(name="Diwali 2025 — 15% off", discount_type="percentage", value=15, scope="subscription",
                            start_date=date(2025, 10, 15), end_date=date(2025, 11, 15))
    db.add_all([d_vol, d_welcome, d_diwali])

    people = [
        ("Priya Sharma", "priya@sparkshop.demo", "SparkShop Retail", "small_business"),
        ("Arjun Nair", "arjun@kochikart.demo", "KochiKart", "small_business"),
        ("Fatima Khan", "fatima@chaiwala.demo", "Chaiwala Cafés", "small_business"),
        ("Rahul Verma", "rahul@vermaauto.demo", "Verma Auto Parts", "small_business"),
        ("Lakshmi Pillai", "lakshmi@backwater.demo", "Backwater Stays", "small_business"),
        ("Deepak Joshi", "deepak@joshitex.demo", "Joshi Textiles", "small_business"),
        ("Sneha Reddy", "sneha@greenleaf.demo", "GreenLeaf Organics", "small_business"),
        ("Thomas Mathew", "thomas@spicecoast.demo", "Spice Coast Exports", "small_business"),
        ("Kavya Iyer", "kavya@pixelcraft.demo", "PixelCraft Studio", "small_business"),
        ("Rohan Gupta", "rohan@fitnation.demo", "FitNation Gyms", "small_business"),
        ("Ananya Das", "procurement@tatvik.demo", "Tatvik Industries Ltd", "enterprise"),
        ("Suresh Menon", "it@malabarbank.demo", "Malabar Co-operative Bank", "enterprise"),
        ("Neha Kapoor", "ops@skyroute.demo", "SkyRoute Logistics", "enterprise"),
        ("Imran Sheikh", "admin@meridianhealth.demo", "Meridian Health Group", "enterprise"),
    ]
    customers = []
    for name, email, company, seg in people:
        c = Customer(name=name, email=email, company=company, segment=seg, phone=f"+91 9{rng.randint(100000000, 999999999)}",
                     address=f"{rng.randint(1, 240)}, {rng.choice(['MG Road', 'Marine Drive', 'Panampilly Nagar', 'Kakkanad', 'Edappally'])}\nKochi, Kerala 6820{rng.randint(10, 40)}", is_demo=True)
        db.add(c)
        customers.append(c)
    db.flush()
    portal_user = _user(db, "priya@sparkshop.demo", "Priya Sharma", Role.customer)
    customers[0].user_id = portal_user.id
    db.commit()

    # ------------- replay history -------------
    start_of_history = add_months(date(real_today.year, real_today.month, 1), -11)
    clock.set_today(start_of_history)
    C = customers

    def at(d: date):
        clock.set_today(d)

    def open_sub(cust, pl, tmpl=None, start=None, lines=None, demo=True):
        at(start - timedelta(days=5))
        s = subsvc.create_subscription(db, staff, customer_id=cust.id, plan_id=pl.id, template_id=tmpl.id if tmpl else None,
                                       lines=lines or [])
        s.is_demo = demo
        subsvc.send_quotation(db, staff, s)
        at(start - timedelta(days=2))
        subsvc.confirm(db, staff, s)
        at(start)
        subsvc.activate(db, staff, s, start)
        db.commit()
        return s

    m = lambda k, day=1: add_months(start_of_history, k) + timedelta(days=day - 1)  # noqa: E731
    L = subsvc.LineInput
    plan_events = []  # (date, fn)
    subs = [
        open_sub(C[0], p_crm_m, t_smb, m(0, 5)),
        open_sub(C[1], p_books, t_books, m(0, 12)),
        open_sub(C[2], p_crm_m, None, m(1, 3), [L(crm.id, v[("Brightloop CRM", "Odoo")].id, 2)]),
        open_sub(C[3], p_desk_w, None, m(6, 1)),
        open_sub(C[4], p_crm_m, t_smb, m(2, 18)),
        open_sub(C[5], p_books, None, m(3, 7)),
        open_sub(C[6], p_crm_y, None, m(0, 20), [L(crm.id, v[("Brightloop CRM", "Standard")].id, 4)]),
        open_sub(C[7], p_crm_m, None, m(4, 9), [L(crm.id, v[("Brightloop CRM", "Odoo")].id, 12),
                                                L(storage.id, None, 3)]),
        open_sub(C[8], p_books, t_books, m(5, 14)),
        open_sub(C[9], p_crm_m, t_smb, m(7, 2)),
        open_sub(C[10], p_ent, t_ent, m(0, 25)),
        open_sub(C[11], p_ent, t_ent, m(3, 1)),
        open_sub(C[12], p_crm_y, None, m(8, 15), [L(crm.id, v[("Brightloop CRM", "Odoo")].id, 40),
                                                  L(support.id, None, 1)]),
        open_sub(C[13], p_ent, None, m(6, 10), [L(crm.id, v[("Brightloop CRM", "Odoo")].id, 18),
                                                L(desk.id, None, 8)]),
        open_sub(C[1], p_daily, None, m(9, 3)),
        open_sub(C[8], p_train, None, m(10, 6)),
        open_sub(C[5], p_desk_w, None, m(9, 20)),
    ]
    # lifecycle events: pause/resume, early closure, renewal
    plan_events += [
        (m(6, 10), lambda: subsvc.pause(db, staff, subs[4], "Monsoon season — temporarily closed")),
        (m(8, 5), lambda: subsvc.resume(db, staff, subs[4])),
        (m(7, 25), lambda: subsvc.close(db, staff, subs[5], "Switched to in-house accounting")),
        (m(9, 15), lambda: subsvc.pause(db, staff, subs[16], "Customer requested pause")),
        (m(10, 28), lambda: subsvc.renew(db, staff, subs[6])),
    ]
    plan_events.sort(key=lambda e: e[0])

    def bill_until(d: date):
        at(d)
        for s in db.scalars(select(Subscription).where(Subscription.state == SubState.active)).all():
            bill_subscription(db, s.id, d, user=None, source="scheduler")
        # finance confirms drafts within a couple of days, except the very latest few
        for inv in db.scalars(select(Invoice).where(Invoice.state == InvoiceState.draft,
                                                    Invoice.invoice_date <= d - timedelta(days=2))).all():
            invsvc.confirm_invoice(db, staff, inv)
        db.commit()

    def collect(d: date):
        at(d)
        for inv in db.scalars(select(Invoice).where(Invoice.state == InvoiceState.confirmed,
                                                    Invoice.invoice_date <= d)).all():
            age = (d - inv.invoice_date).days
            key = inv.id * 7919 % 100
            if key < 8:
                continue  # chronic late payers -> overdue
            due = inv.total - inv.amount_paid
            if age >= 4 + key % 20:
                if key % 11 == 0 and inv.amount_paid == 0 and due > 2000:
                    amt = (due / 2).quantize(Decimal("0.01"))  # pays in two instalments
                else:
                    amt = due
                paysvc.record_payment(db, staff, invoice_id=inv.id, amount=amt,
                                      method=list(PaymentMethod)[key % 5], payment_date=d,
                                      note="Demo payment")
        db.commit()

    d = start_of_history
    ev = 0
    while d <= real_today:
        while ev < len(plan_events) and plan_events[ev][0] <= d:
            bill_until(plan_events[ev][0])
            at(plan_events[ev][0])
            plan_events[ev][1]()
            db.commit()
            ev += 1
        bill_until(d)
        if d.weekday() in (0, 3):
            collect(d)
        jobs.auto_close(SessionLocal, d, trigger="seed")
        d += timedelta(days=1)

    # open quotations in various states (today)
    at(real_today - timedelta(days=40))
    old = subsvc.create_subscription(db, staff, customer_id=C[3].id, plan_id=p_crm_m.id, template_id=t_smb.id, lines=[])
    subsvc.send_quotation(db, staff, old)  # will show as expired
    at(real_today - timedelta(days=3))
    subsvc.create_subscription(db, staff, customer_id=C[2].id, plan_id=p_books.id, template_id=t_books.id, lines=[])
    q2 = subsvc.create_subscription(db, staff, customer_id=C[12].id, plan_id=p_ent.id, template_id=t_ent.id, lines=[])
    subsvc.send_quotation(db, staff, q2)
    at(real_today - timedelta(days=1))
    q3 = subsvc.create_subscription(db, staff, customer_id=C[0].id, plan_id=p_crm_y.id, lines=[
        L(crm.id, v[("Brightloop CRM", "Odoo")].id, 5)])
    subsvc.send_quotation(db, staff, q3)
    subsvc.confirm(db, staff, q3)  # confirmed, awaiting activation
    # leave one invoice visibly part-paid for the demo
    at(real_today)
    part = db.scalars(select(Invoice).where(Invoice.state == InvoiceState.confirmed, Invoice.amount_paid == 0,
                                            Invoice.due_date >= real_today, Invoice.total > 2000)
                      .order_by(Invoice.total.desc())).first()
    if part:
        paysvc.record_payment(db, staff, invoice_id=part.id, amount=(part.total * Decimal("0.4")).quantize(
            Decimal("0.01")), method=PaymentMethod.bank_transfer, payment_date=real_today,
            note="Advance — balance promised next week")
    for s in db.scalars(select(Subscription)).all():
        s.is_demo = True
    db.add(AppSetting(key=MARKER, value=real_today.isoformat()))
    db.commit()
    clock.set_today(None)
    jobs.run_daily(SessionLocal, real_today, trigger="seed")
    n_sub = db.scalar(select(func.count()).select_from(Subscription))
    n_inv = db.scalar(select(func.count()).select_from(Invoice))
    n_pay = db.scalar(select(func.count()).select_from(Payment))
    print(f"Seeded Brightloop demo: {len(customers)} customers, {n_sub} subscriptions, {n_inv} invoices, "
          f"{n_pay} payments. Logins (password {DEMO_PASSWORD}): admin@brightloop.demo, staff@brightloop.demo, "
          f"priya@sparkshop.demo (customer)")
    db.close()


def bulk(n: int):
    """Synthetic load for performance testing: n customers each with one active monthly subscription and
    one confirmed invoice. Inserted in batches with plain ORM objects (not via the API) for speed."""
    db = SessionLocal()
    plan = db.scalars(select(Plan).where(Plan.name == "CRM Monthly")).first()
    if not plan:
        raise SystemExit("Run the demo seed first")
    start_idx = db.scalar(select(func.count()).select_from(Customer).where(Customer.email.like("perf%")))
    line = plan.lines[0]
    price = line.product.sales_price + (line.variant.price_extra if line.variant else 0)
    t = clock.today()
    rng = random.Random(7)
    for i in range(start_idx, start_idx + n):
        c = Customer(name=f"Perf Customer {i:05d}", email=f"perf{i:05d}@load.demo", company=f"LoadCo {i}",
                     segment="small_business", is_demo=True)
        db.add(c)
        db.flush()
        sd = t - timedelta(days=rng.randint(0, 25))
        s = Subscription(customer_id=c.id, plan_id=plan.id, state=SubState.active, quotation_date=sd,
                         start_date=sd, end_date=add_months(sd, 12) - timedelta(days=1), billing_anchor=sd,
                         next_period_index=1, next_invoice_date=add_months(sd, 1), payment_terms_days=15,
                         is_demo=True)
        s.lines.append(subsvc.SubscriptionLine(product_id=line.product_id, variant_id=line.variant_id,
                                               description="Brightloop CRM (Brand: Odoo)", quantity=1 + i % 9,
                                               unit_price=price, tax_id=line.product.tax_id))
        db.add(s)
        db.flush()
        s.number = f"SUB-{s.id:06d}"
        gross = price * (1 + i % 9)
        tax = (gross * Decimal("0.18")).quantize(Decimal("0.01"))
        inv = Invoice(customer_id=c.id, subscription_id=s.id, state=InvoiceState.confirmed, invoice_date=sd,
                      due_date=sd + timedelta(days=15), period_start=sd, period_end=add_months(sd, 1) - timedelta(days=1),
                      untaxed_amount=gross, tax_amount=tax, total=gross + tax, is_demo=True)
        db.add(inv)
        db.flush()
        inv.number = f"INV-{inv.id:06d}"
        if i % 1000 == 999:
            db.commit()
    db.commit()
    print(f"Added {n} synthetic subscriptions (+ customers, invoices) for performance testing.")
    db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bulk", type=int, default=0)
    args = ap.parse_args()
    seed()
    if args.bulk:
        bulk(args.bulk)
