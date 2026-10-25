"""M2 collaboration: notifications, message center, signed approvals bound to
Rx version (E2E-09), attachment-anchored comments. Real Postgres, synthetic.
"""
import uuid
import io

import pytest
import pytest_asyncio

from tests.conftest import login
from tests.test_rx import s3ok  # noqa: F401  (shared S3 gate fixture)

pytestmark = pytest.mark.asyncio

ADMIN = "admin@pa.dev"
DOCTOR = "doctor@pa.dev"
LAB_ADMIN = "admin@la.dev"


async def _patient_id(client) -> str:
    r = await client.get("/v1/patients?external_ref=SYN-0001")
    return r.json()["items"][0]["id"]


async def _lab_org_id(client) -> str:
    me = (await client.get("/v1/auth/me")).json()
    r = await client.get(f"/v1/org-connections?org_id={me['org_id']}")
    return [c for c in r.json()["items"] if c["status"] == "accepted"][0]["lab_org_id"]


async def _catalog_id(client, code: str) -> str:
    for kind in ("parts", "appliances"):
        r = await client.get(f"/v1/catalog/{kind}")
        hit = [i for i in r.json()["items"] if i["code"] == code]
        if hit:
            return hit[0]["id"]
    raise AssertionError(code)


async def _submitted_rx(client) -> dict:
    """Practice submits a fresh Rx to Friendly Lab; returns submitted row."""
    await login(client, ADMIN)
    r = await client.post("/v1/rx", json={
        "patient_id": await _patient_id(client),
        "lab_org_id": await _lab_org_id(client)})
    rx = r.json()
    r = await client.put(f"/v1/rx/{rx['id']}/items", json={"items": [{
        "appliance_id": await _catalog_id(client, "HWL"), "arch": "upper"}]},
        headers={"If-Match": str(rx["version"])})
    assert r.status_code == 200, r.text
    rx = (await client.get(f"/v1/rx/{rx['id']}")).json()
    r = await client.post(f"/v1/rx/{rx['id']}/submit", json={
        "signature_name": "Dr Demo", "confirm_submit": True},
        headers={"If-Match": str(rx["version"]),
                 "Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 200, r.text
    return r.json()


async def test_issue_notification_flow(client):
    """LAB-002/COM-002: lab raises issue -> practice inbox -> ack resolves."""
    rx = await _submitted_rx(client)
    await login(client, LAB_ADMIN)
    r = await client.post("/v1/notifications", json={
        "rx_id": rx["id"], "kind": "ack_required",
        "subject": "Margin unclear on 16", "body": "please confirm"})
    assert r.status_code == 201, r.text
    # practice sees it
    await login(client, ADMIN)
    inbox = (await client.get("/v1/notifications")).json()
    hit = [n for n in inbox["items"] if n["subject"] == "Margin unclear on 16"]
    assert hit and inbox["counts"]["unread"] >= 1
    r = await client.post(f"/v1/notifications/{hit[0]['id']}/read")
    assert r.json()["status"] == "resolved"  # ack_required consumed


async def test_approval_loop_signed_and_version_bound(client, admindb):
    """COM-004/E2E-09: approval_required -> signed decision bound to version,
    recorded in audit + transition trail."""
    rx = await _submitted_rx(client)
    await login(client, LAB_ADMIN)
    n = (await client.post("/v1/notifications", json={
        "rx_id": rx["id"], "kind": "approval_required",
        "subject": "Approve pontic design"})).json()
    assert n["rx_version_at_creation"] == rx["version"]
    await login(client, DOCTOR)
    inbox = (await client.get("/v1/notifications")).json()
    assert inbox["counts"]["approval_pending"] >= 1
    r = await client.post(f"/v1/notifications/{n['id']}/decision", json={
        "decision": "approved", "signature_name": "Dr. Demo",
        "comment": "ok as proposed"},
        headers={"Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 200, r.text
    ap = r.json()
    assert ap["decision"] == "approved" and ap["rx_version"] == rx["version"]
    assert ap["signature_name"] == "Dr. Demo"
    # persisted + notification resolved + transition event
    from app.modules.rx.models import Approval, RxTransition
    from sqlalchemy import select
    row = (await admindb.execute(select(Approval).where(
        Approval.id == uuid.UUID(ap["id"])))).scalar_one()
    assert row.decided_by_user_id is not None and row.decided_at is not None
    n2 = (await client.get("/v1/notifications?status=resolved")).json()["items"]
    assert any(x["id"] == n["id"] for x in n2)
    tr = (await client.get(f"/v1/rx/{rx['id']}/transitions")).json()["items"]
    assert any(t["via"] == "approval" and "approved" in (t["note"] or "")
               for t in tr)


async def test_approval_replay_returns_existing(client):
    rx = await _submitted_rx(client)
    await login(client, LAB_ADMIN)
    n = (await client.post("/v1/notifications", json={
        "rx_id": rx["id"], "kind": "approval_required",
        "subject": "A1"})).json()
    await login(client, DOCTOR)
    r1 = await client.post(f"/v1/notifications/{n['id']}/decision", json={
        "decision": "rejected", "signature_name": "Dr. Demo"},
        headers={"Idempotency-Key": str(uuid.uuid4())})
    r2 = await client.post(f"/v1/notifications/{n['id']}/decision", json={
        "decision": "approved", "signature_name": "Someone Else"},
        headers={"Idempotency-Key": str(uuid.uuid4())})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]          # replay, not 2nd decision
    assert r2.json()["decision"] == "rejected"


async def test_stale_approval_rejected_on_version_drift(client):
    """Rx mutated after request -> decide = 409 version_drift (no silent
    carry-over of old conclusions). unsubmit->resubmit bumps version."""
    rx = await _submitted_rx(client)
    await login(client, LAB_ADMIN)
    n = (await client.post("/v1/notifications", json={
        "rx_id": rx["id"], "kind": "approval_required",
        "subject": "stale-check"})).json()
    await login(client, ADMIN)
    r = await client.post(f"/v1/rx/{rx['id']}/unsubmit", json={},
                          headers={"If-Match": str(rx["version"])})
    assert r.status_code == 200, r.text
    cur = (await client.get(f"/v1/rx/{rx['id']}")).json()
    r = await client.post(f"/v1/rx/{cur['id']}/submit", json={
        "signature_name": "Dr Demo", "confirm_submit": True},
        headers={"If-Match": str(cur["version"]),
                 "Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 200, r.text
    await login(client, DOCTOR)
    r = await client.post(f"/v1/notifications/{n['id']}/decision", json={
        "decision": "approved", "signature_name": "Dr. Demo"},
        headers={"Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "version_drift"


async def test_lab_complete_and_practice_cannot(client):
    """LAB-019: checked_in -> completed by lab; practice-side is denied."""
    rx = await _submitted_rx(client)
    await login(client, LAB_ADMIN)
    cur = (await client.get(f"/v1/rx/{rx['id']}")).json()
    r = await client.post(f"/v1/rx/{rx['id']}/check-in", json={},
                          headers={"If-Match": str(cur["version"])})
    assert r.status_code == 200, r.text
    cur = r.json()
    r = await client.post(f"/v1/rx/{rx['id']}/complete", json={},
                          headers={"If-Match": str(cur["version"])})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"
    assert r.json()["completed_at"] is not None
    # repeat is idempotent
    r2 = await client.post(f"/v1/rx/{rx['id']}/complete", json={},
                           headers={"If-Match": "999"})
    assert r2.status_code == 200 and r2.json()["status"] == "completed"
    # practice cannot complete
    await login(client, ADMIN)
    r = await client.post(f"/v1/rx/{rx['id']}/complete", json={},
                          headers={"If-Match": str(cur["version"] + 1)})
    assert r.status_code == 403


async def test_notification_isolation(client, admindb):
    """Unconnected lab cannot see another org's inbox entries."""
    rx = await _submitted_rx(client)
    await login(client, LAB_ADMIN)
    n = (await client.post("/v1/notifications", json={
        "rx_id": rx["id"], "kind": "info", "subject": "iso"})).json()
    # ensure a user on the unaddressed lab LB exists
    from app.modules.iam.models import (Membership, Organization, UserAccount)
    from app.security import hash_password
    from sqlalchemy import select
    lb = (await admindb.execute(select(Organization).where(
        Organization.name.like("Unconnected%")))).scalar_one()
    u = (await admindb.execute(select(UserAccount).where(
        UserAccount.email == "lab2@lb.dev"))).scalar_one_or_none()
    if not u:
        u = UserAccount(email="lab2@lb.dev", display_name="LB Tech",
                        password_hash=hash_password("Passw0rd!dev"))
        admindb.add(u)
        await admindb.flush()
    if not (await admindb.execute(select(Membership).where(
            Membership.user_id == u.id,
            Membership.org_id == lb.id))).scalar_one_or_none():
        admindb.add(Membership(tenant_id=lb.tenant_id, org_id=lb.id,
                               user_id=u.id, role="lab_technician",
                               status="active"))
    await admindb.commit()
    await login(client, "lab2@lb.dev", "Passw0rd!dev")
    r = await client.post(f"/v1/notifications/{n['id']}/read")
    assert r.status_code == 403
    inbox = (await client.get("/v1/notifications")).json()
    assert not any(x["id"] == n["id"] for x in inbox["items"])


async def test_comment_anchored_to_attachment(client, s3ok):
    """COM-001 gap: comment can reference a live file_reference."""
    rx = await _submitted_rx(client)
    # upload real STL and attach (presigned PUT hits the real S3 endpoint)
    import hashlib
    import httpx
    stl = (b"solid t\nfacet normal 0 0 0\nouter loop\nvertex 0 0 0\n"
           b"vertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid t\n")
    h = hashlib.sha256(stl).hexdigest()
    up = (await client.post("/v1/uploads", json={
        "sha256": h, "bytes": len(stl), "kind": "stl", "jaw": "upper"})).json()
    assert "id" in up, up
    async with httpx.AsyncClient(timeout=30) as raw:
        pr = await raw.put(up["upload_urls"][0], content=stl)
        assert pr.status_code == 200, pr.text
    comp = (await client.post(f"/v1/uploads/{up['id']}/complete",
                              json={"sha256": h})).json()
    assert "id" in comp, comp
    ref = (await client.post(f"/v1/rx/{rx['id']}/attachments",
                             json={"asset_id": comp["id"], "role": "original"})
           ).json()
    r = await client.post(f"/v1/rx/{rx['id']}/comments", json={
        "body": "see attached scan", "file_reference_id": ref["id"]})
    assert r.status_code == 201, r.text
    assert r.json()["file_reference_id"] == ref["id"]
    # invalid ref -> 422
    r = await client.post(f"/v1/rx/{rx['id']}/comments", json={
        "body": "bad", "file_reference_id": str(uuid.uuid4())})
    assert r.status_code == 422
