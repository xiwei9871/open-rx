"""B0.1-01 — org_connection direction-aware authorization.

The initiating side must never be able to approve its own request; only the
counterparty decides. These rules are EasyRS's own security design decisions
(V-14 still NEEDS_VERIFICATION for EasyRx parity — not claimed as such).
"""
import uuid

import pytest
from sqlalchemy import select

from app.modules.audit.models import AuditEvent
from app.modules.iam.models import Membership, Organization, UserAccount
from app.security import hash_password
from tests.conftest import login

pytestmark = pytest.mark.asyncio


async def _org_id(client, needle: str) -> str:
    items = (await client.get("/v1/orgs")).json()["items"]
    return next(o["id"] for o in items if needle in o["name"])


async def _mk_member(admindb, org_id: str, role: str = "lab_admin"):
    org = await admindb.get(Organization, uuid.UUID(org_id))
    suffix = uuid.uuid4().hex[:8]
    u = UserAccount(email=f"{role}-{suffix}@easyrs.dev", display_name=f"{role} {suffix}",
                    password_hash=hash_password("Passw0rd!dev"))
    admindb.add(u)
    await admindb.flush()
    admindb.add(Membership(tenant_id=org.tenant_id, org_id=org.id,
                           user_id=u.id, role=role, status="active"))
    await admindb.commit()
    return u.email


async def _request(client, scopes=None):
    """admin@pa.dev creates a fresh lab org, requests PA -> it.
    Unique pair per test: the natural-key uq means reusing 'Unconnected Lab'
    would collide with pending rows left by other tests.
    """
    await login(client, "admin@pa.dev")
    pa = await _org_id(client, "Smile Ortho")
    r = await client.post("/v1/orgs", json={
        "kind": "lab", "name": f"Probe Lab {uuid.uuid4().hex[:8]}"})
    assert r.status_code == 201, r.text
    lb = r.json()["id"]
    r = await client.post("/v1/org-connections", json={
        "practice_org_id": pa, "lab_org_id": lb,
        "granted_scopes": scopes or []})
    assert r.status_code == 201, r.text
    return r.json()["id"], lb, r.json()["version"]


async def test_initiator_cannot_accept_own_request(client, admindb):
    """The review's P0: PA requests, PA admin tries to accept -> 403."""
    cid, _, _ = await _request(client)
    r = await client.patch(f"/v1/org-connections/{cid}",
                           json={"action": "accept", "expected_version": 0})
    assert r.status_code == 403
    ev = (await admindb.execute(select(AuditEvent).where(
        AuditEvent.action == "access_denied",
        AuditEvent.object_id.contains(cid)))).scalars().all()
    assert ev, "denied self-accept must be audited"


async def test_counterparty_accepts_and_is_stamped(client, admindb):
    cid, lb, _ = await _request(client)
    email = await _mk_member(admindb, lb)
    await login(client, email)
    r = await client.patch(f"/v1/org-connections/{cid}",
                           json={"action": "accept", "expected_version": 0})
    assert r.status_code == 200 and r.json()["status"] == "accepted"
    assert r.json()["decided_by_user_id"], "deciding actor must be recorded"
    assert r.json()["decided_at"], "decision timestamp must be recorded"
    me = (await client.get("/v1/auth/me")).json()
    assert r.json()["decided_by_user_id"] == me["user_id"]


async def test_third_party_cannot_decide(client, admindb):
    cid, _, _ = await _request(client)
    await login(client, "admin@la.dev")  # LA is not a party to PA<->LB
    for action in ("accept", "reject", "withdraw", "revoke"):
        r = await client.patch(f"/v1/org-connections/{cid}",
                               json={"action": action, "expected_version": 0})
        assert r.status_code == 403, action


async def test_duplicate_accept_and_stale_version(client, admindb):
    cid, lb, _ = await _request(client)
    email = await _mk_member(admindb, lb)
    await login(client, email)
    ok = await client.patch(f"/v1/org-connections/{cid}",
                            json={"action": "accept", "expected_version": 0})
    assert ok.status_code == 200
    # second accept: status no longer pending -> explainable 422
    dup = await client.patch(f"/v1/org-connections/{cid}",
                             json={"action": "accept", "expected_version": 1})
    assert dup.status_code == 422 and dup.json()["detail"]["code"] == "illegal_transition"
    # stale version (simulates a racing approver) -> 409
    stale = await client.patch(f"/v1/org-connections/{cid}",
                               json={"action": "revoke", "expected_version": 0})
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "version_conflict"


async def test_initiator_withdraws_pending(client, admindb):
    cid, lb, _ = await _request(client)
    # counterparty cannot withdraw the initiator's request
    email = await _mk_member(admindb, lb)
    await login(client, email)
    r = await client.patch(f"/v1/org-connections/{cid}",
                           json={"action": "withdraw", "expected_version": 0})
    assert r.status_code == 403
    # initiator can
    await login(client, "admin@pa.dev")
    r = await client.patch(f"/v1/org-connections/{cid}",
                           json={"action": "withdraw", "expected_version": 0})
    assert r.status_code == 200 and r.json()["status"] == "withdrawn"


async def test_revoke_then_reuse_and_re_request(client, admindb):
    cid, lb, _ = await _request(client)
    email = await _mk_member(admindb, lb)
    await login(client, email)
    await client.patch(f"/v1/org-connections/{cid}",
                       json={"action": "accept", "expected_version": 0})
    r = await client.patch(f"/v1/org-connections/{cid}",
                           json={"action": "revoke", "expected_version": 1})
    assert r.status_code == 200 and r.json()["status"] == "revoked"
    # post-revoke: no transition back without a fresh request cycle
    r = await client.patch(f"/v1/org-connections/{cid}",
                           json={"action": "accept", "expected_version": 2})
    assert r.status_code == 422
    # revoked grant cannot be revived implicitly — re-request makes a NEW
    # pending cycle that the (now counterparty) lab side must decide again
    await login(client, "admin@pa.dev")
    pa = await _org_id(client, "Smile Ortho")
    r = await client.post("/v1/org-connections", json={
        "practice_org_id": pa, "lab_org_id": lb})
    assert r.status_code == 201
    assert r.json()["status"] == "pending" and r.json()["id"] == cid
    assert r.json()["initiated_by_org_id"] == pa
    # the lab could reject this time — decision sovereignty stays bilateral
    await login(client, email)
    r = await client.patch(f"/v1/org-connections/{cid}", json={
        "action": "reject", "expected_version": r.json()["version"]})
    assert r.status_code == 200 and r.json()["status"] == "rejected"


async def test_accept_may_narrow_but_not_expand_scopes(client, admindb):
    cid, lb, _ = await _request(client, scopes=["rx.read", "asset.read"])
    email = await _mk_member(admindb, lb)
    await login(client, email)
    r = await client.patch(f"/v1/org-connections/{cid}", json={
        "action": "accept", "expected_version": 0,
        "granted_scopes": ["rx.read", "asset.write"]})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "scope_expansion"
    r = await client.patch(f"/v1/org-connections/{cid}", json={
        "action": "accept", "expected_version": 0,
        "granted_scopes": ["rx.read"]})
    assert r.status_code == 200 and r.json()["granted_scopes"] == ["rx.read"]
