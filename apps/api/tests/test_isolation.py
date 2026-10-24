"""Tenant + organization isolation — app layer AND PostgreSQL RLS layer.

Covers authz-test-matrix intent: authorized access, unauthorized access,
cross-tenant denial (AZ-32 class), and no-oracle 403 semantics (AZ-30 class).
"""
import uuid

import pytest
from sqlalchemy import select, text

from app.modules.iam.models import (
    Membership, Organization, Tenant, UserAccount,
)
from app.security import hash_password
from tests.conftest import login

pytestmark = pytest.mark.asyncio


async def _mk_tenant2(admindb):
    """Create a second tenant with its own org/user (synthetic)."""
    suffix = uuid.uuid4().hex[:8]
    t2 = Tenant(name=f"Other Tenant {suffix}")
    admindb.add(t2)
    await admindb.flush()
    org = Organization(tenant_id=t2.id, kind="practice", name=f"Org T2 {suffix}")
    admindb.add(org)
    user = UserAccount(email=f"admin@t2-{suffix}.dev", display_name="T2 Admin",
                       password_hash=hash_password("Passw0rd!dev"))
    admindb.add(user)
    await admindb.flush()
    admindb.add(Membership(tenant_id=t2.id, org_id=org.id, user_id=user.id,
                           role="practice_admin", status="active"))
    await admindb.commit()
    return t2, org, user


async def _org_id(client, name_contains: str) -> str:
    items = (await client.get("/v1/orgs")).json()["items"]
    return next(o["id"] for o in items if name_contains in o["name"])


async def test_tenant_isolation_api_layer(client, admindb):
    t2, t2_org, t2_user = await _mk_tenant2(admindb)

    await login(client, "admin@pa.dev")           # T1
    items = (await client.get("/v1/orgs")).json()["items"]
    names = {o["name"] for o in items}
    assert "Smile Ortho (synthetic)" in names and t2_org.name not in names

    # cross-tenant id probing -> uniform 403, no existence leak (AZ-30/32)
    r = await client.get(f"/v1/orgs/{t2_org.id}/locations")
    assert r.status_code == 403
    r = await client.get(f"/v1/orgs/{uuid.uuid4()}/locations")   # nonexistent id
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "forbidden"

    # T2 user sees only their own org
    c2 = client
    await login(c2, t2_user.email)
    names2 = {o["name"] for o in (await c2.get("/v1/orgs")).json()["items"]}
    assert names2 == {t2_org.name}


async def test_tenant_isolation_rls_layer(appdb, admindb):
    """Prove the wall exists below the app: same query, different GUC."""
    t2, t2_org, _ = await _mk_tenant2(admindb)
    t1 = (await admindb.execute(select(Tenant).where(
        Tenant.name == "Dev Tenant (synthetic)"))).scalar_one()

    for tid, expect_in, expect_out in [
        (t1.id, "Smile Ortho", t2_org.name),
        (t2.id, t2_org.name, "Smile Ortho"),
    ]:
        await appdb.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tid)})
        names = {r[0] for r in (await appdb.execute(
            text("SELECT name FROM organization"))).all()}
        assert expect_in in next(n for n in names if expect_in in n)
        assert not any(expect_out in n for n in names)
        await appdb.rollback()


async def test_org_isolation_same_tenant(client):
    """Same tenant, different org: PA admin cannot touch LA's subresources."""
    await login(client, "admin@pa.dev")
    la_id = await _org_id(client, "Friendly Lab")
    for method, url, kw in [
        ("get", f"/v1/orgs/{la_id}/members", {}),
        ("get", f"/v1/orgs/{la_id}/roster", {}),
        ("get", f"/v1/orgs/{la_id}/locations", {}),
        ("post", f"/v1/orgs/{la_id}/roster",
         {"json": {"kind": "staff", "display_name": "x"}}),
    ]:
        r = await getattr(client, method)(url, **kw)
        assert r.status_code == 403, (method, url, r.status_code)

    # own org works
    pa_id = await _org_id(client, "Smile Ortho")
    assert (await client.get(f"/v1/orgs/{pa_id}/members")).status_code == 200
    assert (await client.get(f"/v1/orgs/{pa_id}/roster")).status_code == 200


async def test_connection_request_and_idempotency(client):
    """PA->LB connection request; repeat returns same row (natural key)."""
    await login(client, "admin@pa.dev")
    pa = await _org_id(client, "Smile Ortho")
    lb = await _org_id(client, "Unconnected Lab")
    body = {"practice_org_id": pa, "lab_org_id": lb}
    r1 = await client.post("/v1/org-connections", json=body)
    assert r1.status_code == 201 and r1.json()["status"] == "pending"
    r2 = await client.post("/v1/org-connections", json=body)
    assert r2.status_code in (200, 201) and r2.json()["id"] == r1.json()["id"]

    # version guard on transition
    r = await client.patch(f"/v1/org-connections/{r1.json()['id']}",
                           json={"action": "accept", "expected_version": 9})
    assert r.status_code == 409

    # LA admin is not a party to PA<->LB -> 403
    await login(client, "admin@la.dev")
    r = await client.patch(f"/v1/org-connections/{r1.json()['id']}",
                           json={"action": "accept", "expected_version": 0})
    assert r.status_code == 403


async def test_connection_accept_by_receiving_side(client, admindb):
    """LB admin accepts the pending connection with matching version."""
    await login(client, "admin@pa.dev")
    pa = await _org_id(client, "Smile Ortho")
    lb = await _org_id(client, "Unconnected Lab")
    r1 = await client.post("/v1/org-connections",
                           json={"practice_org_id": pa, "lab_org_id": lb})
    conn_id = r1.json()["id"]

    lb_org = await admindb.get(Organization, uuid.UUID(lb))
    suffix = uuid.uuid4().hex[:8]
    u = UserAccount(email=f"lbadmin-{suffix}@easyrs.dev", display_name="LB Admin",
                    password_hash=hash_password("Passw0rd!dev"))
    admindb.add(u)
    await admindb.flush()
    admindb.add(Membership(tenant_id=lb_org.tenant_id, org_id=lb_org.id,
                           user_id=u.id, role="lab_admin", status="active"))
    await admindb.commit()

    await login(client, u.email)
    r = await client.patch(f"/v1/org-connections/{conn_id}",
                           json={"action": "accept", "expected_version": 0})
    assert r.status_code == 200 and r.json()["status"] == "accepted" \
        and r.json()["version"] == 1

    # revoke by either party still works; accept after accepted is illegal
    r = await client.patch(f"/v1/org-connections/{conn_id}",
                           json={"action": "accept", "expected_version": 1})
    assert r.status_code == 422
    r = await client.patch(f"/v1/org-connections/{conn_id}",
                           json={"action": "revoke", "expected_version": 1})
    assert r.status_code == 200 and r.json()["status"] == "revoked"
