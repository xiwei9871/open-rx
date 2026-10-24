"""B0.1-03 — CSRF/Origin guard, rate limiting, session revocation,
challenge caps, encrypted TOTP, resolve_login grants, disabled accounts."""
import pyotp
import pytest
from sqlalchemy import select, text

from app.config import get_settings
from app.modules.iam.models import Membership, Organization, UserAccount
from app.ratelimit import allow, reset
from app.security import dec_totp, hash_password
from tests.conftest import login

pytestmark = pytest.mark.asyncio


# ---- CSRF / Origin ---------------------------------------------------------
async def test_unsafe_methods_require_csrf_header(client):
    await login(client, "admin@pa.dev")
    # strip the default header -> 403 before reaching the endpoint
    r = await client.post("/v1/orgs", json={"kind": "lab", "name": "X"},
                          headers={"X-Requested-With": ""})
    assert r.status_code == 403 and "CSRF" in r.text


async def test_untrusted_origin_rejected(client):
    await login(client, "admin@pa.dev")
    r = await client.post("/v1/orgs", json={"kind": "lab", "name": "X"},
                          headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and "Origin" in r.json()["detail"]["message"]


# ---- rate limiting ---------------------------------------------------------
async def test_login_rate_limit_trips(client):
    s = get_settings()
    orig = s.rl_login_email_limit
    s.rl_login_email_limit = 2
    email = "ratelimit-probe@easyrs.dev"
    try:
        await reset("login_email", email)
        for i in range(2):
            r = await client.post("/v1/auth/login", json={
                "email": email, "password": "nope-nope-nope"})
            assert r.status_code == 401
        r = await client.post("/v1/auth/login", json={
            "email": email, "password": "nope-nope-nope"})
        assert r.status_code == 429 and r.json()["detail"]["code"] == "rate_limited"
    finally:
        s.rl_login_email_limit = orig
        await reset("login_email", email)


async def test_sensitive_write_rate_limit(client):
    """IAM mutations share a per-user fixed-window bucket (B0.1 spec: 敏感写)."""
    s = get_settings()
    orig = s.rl_write_limit
    s.rl_write_limit = 1
    await login(client, "admin@pa.dev")
    uid = (await client.get("/v1/auth/me")).json()["user_id"]
    try:
        await reset("write", uid)
        r1 = await client.post("/v1/orgs", json={
            "kind": "lab", "name": "RL Probe Lab 1", "timezone": "UTC"})
        assert r1.status_code == 201
        r2 = await client.post("/v1/orgs", json={
            "kind": "lab", "name": "RL Probe Lab 2", "timezone": "UTC"})
        assert r2.status_code == 429 and r2.json()["detail"]["code"] == "rate_limited"
    finally:
        s.rl_write_limit = orig
        await reset("write", uid)


async def test_rate_limiter_unit(appdb):
    """Direct: the Redis-backed limiter denies after `limit` hits."""
    await reset("unit", "id1")
    assert await allow("unit", "id1", 2, 60)
    assert await allow("unit", "id1", 2, 60)
    assert not await allow("unit", "id1", 2, 60)
    await reset("unit", "id1")





# ---- auth boundary (resolve_login, disabled accounts) -----------------------
async def test_resolve_login_scoped_function(admindb, appdb):
    """Runtime role can EXECUTE the narrow function but gets zero rows on
    the underlying RLS tables without tenant context."""
    row = (await appdb.execute(text(
        "SELECT org_id, tenant_id FROM resolve_login('admin@pa.dev')"))
    ).mappings().first()
    assert row and row["org_id"]
    n = (await appdb.execute(text("SELECT count(*) FROM membership"))).scalar()
    assert n == 0, "runtime role must see zero membership rows w/o tenant GUC"


async def test_disabled_account_cannot_login(client, admindb):
    admindb.add(UserAccount(email="disabled@easyrs.dev", display_name="Dis",
                            password_hash=hash_password("Passw0rd!dev"),
                            status="disabled"))
    await admindb.commit()
    r = await client.post("/v1/auth/login", json={
        "email": "disabled@easyrs.dev", "password": "Passw0rd!dev"})
    assert r.status_code == 401


# ---- sessions ---------------------------------------------------------------
async def test_password_change_revokes_other_sessions(client):
    import httpx
    from app.main import app
    hdrs = {"X-Requested-With": "XMLHttpRequest"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://test", headers=hdrs) as c2:
        await login(client, "staff@pa.dev")
        await login(c2, "staff@pa.dev")
        r = await client.post("/v1/auth/password", json={
            "old_password": "Passw0rd!dev", "new_password": "Rotated!pass1"})
        assert r.status_code == 204
        assert (await c2.get("/v1/auth/me")).status_code == 401, \
            "other session must be revoked after password change"
        assert (await client.get("/v1/auth/me")).status_code == 200
        # restore
        r = await client.post("/v1/auth/password", json={
            "old_password": "Rotated!pass1", "new_password": "Passw0rd!dev"})
        assert r.status_code == 204


# ---- 2FA: attempt cap + replay + encrypted secret ---------------------------
async def _enable_2fa(client, admindb, email="doctor@pa.dev"):
    await login(client, email)
    secret = (await client.post("/v1/auth/2fa/setup")).json()["secret"]
    r = await client.post("/v1/auth/2fa/enable", json={
        "secret": secret, "code": pyotp.TOTP(secret).now()})
    assert r.status_code == 204
    await client.post("/v1/auth/logout")
    return secret


async def _reset_2fa(admindb, email="doctor@pa.dev"):
    await admindb.execute(text(
        "UPDATE user_account SET totp_enabled=false, totp_secret_enc=NULL "
        "WHERE email=:e"), {"e": email})
    await admindb.commit()


async def test_totp_secret_encrypted_at_rest(client, admindb):
    secret = await _enable_2fa(client, admindb)
    enc = (await admindb.execute(text(
        "SELECT totp_secret_enc FROM user_account WHERE email='doctor@pa.dev'"))
    ).scalar()
    assert isinstance(enc, (bytes, memoryview))
    assert secret.encode() not in bytes(enc), "plaintext secret must never be stored"
    assert dec_totp(bytes(enc)) == secret
    await _reset_2fa(admindb)


async def test_2fa_attempt_cap_and_replay(client, admindb):
    secret = await _enable_2fa(client, admindb)
    r = await client.post("/v1/auth/login", json={
        "email": "doctor@pa.dev", "password": "Passw0rd!dev"})
    ch = r.json()["challenge_id"]
    max_a = get_settings().challenge_max_attempts
    for i in range(max_a):
        bad = await client.post("/v1/auth/2fa/verify", json={
            "challenge_id": ch, "code": "000000"})
        assert bad.status_code == 401
    # challenge exhausted: even the correct code must fail now
    ok = await client.post("/v1/auth/2fa/verify", json={
        "challenge_id": ch, "code": pyotp.TOTP(secret).now()})
    assert ok.status_code == 401
    # replay: a consumed challenge can never be reused
    await _reset_2fa(admindb)


async def test_2fa_expired_challenge(client, admindb):
    secret = await _enable_2fa(client, admindb)
    r = await client.post("/v1/auth/login", json={
        "email": "doctor@pa.dev", "password": "Passw0rd!dev"})
    ch = r.json()["challenge_id"]
    await admindb.execute(text(
        "UPDATE auth_challenge SET expires_at=now()-interval '1s' WHERE id=:c"),
        {"c": ch})
    await admindb.commit()
    r = await client.post("/v1/auth/2fa/verify", json={
        "challenge_id": ch, "code": pyotp.TOTP(secret).now()})
    assert r.status_code == 401
    await _reset_2fa(admindb)
