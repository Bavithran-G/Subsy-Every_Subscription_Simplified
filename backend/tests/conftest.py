import os
from datetime import date

os.environ.setdefault("SUBSY_DATABASE_URL", "postgresql+psycopg://subsy:subsy@localhost:5432/subsy_test")
os.environ["SUBSY_SCHEDULER_ENABLED"] = "false"
os.environ["SUBSY_SMTP_HOST"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core import clock  # noqa: E402
from app.core.db import Base, get_db  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Role, User  # noqa: E402

engine = create_engine(os.environ["SUBSY_DATABASE_URL"], future=True)
TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
PW = "Str0ng!Pass"


@pytest.fixture(scope="session", autouse=True)
def schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(autouse=True)
def clean():
    with engine.begin() as conn:
        tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    clock.set_today(date(2026, 1, 15))
    yield
    clock.set_today(None)


@pytest.fixture
def db():
    s = TestSession()
    yield s
    s.close()


def _override():
    s = TestSession()
    try:
        yield s
    finally:
        s.close()


app.dependency_overrides[get_db] = _override

# the manual "run billing" endpoint uses the app's SessionLocal — point it at the test DB
import app.api.invoices as inv_api  # noqa: E402
import app.api.admin as admin_api  # noqa: E402

inv_api.SessionLocal = TestSession
admin_api.SessionLocal = TestSession


@pytest.fixture
def client():
    return TestClient(app)


def make_user(email, role, name="User"):
    s = TestSession()
    u = User(email=email, password_hash=hash_password(PW), full_name=name, role=role)
    s.add(u)
    s.commit()
    s.close()


def login(client, email):
    r = client.post("/api/auth/login", json={"email": email, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def admin(client):
    make_user("admin@test.io", Role.admin, "Ada Admin")
    return login(client, "admin@test.io")


@pytest.fixture
def staff(client, admin):
    r = client.post("/api/users/staff", json={"full_name": "Sam Staff", "email": "staff@test.io", "password": PW},
                    headers=admin)
    assert r.status_code == 201, r.text
    return login(client, "staff@test.io")


def register(client, email, name="Cara Customer"):
    r = client.post("/api/auth/register", json={"full_name": name, "email": email, "password": PW})
    assert r.status_code == 201, r.text
    body = r.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["customer_id"]


@pytest.fixture
def catalog(client, admin):
    """GST 18%, a software product with an Odoo brand variant (+560), an add-on, and a monthly plan."""
    tax = client.post("/api/taxes", json={"name": "GST 18%", "tax_type": "percentage", "rate": "18"},
                      headers=admin).json()
    crm = client.post("/api/products", headers=admin, json={
        "name": "Brightloop CRM", "product_type": "software", "sales_price": "1000", "cost_price": "300",
        "tax_id": tax["id"], "variants": [{"attribute": "Brand", "value": "Odoo", "price_extra": "560"},
                                          {"attribute": "Brand", "value": "Standard", "price_extra": "0"}]}).json()
    addon = client.post("/api/products", headers=admin, json={
        "name": "Extra Storage", "product_type": "addon", "sales_price": "200", "tax_id": tax["id"]}).json()
    odoo = next(v for v in crm["variants"] if v["value"] == "Odoo")
    plan = client.post("/api/plans", headers=admin, json={
        "name": "CRM Monthly", "billing_period": "monthly", "min_quantity": 1, "pausable": True,
        "renewable": True, "closable": True, "term_periods": 12,
        "lines": [{"product_id": crm["id"], "variant_id": odoo["id"], "quantity": 1}]}).json()
    tmpl = client.post("/api/templates", headers=admin, json={
        "name": "CRM Standard Offer", "plan_id": plan["id"], "validity_days": 30, "payment_terms_days": 15,
        "lines": [{"product_id": crm["id"], "variant_id": odoo["id"], "quantity": 5},
                  {"product_id": addon["id"], "quantity": 2}]}).json()
    return {"tax": tax, "crm": crm, "addon": addon, "odoo": odoo, "plan": plan, "template": tmpl}


def active_sub(client, hdr, customer_id, catalog, start="2026-01-15"):
    r = client.post("/api/subscriptions", headers=hdr, json={
        "customer_id": customer_id, "plan_id": catalog["plan"]["id"], "template_id": catalog["template"]["id"]})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    for action, body in (("confirm", {}), ("activate", {"start_date": start})):
        r = client.post(f"/api/subscriptions/{sid}/actions/{action}", headers=hdr, json=body)
        assert r.status_code == 200, r.text
    return r.json()
