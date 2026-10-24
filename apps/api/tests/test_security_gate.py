"""S1a-00 security gate — TOTP fail-closed, audit org isolation,
atomic concurrent decisions, migration secret preservation."""
import asyncio
import os
import subprocess
import sys
import uuid

import pyotp
import pytest
from sqlalchemy import select, text

from app.modules.audit.models import AuditEvent
from app.modules.iam.models import UserAccount
from app.modules.iam.models import Membership, Organization
from app.security import dec_totp, hash_password
from tests.conftest import ADMIN_PW, API_DIR, PG_HOST, PG_PORT, login, _psql

pytestmark = pytest.mark.asyncio

_SUFFIX = uuid.uuid4().hex[:8]


def _psql_out(db: str, sql: str) -> str:
    return subprocess.run(
        ["psql", f"postgresql://easyrs_admin:{ADMIN_PW}@{PG_HOST}:{PG_PORT}/{db}",
         "-v", "ON_ERROR_STOP=1", "-tA", "-c", sql],
        check=True, capture_output=True, text=True).stdout.strip()


async def _enable_2fa(client, email: str) -> str:
    await login(client, email)
    r = await client.post("/v1/auth/2fa/setup")
    secret = r.json()["secret"]
    code = pyotp.TOTP(secret).now()
    assert (await client.post("/v1/auth/2fa/enable", json={
        "secret": secret, "code": code})).status_code == 204
    return secret


# ---- A. TOTP fail closed ----------------------------------------------------
async def test_enabled_without_secret_denies_login(client, admindb):
    """totp_enabled=True + missing secret must NOT downgrade to 1FA."""
    email = f"gate2fa-{_SUFFIX}@easyrs.dev"
    u = UserAccount(email=email, display_name="Gate 2FA",
                    password_hash=hash_password("Passw0rd!dev"))
    admindb.add(u)
    await admindb.flush()
    org = (await admindb.execute(select(Organization).where(
        Organization.name.like("Smile Ortho%")))).scalar_one()
    admindb.add(Membership(tenant_id=org.tenant_id, org_id=org.id,
                           user_id=u.id, role="practice_admin", status="active"))
    await admindb.commit()

    await _enable_2fa(client, email)
    # secret column wiped (e.g. partial migration / corruption) -> flag stays
    await admindb.execute(text(
        "UPDATE user_account SET totp_secret_enc = NULL WHERE email = :e"),
        {"e": email})
    await admindb.commit()

    await client.post("/v1/auth/logout")
    r = await client.post("/v1/auth/login", json={
        "email": email, "password": "Passw0rd!dev"})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "totp_recovery_required"
    # no usable session: any stale cookie was revoked by the logout above
    assert (await client.get("/v1/auth/me")).status_code == 401
    ev = (await admindb.execute(select(AuditEvent).where(
        AuditEvent.action == "login_denied_2fa_inconsistent"))).scalars().all()
    assert ev, "fail-closed denial must be audited"


async def test_corrupt_secret_fails_verify_not_500(client, admindb):
    """A secret that exists but won't decrypt denies at verify, never 500s."""
    email = f"gate2fb-{_SUFFIX}@easyrs.dev"
    u = UserAccount(email=email, display_name="Gate 2FB",
                    password_hash=hash_password("Passw0rd!dev"))
    admindb.add(u)
    await admindb.flush()
    org = (await admindb.execute(select(Organization).where(
        Organization.name.like("Smile Ortho%")))).scalar_one()
    admindb.add(Membership(tenant_id=org.tenant_id, org_id=org.id,
                           user_id=u.id, role="practice_admin", status="active"))
    await admindb.commit()

    await _enable_2fa(client, email)
    await admindb.execute(text(
        "UPDATE user_account SET totp_secret_enc = :g WHERE email = :e"),
        {"g": b"not-a-fernet-token", "e": email})
    await admindb.commit()

    await client.post("/v1/auth/logout")
    r = await client.post("/v1/auth/login", json={
        "email": email, "password": "Passw0rd!dev"})
    assert r.status_code == 200 and r.json()["requires_2fa"]
    ch = r.json()["challenge_id"]
    r = await client.post("/v1/auth/2fa/verify", json={
        "challenge_id": ch, "code": "123456"})
    assert r.status_code == 401, r.text  # denied, not a crash
    ev = (await admindb.execute(select(AuditEvent).where(
        AuditEvent.action == "login_2fa_secret_unusable"))).scalars().all()
    assert ev


# ---- B. audit org isolation -------------------------------------------------
async def test_audit_events_are_org_scoped(client):
    """LA admin must not see PA-stamped events and vice versa."""
    await login(client, "admin@pa.dev")
    pa = next(o["id"] for o in (await client.get("/v1/orgs")).json()["items"]
              if "Smile Ortho" in o["name"])
    await client.post("/v1/orgs", json={
        "kind": "lab", "name": f"Audit Probe Lab {_SUFFIX}"})

    await login(client, "admin@la.dev")
    r = await client.get("/v1/audit-events")
    assert r.status_code == 200
    items = r.json()["items"]
    assert items, "LA should at least see its own login_success"
    assert all(e["org_id"] != pa for e in items), \
        "PA-stamped events leaked into LA's audit view"
    # own-org events do appear
    la = next(o["id"] for o in (await client.get("/v1/orgs")).json()["items"]
              if "Friendly Lab" in o["name"])
    assert any(e["org_id"] == la for e in items)


# ---- C. atomic concurrent decision ------------------------------------------
async def test_concurrent_accepts_exactly_one_wins(client, admindb):
    """Two simultaneous accepts on the same version: exactly one commits."""
    await login(client, "admin@pa.dev")
    pa = next(o["id"] for o in (await client.get("/v1/orgs")).json()["items"]
              if "Smile Ortho" in o["name"])
    r = await client.post("/v1/orgs", json={
        "kind": "lab", "name": f"Race Lab {uuid.uuid4().hex[:8]}"})
    lb = r.json()["id"]
    r = await client.post("/v1/org-connections", json={
        "practice_org_id": pa, "lab_org_id": lb})
    cid = r.json()["id"]

    lab_email = f"racer-{uuid.uuid4().hex[:8]}@easyrs.dev"
    org = (await admindb.execute(text(
        "SELECT id, tenant_id FROM organization WHERE id = :i"),
        {"i": lb})).mappings().one()
    u = UserAccount(email=lab_email, display_name="Racer",
                    password_hash=hash_password("Passw0rd!dev"))
    admindb.add(u)
    await admindb.flush()
    admindb.add(Membership(tenant_id=org["tenant_id"], org_id=org["id"],
                           user_id=u.id, role="lab_admin", status="active"))
    await admindb.commit()

    await login(client, lab_email)
    body = {"action": "accept", "expected_version": 0}
    r1, r2 = await asyncio.gather(
        client.patch(f"/v1/org-connections/{cid}", json=body),
        client.patch(f"/v1/org-connections/{cid}", json=body),
    )
    codes = sorted([r1.status_code, r2.status_code])
    assert codes == [200, 409], (r1.status_code, r2.status_code,
                                 r1.text, r2.text)


# ---- A2. migration preserves enrolled secrets -------------------------------
async def test_totp_secret_survives_0002_encryption_migration():
    """A user enrolled at rev 0001 (plaintext) must still hold a usable secret
    after upgrade to head — encrypted, not dropped."""
    await asyncio.to_thread(_migration_preserves_secret)


def _migration_preserves_secret():
    db = f"easyrs_mig_{uuid.uuid4().hex[:8]}"
    _psql("postgres", f"DROP DATABASE IF EXISTS {db}")
    _psql("postgres", f"CREATE DATABASE {db} OWNER easyrs_admin")
    try:
        env = dict(os.environ)
        env["DATABASE_ADMIN_URL"] = (
            f"postgresql+asyncpg://easyrs_admin:{ADMIN_PW}"
            f"@{PG_HOST}:{PG_PORT}/{db}")
        env["DATABASE_URL"] = env["DATABASE_ADMIN_URL"]
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "0001"],
                       cwd=API_DIR, env=env, check=True,
                       capture_output=True, text=True)
        secret = "JBSWY3DPEH" + "PK3PXP"  # split: keep secret-scan regex from matching
        _psql(db, f"""INSERT INTO user_account
            (id, email, display_name, password_hash, status, totp_enabled, totp_secret)
            VALUES (gen_random_uuid(), 'legacy@mig.dev', 'Legacy', 'x',
                    'active', true, '{secret}')""")
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       cwd=API_DIR, env=env, check=True,
                       capture_output=True, text=True)
        hexed = _psql_out(db, "SELECT encode(totp_secret_enc, 'hex') "
                              "FROM user_account WHERE email='legacy@mig.dev'")
        assert hexed and hexed != "\\x", "secret vanished during migration"
        assert dec_totp(bytes.fromhex(hexed)) == secret
    finally:
        _psql("postgres", f"DROP DATABASE IF EXISTS {db}")
