"""S1a-01/02: patient CRUD, search, duplicate detection, soft delete,
org/tenant isolation, case lifecycle — synthetic data only."""
import uuid

import pytest
from sqlalchemy import select, text

from app.modules.clinical.models import Patient
from tests.conftest import login

pytestmark = pytest.mark.asyncio


async def _create(client, **kw):
    # unique default surname so unrelated tests never collide on the
    # last_name+dob duplicate rule
    body = {"first_name": "Max", "last_name": f"Mu{uuid.uuid4().hex[:8]}",
            "dob": "2011-03-04", **kw}
    r = await client.post("/v1/patients", json=body)
    return r


async def test_patient_crud_and_versioning(client):
    await login(client, "staff@pa.dev")  # patient:write, not delete
    r = await _create(client, external_ref=f"EXT-{uuid.uuid4().hex[:6]}")
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["patient_number"].startswith("P")
    assert p["version"] == 1

    r = await client.get(f"/v1/patients/{p['id']}")
    assert r.status_code == 200 and r.json()["last_name"] == p["last_name"]

    r = await client.patch(f"/v1/patients/{p['id']}",
                           json={"notes": "updated"},
                           headers={"If-Match": "1"})
    assert r.status_code == 200 and r.json()["version"] == 2
    # stale version -> 409
    r = await client.patch(f"/v1/patients/{p['id']}",
                           json={"notes": "stale"},
                           headers={"If-Match": "1"})
    assert r.status_code == 409


async def test_patient_search_filters(client):
    await login(client, "staff@pa.dev")
    tag = uuid.uuid4().hex[:6]
    await _create(client, first_name="Zephyr", last_name=f"Quill{tag}",
                  external_ref=f"Q{tag}")
    r = await client.get(f"/v1/patients?q=zephyr")
    assert any(p["last_name"] == f"Quill{tag}" for p in r.json()["items"])
    r = await client.get(f"/v1/patients?external_ref=Q{tag}")
    assert len(r.json()["items"]) == 1
    r = await client.get("/v1/patients?q=zz-no-such-name")
    assert r.json()["items"] == []


async def test_duplicate_detection_and_confirm(client):
    await login(client, "staff@pa.dev")
    tag = uuid.uuid4().hex[:6]
    r = await _create(client, last_name=f"Dupe{tag}", dob="2009-01-01")
    assert r.status_code == 201
    # same last name + dob -> 409 with candidates
    r = await _create(client, last_name=f"dupe{tag}", dob="2009-01-01")
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "possible_duplicate"
    assert detail["candidates"], "candidate list required"
    # explicit confirmation creates anyway
    r = await _create(client, last_name=f"Dupe{tag}", dob="2009-01-01",
                      confirm_duplicate=True)
    assert r.status_code == 201


async def test_soft_delete_requires_admin_and_hides(client):
    await login(client, "staff@pa.dev")
    r = await _create(client)
    pid = r.json()["id"]
    # staff lacks patient:delete
    assert (await client.delete(f"/v1/patients/{pid}")).status_code == 403
    await login(client, "admin@pa.dev")
    assert (await client.delete(f"/v1/patients/{pid}")).status_code == 204
    # deleted patient invisible
    assert (await client.get(f"/v1/patients/{pid}")).status_code == 403
    r = await client.get("/v1/patients?q=Mustermann")
    assert all(p["id"] != pid for p in r.json()["items"])


async def test_lab_and_foreign_org_cannot_read_patients(client, admindb):
    await login(client, "staff@pa.dev")
    r = await _create(client)
    pid = r.json()["id"]

    await login(client, "admin@la.dev")
    # lab_admin holds no patient:* perms at all
    assert (await client.get("/v1/patients")).status_code == 403
    assert (await client.get(f"/v1/patients/{pid}")).status_code == 403

    # a second practice org in the same tenant also cannot see PA's patient
    suffix = uuid.uuid4().hex[:6]
    from app.modules.iam.models import Membership, Organization, UserAccount
    from app.security import hash_password
    pa_org = (await admindb.execute(text(
        "SELECT id, tenant_id FROM organization WHERE name LIKE 'Smile Ortho%'"))
        ).mappings().one()
    org2 = Organization(tenant_id=pa_org["tenant_id"], kind="practice",
                        name=f"Other Clinic {suffix}")
    admindb.add(org2)
    await admindb.flush()
    u = UserAccount(email=f"other-{suffix}@easyrs.dev", display_name="Other",
                    password_hash=hash_password("Passw0rd!dev"))
    admindb.add(u)
    await admindb.flush()
    admindb.add(Membership(tenant_id=pa_org["tenant_id"], org_id=org2.id,
                           user_id=u.id, role="practice_admin", status="active"))
    await admindb.commit()

    await login(client, u.email)
    assert (await client.get(f"/v1/patients/{pid}")).status_code == 403
    r = await client.get("/v1/patients?q=Mustermann")
    assert all(p["id"] != pid for p in r.json()["items"])


async def test_cases_lifecycle_and_isolation(client, admindb):
    await login(client, "staff@pa.dev")
    r = await _create(client, first_name="Casey")
    pid = r.json()["id"]

    r = await client.post(f"/v1/patients/{pid}/cases", json={
        "label": "Phase 1 (synthetic)"})
    assert r.status_code == 201, r.text
    case = r.json()
    assert case["stage"] == "active" and case["patient_id"] == pid

    r = await client.get(f"/v1/patients/{pid}/cases")
    assert len(r.json()["items"]) == 1

    # cross-org: lab user cannot create/list cases on PA's patient
    await login(client, "admin@la.dev")
    assert (await client.get(f"/v1/patients/{pid}/cases")).status_code == 403
    assert (await client.post(f"/v1/patients/{pid}/cases",
                              json={"label": "x"})).status_code == 403


async def test_seeded_patient_visible(client):
    await login(client, "doctor@pa.dev")
    r = await client.get("/v1/patients?external_ref=SYN-0001")
    assert r.status_code == 200 and len(r.json()["items"]) == 1
    p = r.json()["items"][0]
    assert p["first_name"] == "Ava" and p["last_name"] == "Synthetic"


# ---------------- PAT-009: in-flight Rx delete guard -------------------------
async def _rx_for_patient(client, pid: str) -> dict:
    """Practice creates a draft Rx for the given patient."""
    me = (await client.get("/v1/auth/me")).json()
    conns = (await client.get(
        f"/v1/org-connections?org_id={me['org_id']}")).json()["items"]
    lab = [c for c in conns if c["status"] == "accepted"][0]["lab_org_id"]
    r = await client.post("/v1/rx", json={"patient_id": pid,
                                          "lab_org_id": lab})
    assert r.status_code == 201, r.text
    return r.json()


async def _submit_rx(client, rx: dict) -> dict:
    cat = (await client.get("/v1/catalog/parts")).json()["items"][0]["id"]
    r = await client.put(f"/v1/rx/{rx['id']}/items",
                         json={"items": [{"appliance_id": cat,
                                          "arch": "upper"}]},
                         headers={"If-Match": str(rx["version"])})
    assert r.status_code == 200, r.text
    rx = (await client.get(f"/v1/rx/{rx['id']}")).json()
    r = await client.post(f"/v1/rx/{rx['id']}/submit", json={
        "signature_name": "Dr. Demo", "confirm_submit": True},
        headers={"Idempotency-Key": uuid.uuid4().hex,
                 "If-Match": str(rx["version"])})
    assert r.status_code == 200, r.text
    return (await client.get(f"/v1/rx/{rx['id']}")).json()


async def test_delete_blocked_by_inflight_rx(client):
    """PAT-009: draft / submitted Rx block patient deletion."""
    await login(client, "staff@pa.dev")
    pid = (await _create(client)).json()["id"]
    rx = await _rx_for_patient(client, pid)

    await login(client, "admin@pa.dev")
    r = await client.delete(f"/v1/patients/{pid}")
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "patient_has_inflight_rx"
    assert r.json()["detail"]["inflight_rx"][0]["id"] == rx["id"]

    # submitted stays in-flight too
    await login(client, "doctor@pa.dev")
    rx = await _submit_rx(client, rx)
    await login(client, "admin@pa.dev")
    r = await client.delete(f"/v1/patients/{pid}")
    assert r.status_code == 409
    # patient NOT deleted, still readable
    assert (await client.get(f"/v1/patients/{pid}")).status_code == 200


async def test_delete_allowed_without_rx(client):
    await login(client, "staff@pa.dev")
    pid = (await _create(client)).json()["id"]
    await login(client, "admin@pa.dev")
    assert (await client.delete(f"/v1/patients/{pid}")).status_code == 204


async def test_delete_completed_but_inflight_fulfillment_blocked(client):
    """completed Rx still in the delivery pipeline (qc_pending..received)
    counts as in-flight — the goods are literally in transit."""
    await login(client, "doctor@pa.dev")
    pid = (await _create(client)).json()["id"]
    rx = await _rx_for_patient(client, pid)
    rx = await _submit_rx(client, rx)

    await login(client, "tech@la.dev")
    r = await client.post(f"/v1/rx/{rx['id']}/check-in", json={},
                          headers={"If-Match": str(rx["version"])})
    assert r.status_code == 200, r.text
    rx = (await client.get(f"/v1/rx/{rx['id']}")).json()
    r = await client.post(f"/v1/rx/{rx['id']}/complete", json={},
                          headers={"If-Match": str(rx["version"])})
    assert r.status_code == 200, r.text

    await login(client, "admin@pa.dev")
    # completed but qc_pending -> still in-flight
    r = await client.delete(f"/v1/patients/{pid}")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "patient_has_inflight_rx"


async def test_delete_allowed_after_delivered(client):
    """Terminal loop: completed + delivered (and cancelled) release the
    patient; signature/approval history rows are untouched."""
    await login(client, "doctor@pa.dev")
    pid = (await _create(client)).json()["id"]
    rx = await _rx_for_patient(client, pid)
    rx = await _submit_rx(client, rx)

    await login(client, "tech@la.dev")
    for op, body in (("check-in", {}), ("complete", {}),
                     ("qc", {"result": "pass", "note": "ok"}),
                     ("ship", {"carrier": "UPS", "tracking_number": "1Z999"})):
        rx = (await client.get(f"/v1/rx/{rx['id']}")).json()
        r = await client.post(f"/v1/rx/{rx['id']}/{op}", json=body,
                              headers={"If-Match": str(rx["version"])})
        assert r.status_code in (200, 201), (op, r.text)

    await login(client, "doctor@pa.dev")
    for op in ("receive", "deliver"):
        rx = (await client.get(f"/v1/rx/{rx['id']}")).json()
        r = await client.post(f"/v1/rx/{rx['id']}/{op}", json={},
                              headers={"If-Match": str(rx["version"])})
        assert r.status_code == 200, (op, r.text)

    await login(client, "admin@pa.dev")
    r = await client.delete(f"/v1/patients/{pid}")
    assert r.status_code == 204, r.text
    # Rx row + signature survive the soft delete (history not destroyed)
    await login(client, "doctor@pa.dev")
    got = (await client.get(f"/v1/rx/{rx['id']}")).json()
    assert got["signature_name"] == "Dr. Demo"
    assert got["fulfillment_status"] == "delivered"


async def test_delete_blocked_for_lab_admin(client):
    """Lab admin holds no patient:delete at all — 403 not 409."""
    await login(client, "staff@pa.dev")
    pid = (await _create(client)).json()["id"]
    await login(client, "admin@la.dev")
    assert (await client.delete(f"/v1/patients/{pid}")).status_code == 403
