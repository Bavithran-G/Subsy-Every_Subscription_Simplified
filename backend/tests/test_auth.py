import pytest
from sqlalchemy import select

from app.core.security import validate_password
from app.models import EmailOutbox, PasswordResetToken
from tests.conftest import PW, TestSession, login, register


@pytest.mark.parametrize("pw,ok", [
    ("Short!1a", False),          # 8 chars — PS requires MORE than 8
    ("Abcdefgh!", True),          # 9 chars, upper, lower, special
    ("abcdefgh!x", False),        # no uppercase
    ("ABCDEFGH!X", False),        # no lowercase
    ("Abcdefghij", False),        # no special
    ("Brightloop#2026", True),
])
def test_password_rules(pw, ok):
    assert (validate_password(pw) is None) == ok


def test_register_login_me(client):
    hdr, cid = register(client, "new@shop.in")
    assert cid
    me = client.get("/api/auth/me", headers=hdr).json()
    assert me["role"] == "customer" and me["email"] == "new@shop.in"


def test_email_unique_case_insensitive(client):
    register(client, "dup@shop.in")
    r = client.post("/api/auth/register", json={"full_name": "X Y", "email": "DUP@shop.in", "password": PW})
    assert r.status_code == 409


def test_weak_password_rejected(client):
    r = client.post("/api/auth/register", json={"full_name": "X Y", "email": "w@x.in", "password": "password"})
    assert r.status_code == 422


def test_wrong_password(client):
    register(client, "a@b.in")
    assert client.post("/api/auth/login", json={"email": "a@b.in", "password": "Wrong!pass1"}).status_code == 401


def test_logout_revokes_token(client):
    hdr, _ = register(client, "out@b.in")
    assert client.post("/api/auth/logout", headers=hdr).status_code == 200
    assert client.get("/api/auth/me", headers=hdr).status_code == 401


def test_password_reset_flow(client, monkeypatch):
    register(client, "reset@b.in")
    captured = {}
    import app.api.auth as auth_api
    orig = auth_api.new_reset_token

    def spy():
        raw, h = orig()
        captured["raw"] = raw
        return raw, h
    monkeypatch.setattr(auth_api, "new_reset_token", spy)
    r = client.post("/api/auth/forgot-password", json={"email": "reset@b.in"})
    assert r.status_code == 200 and r.json()["detail"]["email_delivery"] == "outbox"
    s = TestSession()
    mail = s.scalars(select(EmailOutbox)).one()
    assert mail.status == "not_sent"  # honest: SMTP not configured in tests
    assert captured["raw"] in mail.body
    tok = s.scalars(select(PasswordResetToken)).one()
    assert tok.token_hash != captured["raw"]  # only the hash is stored
    s.close()
    bad = client.post("/api/auth/reset-password", json={"token": captured["raw"], "password": "weak"})
    assert bad.status_code == 422
    ok = client.post("/api/auth/reset-password", json={"token": captured["raw"], "password": "N3w!Password"})
    assert ok.status_code == 200
    assert client.post("/api/auth/login", json={"email": "reset@b.in", "password": "N3w!Password"}).status_code == 200
    # token cannot be reused
    again = client.post("/api/auth/reset-password", json={"token": captured["raw"], "password": "An0ther!Pass"})
    assert again.status_code == 400


def test_forgot_password_unknown_email_same_response(client):
    r = client.post("/api/auth/forgot-password", json={"email": "ghost@nowhere.in"})
    assert r.status_code == 200


def test_only_admin_creates_staff(client, admin, staff):
    body = {"full_name": "Eve", "email": "eve@test.io", "password": PW}
    assert client.post("/api/users/staff", json=body, headers=staff).status_code == 403
    cust, _ = register(client, "c@c.in")
    assert client.post("/api/users/staff", json=body, headers=cust).status_code == 403
    assert client.post("/api/users/staff", json=body, headers=admin).status_code == 201


def test_role_restrictions(client, admin, staff, catalog):
    cust, _ = register(client, "c2@c.in")
    # staff cannot create discounts, taxes, products or plans
    disc = {"name": "X", "discount_type": "percentage", "value": "10", "scope": "subscription"}
    assert client.post("/api/discounts", json=disc, headers=staff).status_code == 403
    assert client.post("/api/taxes", json={"name": "T", "tax_type": "percentage", "rate": "5"},
                       headers=staff).status_code == 403
    # customers cannot reach internal endpoints at all
    for url in ("/api/customers", "/api/subscriptions", "/api/invoices", "/api/payments", "/api/reports/dashboard",
                "/api/users"):
        assert client.get(url, headers=cust).status_code == 403, url
    # unauthenticated
    assert client.get("/api/subscriptions").status_code == 401


def test_deactivated_user_loses_access(client, admin, staff):
    users = client.get("/api/users?role=staff", headers=admin).json()["items"]
    client.patch(f"/api/users/{users[0]['id']}", json={"is_active": False}, headers=admin)
    assert client.get("/api/customers", headers=staff).status_code == 401


def test_register_links_existing_customer_record(client, staff):
    c = client.post("/api/customers", json={"name": "Acme", "email": "acme@corp.in", "segment": "enterprise"},
                    headers=staff).json()
    _, cid = register(client, "acme@corp.in", "Acme Admin")
    assert cid == c["id"]
