"""Role/permission enforcement + audit trail verification."""
import pytest
from sqlalchemy import select

from app.modules.audit.models import AuditEvent
from tests.conftest import login

pytestmark = pytest.mark.asyncio


async def test_staff_cannot_manage_org(client):
    await login(client, "staff@pa.dev")   # roster:read only
    r = await client.post("/v1/orgs", json={"kind": "practice", "name": "X"})
    assert r.status_code == 403


async def test_admin_manages_org_lifecycle(client):
    await login(client, "admin@pa.dev")
    r = await client.post("/v1/orgs", json={
        "kind": "practice", "name": "New Practice (synthetic)"})
    assert r.status_code == 201
    org_id = r.json()["id"]

    # admin's active org is PA — they cannot manage the NEW org's members
    # (no membership there) -> org isolation still applies
    r = await client.get(f"/v1/orgs/{org_id}/members")
    assert r.status_code == 403


async def test_member_write_required_for_member_list(client):
    await login(client, "staff@pa.dev")
    pa_id = next(o["id"] for o in (await client.get("/v1/orgs")).json()["items"]
                 if "Smile Ortho" in o["name"])
    assert (await client.get(f"/v1/orgs/{pa_id}/members")).status_code == 403
    # roster read is allowed for staff (roster:read / member-level)
    assert (await client.get(f"/v1/orgs/{pa_id}/roster")).status_code == 200


async def test_lab_technician_minimal_perms(client):
    await login(client, "tech@la.dev")
    assert (await client.post("/v1/orgs", json={
        "kind": "lab", "name": "Nope"})).status_code == 403
    la_id = next(o["id"] for o in (await client.get("/v1/orgs")).json()["items"]
                 if "Friendly Lab" in o["name"])
    # can read own org's roster but not write
    assert (await client.get(f"/v1/orgs/{la_id}/roster")).status_code == 200
    assert (await client.post(f"/v1/orgs/{la_id}/roster", json={
        "kind": "staff", "display_name": "x"})).status_code == 403


async def test_audit_records_security_events(client, admindb):
    await login(client, "staff@pa.dev")
    await client.post("/v1/orgs", json={"kind": "lab", "name": "Denied"})
    ev = (await admindb.execute(select(AuditEvent).where(
        AuditEvent.action == "access_denied"))).scalars().all()
    assert any("/v1/orgs" in e.object_id for e in ev)

    ev2 = (await admindb.execute(select(AuditEvent).where(
        AuditEvent.action == "login_success"))).scalars().all()
    assert ev2


async def test_audit_list_requires_permission(client):
    await login(client, "staff@pa.dev")
    assert (await client.get("/v1/audit-events")).status_code == 403
    await login(client, "admin@pa.dev")
    r = await client.get("/v1/audit-events")
    assert r.status_code == 200
    actions = {e["action"] for e in r.json()["items"]}
    assert "login_success" in actions
