"""S1b.1 targeted fixes — signature gate, If-Match enforcement, real ZIP
delivery, two-phase check-in, idempotent snapshots, real concurrency."""
import asyncio
import hashlib
import io
import json
import uuid
import zipfile

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from tests.conftest import login

pytestmark = pytest.mark.asyncio

STAFF = "staff@pa.dev"
LAB_ADMIN = "admin@la.dev"
LAB_TECH = "tech@la.dev"

STL = b"""solid b1
facet normal 0 0 0
  outer loop
    vertex 0 0 0
    vertex 1 0 0
    vertex 0 1 0
  endloop
endfacet
endsolid b1
"""


@pytest_asyncio.fixture
async def s3ok(_database):
    import os
    from app.config import get_settings
    from app.storage import s3
    s = get_settings()
    try:
        await asyncio.to_thread(s3().head_bucket, Bucket=s.s3_bucket)
    except Exception:
        try:
            await asyncio.to_thread(s3().create_bucket, Bucket=s.s3_bucket)
        except Exception as e:
            if os.environ.get("REQUIRE_S3"):
                raise AssertionError(f"S3 required but unavailable: {e}")
            pytest.skip(f"S3 store unavailable: {e}")
    return s.s3_bucket


async def _patient_id(client) -> str:
    r = await client.get("/v1/patients?external_ref=SYN-0001")
    return r.json()["items"][0]["id"]


async def _lab_org_id(client) -> str:
    me = (await client.get("/v1/auth/me")).json()
    r = await client.get(f"/v1/org-connections?org_id={me['org_id']}")
    return [c for c in r.json()["items"] if c["status"] == "accepted"][0][
        "lab_org_id"]


async def _catalog_id(client, code: str) -> str:
    for kind in ("parts", "appliances"):
        items = (await client.get(f"/v1/catalog/{kind}")).json()["items"]
        hit = [i for i in items if i["code"] == code]
        if hit:
            return hit[0]["id"]
    raise AssertionError(code)


async def _submitted_rx(client) -> dict:
    """Fresh submitted Rx with one appliance item."""
    body = {"patient_id": await _patient_id(client),
            "lab_org_id": await _lab_org_id(client)}
    rx = (await client.post("/v1/rx", json=body)).json()
    app_id = await _catalog_id(client, "HWL")
    r = await client.put(f"/v1/rx/{rx['id']}/items",
                         json={"items": [{"appliance_id": app_id,
                                          "arch": "upper"}]},
                         headers={"If-Match": str(rx["version"])})
    assert r.status_code == 200, r.text
    rx = (await client.get(f"/v1/rx/{rx['id']}")).json()
    r = await client.post(
        f"/v1/rx/{rx['id']}/submit",
        json={"signature_name": "Dr. Demo", "confirm_submit": True},
        headers={"Idempotency-Key": uuid.uuid4().hex,
                 "If-Match": str(rx["version"])})
    assert r.status_code == 200, r.text
    return r.json()


async def _upload_stl(client, content: bytes) -> dict:
    sha = hashlib.sha256(content).hexdigest()
    sess = (await client.post("/v1/uploads", json={
        "sha256": sha, "bytes": len(content), "kind": "stl",
        "jaw": "upper"})).json()
    put = await httpx.AsyncClient().put(sess["upload_urls"][0],
                                        content=content)
    assert put.status_code == 200
    return (await client.post(f"/v1/uploads/{sess['id']}/complete",
                              json={"sha256": sha})).json()


# ---------------- S1b1-03 signature gate ---------------------------------------
async def test_submit_requires_signature(client):
    await login(client, STAFF)
    rx = (await client.post("/v1/rx", json={
        "patient_id": await _patient_id(client),
        "lab_org_id": await _lab_org_id(client)})).json()
    app_id = await _catalog_id(client, "HWL")
    await client.put(f"/v1/rx/{rx['id']}/items",
                     json={"items": [{"appliance_id": app_id,
                                      "arch": "upper"}]},
                     headers={"If-Match": str(rx["version"])})
    rx = (await client.get(f"/v1/rx/{rx['id']}")).json()

    for payload, code in [
        ({"signature_name": "", "confirm_submit": True}, None),       # pydantic
        ({"signature_name": "   ", "confirm_submit": True},
         "signature_required"),
        ({"signature_name": "Dr. D", "confirm_submit": False},
         "confirmation_required"),
        ({"confirm_submit": True}, None),                              # missing
    ]:
        r = await client.post(
            f"/v1/rx/{rx['id']}/submit", json=payload,
            headers={"Idempotency-Key": uuid.uuid4().hex,
                     "If-Match": str(rx["version"])})
        assert r.status_code == 422, (payload, r.status_code)
        if code:
            assert r.json()["detail"]["code"] == code
    # rejected submits leave no transition events at all
    tr = (await client.get(f"/v1/rx/{rx['id']}/transitions")).json()["items"]
    assert len(tr) == 1 and tr[0]["to_status"] == "draft"
    assert (await client.get(
        f"/v1/rx/{rx['id']}")).json()["status"] == "draft"


async def test_signature_recorded_server_side(client):
    await login(client, STAFF)
    rx = await _submitted_rx(client)
    assert rx["signature_name"] == "Dr. Demo"
    assert rx["submitted_at"]


# ---------------- S1b1-04 If-Match required ------------------------------------
async def test_mutations_require_if_match(client):
    await login(client, STAFF)
    rx = (await client.post("/v1/rx", json={
        "patient_id": await _patient_id(client),
        "lab_org_id": await _lab_org_id(client)})).json()
    r = await client.patch(f"/v1/rx/{rx['id']}", json={"notes": "x"})
    assert r.status_code == 428
    r = await client.put(f"/v1/rx/{rx['id']}/items",
                         json={"items": []})
    assert r.status_code == 428
    rx = await _submitted_rx(client)
    r = await client.post(f"/v1/rx/{rx['id']}/unsubmit", json={})
    assert r.status_code == 428
    r = await client.post(
        f"/v1/rx/{rx['id']}/submit",
        json={"signature_name": "D", "confirm_submit": True},
        headers={"Idempotency-Key": uuid.uuid4().hex})
    assert r.status_code == 428
    await login(client, LAB_TECH)
    r = await client.post(f"/v1/rx/{rx['id']}/check-in", json={})
    assert r.status_code == 428


async def test_idempotent_replay_returns_first_snapshot(client):
    """Replay after a later state change returns the ORIGINAL response —
    never a forged 'latest' state."""
    await login(client, STAFF)
    rx = (await client.post("/v1/rx", json={
        "patient_id": await _patient_id(client),
        "lab_org_id": await _lab_org_id(client)})).json()
    app_id = await _catalog_id(client, "HWL")
    await client.put(f"/v1/rx/{rx['id']}/items",
                     json={"items": [{"appliance_id": app_id,
                                      "arch": "upper"}]},
                     headers={"If-Match": str(rx["version"])})
    rx = (await client.get(f"/v1/rx/{rx['id']}")).json()
    key = uuid.uuid4().hex
    payload = {"signature_name": "Dr. Demo", "confirm_submit": True}
    r1 = await client.post(f"/v1/rx/{rx['id']}/submit", json=payload,
                           headers={"Idempotency-Key": key,
                                    "If-Match": str(rx["version"])})
    assert r1.status_code == 200
    submitted = r1.json()

    # state moves on: practice pulls back to draft
    cur = (await client.get(f"/v1/rx/{rx['id']}")).json()
    assert (await client.post(
        f"/v1/rx/{rx['id']}/unsubmit", json={},
        headers={"If-Match": str(cur["version"])})).status_code == 200

    # byte-identical replay (same body + same If-Match) returns the FIRST
    # response snapshot — never a forged 'latest' state
    r2 = await client.post(f"/v1/rx/{rx['id']}/submit", json=payload,
                           headers={"Idempotency-Key": key,
                                    "If-Match": str(rx["version"])})
    assert r2.status_code == 200
    assert r2.json()["status"] == "submitted"
    assert r2.json()["version"] == submitted["version"]
    # same key + different request -> 409
    r3 = await client.post(f"/v1/rx/{rx['id']}/submit", json=payload,
                           headers={"Idempotency-Key": key,
                                    "If-Match": str(cur["version"])})
    assert r3.status_code == 409
    # and the real row is untouched (still draft)
    assert (await client.get(
        f"/v1/rx/{rx['id']}")).json()["status"] == "draft"


async def test_concurrent_checkin_vs_unsubmit_exactly_one_wins(client):
    await login(client, STAFF)
    rx = await _submitted_rx(client)
    ver = str(rx["version"])

    await login(client, LAB_TECH)
    async def lab_checkin():
        return await client.post(f"/v1/rx/{rx['id']}/check-in", json={},
                                 headers={"If-Match": ver})

    async def practice_unsubmit():
        from app.main import app
        async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
                headers={"X-Requested-With": "XMLHttpRequest"}) as c2:
            await login(c2, STAFF)
            return await c2.post(f"/v1/rx/{rx['id']}/unsubmit", json={},
                                 headers={"If-Match": ver})

    r_check, r_unsub = await asyncio.gather(lab_checkin(),
                                          practice_unsubmit())
    outcomes = sorted([r_check.status_code, r_unsub.status_code])
    assert outcomes[0] == 200, (r_check.status_code, r_unsub.status_code,
                                r_check.text, r_unsub.text)
    assert outcomes[1] in (409, 422)
    final = (await client.get(f"/v1/rx/{rx['id']}")).json()
    assert final["status"] in ("checked_in", "draft")


async def test_concurrent_double_submit_exactly_one_wins(client):
    await login(client, STAFF)
    rx = (await client.post("/v1/rx", json={
        "patient_id": await _patient_id(client),
        "lab_org_id": await _lab_org_id(client)})).json()
    app_id = await _catalog_id(client, "HWL")
    await client.put(f"/v1/rx/{rx['id']}/items",
                     json={"items": [{"appliance_id": app_id,
                                      "arch": "upper"}]},
                     headers={"If-Match": str(rx["version"])})
    rx = (await client.get(f"/v1/rx/{rx['id']}")).json()
    payload = {"signature_name": "Dr. Demo", "confirm_submit": True}
    r1, r2 = await asyncio.gather(*[
        client.post(f"/v1/rx/{rx['id']}/submit", json=payload,
                    headers={"Idempotency-Key": uuid.uuid4().hex,
                             "If-Match": str(rx["version"])})
        for _ in range(2)])
    assert sorted([r1.status_code, r2.status_code]) in ([200, 409], [200, 422])


# ---------------- S1b1-01/02 real bundle ----------------------------------------
async def test_bundle_contains_real_files_and_checks_in(client, s3ok):
    await login(client, STAFF)
    asset = await _upload_stl(client, STL)
    rx = await _submitted_rx(client)
    r = await client.post(f"/v1/rx/{rx['id']}/attachments",
                          json={"asset_id": asset["id"], "role": "original"})
    assert r.status_code == 201, r.text

    # GET bundle list is pure read — no transition
    r = await client.get(f"/v1/rx/{rx['id']}/bundle")
    assert r.status_code == 200 and r.json()["items"] == []
    assert (await client.get(
        f"/v1/rx/{rx['id']}")).json()["status"] == "submitted"

    await login(client, LAB_TECH)
    # lab GET preview also read-only
    assert (await client.get(f"/v1/rx/{rx['id']}")).json()[
        "status"] == "submitted"

    r = await client.post(f"/v1/rx/{rx['id']}/bundle-download")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["download_url"].startswith("http")
    z = await httpx.AsyncClient().get(body["download_url"])
    assert z.status_code == 200
    assert hashlib.sha256(z.content).hexdigest() == body["bundle"]["sha256"]

    zf = zipfile.ZipFile(io.BytesIO(z.content))
    names = set(zf.namelist())
    assert {"prescription.pdf", "manifest.json"} <= names
    assert zf.read("prescription.pdf").startswith(b"%PDF")
    manifest = json.loads(zf.read("manifest.json"))
    entry = manifest["files"][0]
    assert entry["sha256"] == hashlib.sha256(STL).hexdigest()
    stl_name = [n for n in names if n.startswith("attachments/")][0]
    assert ".." not in stl_name and not stl_name.startswith("/")
    assert zf.read(stl_name) == STL  # byte-identical STL in the ZIP

    # lab-side acceptance performed check-in — via download, once
    detail = (await client.get(f"/v1/rx/{rx['id']}")).json()
    assert detail["status"] == "checked_in"
    assert detail["checked_in_via"] == "download"
    tr = (await client.get(f"/v1/rx/{rx['id']}/transitions")).json()["items"]
    assert sum(1 for t in tr if t["to_status"] == "checked_in") == 1

    # repeat download reuses the same package — no second transition
    r2 = await client.post(f"/v1/rx/{rx['id']}/bundle-download")
    assert r2.status_code == 200
    assert r2.json()["bundle"]["id"] == body["bundle"]["id"]
    tr = (await client.get(f"/v1/rx/{rx['id']}/transitions")).json()["items"]
    assert sum(1 for t in tr if t["to_status"] == "checked_in") == 1


async def test_practice_bundle_download_never_checks_in(client, s3ok):
    await login(client, STAFF)
    rx = await _submitted_rx(client)
    r = await client.post(f"/v1/rx/{rx['id']}/bundle-download")
    assert r.status_code == 200, r.text
    assert (await client.get(
        f"/v1/rx/{rx['id']}")).json()["status"] == "submitted"


async def test_bundle_missing_object_aborts_without_checkin(client, s3ok):
    """A referenced object that vanished from storage must fail the build
    AND leave the Rx submitted — never half-delivered."""
    await login(client, STAFF)
    asset = await _upload_stl(client, STL + b"tag")
    rx = await _submitted_rx(client)
    r = await client.post(f"/v1/rx/{rx['id']}/attachments",
                          json={"asset_id": asset["id"], "role": "original"})
    assert r.status_code == 201
    # object disappears after authorization
    from app.config import get_settings
    from app.storage import s3
    me = (await client.get("/v1/auth/me")).json()
    key = f"assets/{me['tenant_id']}/{me['org_id']}/{asset['sha256']}"
    await asyncio.to_thread(s3().delete_object,
                            Bucket=get_settings().s3_bucket, Key=key)
    await login(client, LAB_TECH)
    r = await client.post(f"/v1/rx/{rx['id']}/bundle-download")
    assert r.status_code == 502, r.text
    assert (await client.get(
        f"/v1/rx/{rx['id']}")).json()["status"] == "submitted"


async def test_unauthorized_lab_cannot_bundle(client, s3ok, admindb):
    await login(client, STAFF)
    rx = await _submitted_rx(client)
    await login(client, LAB_ADMIN)  # LA IS addressed — control case
    assert (await client.post(
        f"/v1/rx/{rx['id']}/bundle-download")).status_code == 200

    # ensure a user on the UNADDRESSED lab (LB) exists
    from app.modules.iam.models import (Membership, Organization, UserAccount)
    from app.security import hash_password
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
    assert (await client.get(f"/v1/rx/{rx['id']}")).status_code == 403
    assert (await client.post(
        f"/v1/rx/{rx['id']}/bundle-download")).status_code == 403
