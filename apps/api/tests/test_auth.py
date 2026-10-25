"""TASK-0002: login, session, password change, TOTP 2FA — real HTTP via ASGI."""
import pyotp
import pytest
from sqlalchemy import select, text

from app.modules.audit.models import AuditEvent
from tests.conftest import login

pytestmark = pytest.mark.asyncio


async def test_healthz(client):
    r = await client.get("/healthz")
    assert r.status_code == 200 and r.json()["status"] == "ok"


async def test_login_success_and_me(client):
    await login(client, "admin@pa.dev")
    me = (await client.get("/v1/auth/me")).json()
    assert me["email"] == "admin@pa.dev"
    assert me["role"] == "practice_admin"
    assert me["org_kind"] == "practice"
    assert "org:manage" in me["permissions"]


async def test_login_wrong_password(client, admindb):
    r = await client.post("/v1/auth/login",
                          json={"email": "admin@pa.dev", "password": "wrongpw123"})
    assert r.status_code == 401
    ev = (await admindb.execute(select(AuditEvent).where(
        AuditEvent.action == "login_failed"))).scalars().all()
    assert ev, "login_failed audit row missing"


async def test_unauthenticated_401(client):
    assert (await client.get("/v1/auth/me")).status_code == 401
    assert (await client.get("/v1/orgs")).status_code == 401


async def test_logout_revokes_session(client):
    await login(client, "staff@pa.dev")
    await client.post("/v1/auth/logout")
    assert (await client.get("/v1/auth/me")).status_code == 401


async def test_login_sets_session_and_hint_cookies(client):
    r = await login(client, "staff@pa.dev")
    cookies = r.headers.get_list("set-cookie")
    joined = "; ".join(cookies)
    assert "easyrs_session=" in joined
    assert "easyrs_session_hint=1" in joined
    # session must stay HttpOnly; the hint must NOT (JS reads it to gate me())
    sess = [c for c in cookies if c.startswith("easyrs_session=")][0]
    hint = [c for c in cookies if c.startswith("easyrs_session_hint=")][0]
    assert "httponly" in sess.lower()
    assert "httponly" not in hint.lower()


async def test_logout_sends_delete_headers_for_both_cookies(client):
    await login(client, "staff@pa.dev")
    r = await client.post("/v1/auth/logout")
    assert r.status_code == 204
    cookies = r.headers.get_list("set-cookie")
    for name in ("easyrs_session", "easyrs_session_hint"):
        dele = [c for c in cookies
                if c.startswith(f"{name}=")
                and ("max-age=0" in c.lower() or "expires=" in c.lower())]
        assert dele, f"logout did not send a delete Set-Cookie for {name}"
    # jar emptied: follow-up request carries no cookies
    assert (await client.get("/v1/auth/me")).status_code == 401


async def test_password_change_flow(client):
    await login(client, "staff@pa.dev")
    r = await client.post("/v1/auth/password", json={
        "old_password": "Passw0rd!dev", "new_password": "NewPassw0rd!x"})
    assert r.status_code == 204
    c2 = client  # fresh login with new password on same client
    r = await c2.post("/v1/auth/login",
                      json={"email": "staff@pa.dev", "password": "NewPassw0rd!x"})
    assert r.status_code == 200
    # revert so other tests stay deterministic
    await c2.post("/v1/auth/password", json={
        "old_password": "NewPassw0rd!x", "new_password": "Passw0rd!dev"})


async def test_totp_2fa_full_flow(client, admindb):
    """setup -> enable -> logout -> login(requires_2fa) -> verify -> me."""
    await login(client, "tech@la.dev")
    secret = (await client.post("/v1/auth/2fa/setup")).json()["secret"]
    code = pyotp.TOTP(secret).now()
    assert (await client.post("/v1/auth/2fa/enable",
                              json={"secret": secret, "code": code})
            ).status_code == 204
    await client.post("/v1/auth/logout")

    r = await client.post("/v1/auth/login",
                          json={"email": "tech@la.dev", "password": "Passw0rd!dev"})
    assert r.status_code == 200 and r.json()["requires_2fa"] is True
    ch = r.json()["challenge_id"]

    # wrong code fails
    bad = await client.post("/v1/auth/2fa/verify",
                            json={"challenge_id": ch, "code": "000000"})
    assert bad.status_code == 401

    # fresh challenge (old one consumed? no — bad code doesn't consume)
    ok = await client.post("/v1/auth/2fa/verify", json={
        "challenge_id": ch, "code": pyotp.TOTP(secret).now()})
    assert ok.status_code == 200
    assert (await client.get("/v1/auth/me")).status_code == 200

    # cleanup: disable 2fa for determinism (seed is NOT encrypted-at-rest;
    # the column is bytea now — a NULL reset is sufficient)
    await admindb.execute(text(
        "UPDATE user_account SET totp_enabled=false, totp_secret_enc=NULL "
        "WHERE email='tech@la.dev'"))
    await admindb.commit()
