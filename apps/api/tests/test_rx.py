"""S1b-Core Rx lifecycle tests — real Postgres, synthetic data.

Loop under test: create(draft) -> items -> submit -> lab inbox/check-in ->
unsubmit blocked. Plus download-triggers-check-in (SRC03), idempotent submit,
required part options (2023 rule), visibility/isolation, comments, attach.
"""
import io
import uuid
import zipfile

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from tests.conftest import login

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def s3ok(_database):
    """Same gate as test_assets.s3ok — real S3 or skip (REQUIRE_S3 fails)."""
    import asyncio
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

ADMIN = "admin@pa.dev"
DOCTOR = "doctor@pa.dev"
STAFF = "staff@pa.dev"
LAB_ADMIN = "admin@la.dev"
LAB_TECH = "tech@la.dev"


async def _patient_id(client) -> str:
    r = await client.get("/v1/patients?external_ref=SYN-0001")
    assert r.status_code == 200 and r.json()["items"], r.text
    return r.json()["items"][0]["id"]


async def _lab_org_id(client) -> str:
    me = (await client.get("/v1/auth/me")).json()
    r = await client.get(f"/v1/org-connections?org_id={me['org_id']}")
    conn = [c for c in r.json()["items"] if c["status"] == "accepted"][0]
    return conn["lab_org_id"]


async def _catalog_id(client, code: str) -> str:
    for kind in ("parts", "appliances"):
        r = await client.get(f"/v1/catalog/{kind}")
        assert r.status_code == 200, r.text
        hit = [i for i in r.json()["items"] if i["code"] == code]
        if hit:
            return hit[0]["id"]
    raise AssertionError(f"catalog code {code} not found")


async def _draft(client, **kw) -> dict:
    body = {"patient_id": await _patient_id(client),
            "lab_org_id": await _lab_org_id(client), **kw}
    r = await client.post("/v1/rx", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def _add_item(client, rx: dict, code: str = "HWL", **extra) -> dict:
    body = {"items": [{"appliance_id": await _catalog_id(client, code),
                       "arch": "upper", **extra}]}
    r = await client.put(f"/v1/rx/{rx['id']}/items", json=body,
                         headers={"If-Match": str(rx["version"])})
    assert r.status_code == 200, r.text
    return (await client.get(f"/v1/rx/{rx['id']}")).json()


async def _submit(client, rx: dict, key: str | None = None):
    return await client.post(
        f"/v1/rx/{rx['id']}/submit",
        json={"note": "for lab", "signature_name": "Dr. Demo",
              "confirm_submit": True},
        headers={"Idempotency-Key": key or uuid.uuid4().hex,
                 "If-Match": str(rx["version"])})


# ---------------- happy path + core loop --------------------------------------
async def test_full_loop_submit_checkin_unsubmit_blocked(client):
    await login(client, DOCTOR)
    rx = await _draft(client, due_date="2030-01-15", notes="synthetic rx")
    assert rx["status"] == "draft" and rx["rx_number"].startswith("RX")

    rx = await _add_item(client, rx)
    assert rx["items"][0]["arch"] == "upper"

    r = await _submit(client, rx)
    assert r.status_code == 200, r.text
    rx = r.json()
    assert rx["status"] == "submitted" and rx["submitted_at"]
    assert rx["signature_name"] == "Dr. Demo"

    # editing is closed once submitted
    r = await client.patch(f"/v1/rx/{rx['id']}", json={"notes": "late"},
                           headers={"If-Match": str(rx["version"])})
    assert r.status_code == 422

    # lab inbox sees it, tech checks in
    await login(client, LAB_TECH)
    inbox = (await client.get("/v1/rx?status=submitted")).json()
    assert rx["id"] in [i["id"] for i in inbox["items"]]
    cur = (await client.get(f"/v1/rx/{rx['id']}")).json()
    r = await client.post(f"/v1/rx/{rx['id']}/check-in",
                          json={"note": "received"},
                          headers={"If-Match": str(cur["version"])})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "checked_in"
    assert r.json()["checked_in_via"] == "button"
    # idempotent repeat — no second event
    assert (await client.post(
        f"/v1/rx/{rx['id']}/check-in", json={})).status_code == 200

    # practice can read, but unsubmit is now forbidden (CONFIRMED rule)
    await login(client, DOCTOR)
    r = await client.post(f"/v1/rx/{rx['id']}/unsubmit", json={},
                          headers={"If-Match": str(rx["version"] + 1)})
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "already_checked_in"

    # transition trail is auditable and complete
    tr = (await client.get(f"/v1/rx/{rx['id']}/transitions")).json()["items"]
    assert [(t["from_status"], t["to_status"]) for t in tr] == [
        (None, "draft"), ("draft", "submitted"),
        ("submitted", "checked_in")]


async def test_unsubmit_before_checkin_returns_to_draft(client):
    await login(client, STAFF)
    rx = await _add_item(client, await _draft(client))
    rx = (await _submit(client, rx)).json()
    r = await client.post(f"/v1/rx/{rx['id']}/unsubmit",
                          json={"reason": "wrong lab"},
                          headers={"If-Match": str(rx["version"])})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "draft"
    # editable again
    rx = r.json()
    r = await client.patch(f"/v1/rx/{rx['id']}", json={"notes": "re-edited"},
                           headers={"If-Match": str(rx["version"])})
    assert r.status_code == 200


async def test_lab_bundle_download_checks_in(client, s3ok):
    await login(client, STAFF)
    rx = await _add_item(client, await _draft(client))
    rx = (await _submit(client, rx)).json()

    await login(client, LAB_ADMIN)
    r = await client.post(f"/v1/rx/{rx['id']}/bundle-download")
    assert r.status_code == 200, r.text
    import httpx
    z = await httpx.AsyncClient().get(r.json()["download_url"])
    assert z.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(z.content))
    assert {"prescription.pdf", "manifest.json"} <= set(zf.namelist())

    detail = (await client.get(f"/v1/rx/{rx['id']}")).json()
    assert detail["status"] == "checked_in"
    assert detail["checked_in_via"] == "download"
    tr = (await client.get(f"/v1/rx/{rx['id']}/transitions")).json()["items"]
    assert tr[-1]["via"] == "download"


async def test_practice_bundle_download_does_not_check_in(client, s3ok):
    await login(client, STAFF)
    rx = await _add_item(client, await _draft(client))
    rx = (await _submit(client, rx)).json()
    # practice downloads own bundle — no transition
    r = await client.post(f"/v1/rx/{rx['id']}/bundle-download")
    assert r.status_code == 200
    assert (await client.get(f"/v1/rx/{rx['id']}")).json()["status"] == "submitted"
    # and may still unsubmit
    cur = (await client.get(f"/v1/rx/{rx['id']}")).json()
    assert (await client.post(
        f"/v1/rx/{rx['id']}/unsubmit", json={},
        headers={"If-Match": str(cur["version"])})).status_code == 200


# ---------------- guards -------------------------------------------------------
async def test_submit_requires_accepted_connection(client):
    await login(client, STAFF)
    # LB (unconnected lab): find its org id via admin list
    r = await client.get("/v1/orgs")
    lb = [o for o in r.json()["items"] if "Unconnected" in o["name"]][0]
    rx = await _draft(client, lab_org_id=lb["id"])
    rx = await _add_item(client, rx)
    r = await _submit(client, rx)
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == "no_accepted_connection"


async def test_submit_requires_lab_and_items(client):
    await login(client, STAFF)
    rx = await _draft(client, lab_org_id=None)  # universal-library style
    r = await client.post(
        f"/v1/rx/{rx['id']}/submit",
        json={"signature_name": "Dr. D", "confirm_submit": True},
        headers={"Idempotency-Key": uuid.uuid4().hex,
                 "If-Match": str(rx["version"])})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "no_lab_selected"

    rx = await _draft(client)  # has lab but no items
    r = await _submit(client, rx)
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "validation_failed"


async def test_submit_idempotency(client):
    await login(client, STAFF)
    rx = await _add_item(client, await _draft(client))
    key = uuid.uuid4().hex
    r1 = await _submit(client, rx, key)
    assert r1.status_code == 200
    # replay: same key + same payload -> same result, no error
    r2 = await _submit(client, rx, key)
    assert r2.status_code == 200 and r2.json()["id"] == rx["id"]
    # same key + different payload -> 409
    r3 = await client.post(
        f"/v1/rx/{rx['id']}/submit",
        json={"note": "different", "signature_name": "Dr. Demo",
              "confirm_submit": True},
        headers={"Idempotency-Key": key, "If-Match": str(rx["version"])})
    assert r3.status_code == 409
    # missing key -> 422
    assert (await client.post(
        f"/v1/rx/{rx['id']}/submit",
        json={"signature_name": "Dr. D", "confirm_submit": True},
        headers={"If-Match": str(rx["version"])})).status_code == 422


async def test_required_part_option_enforced(client):
    """2023 evidence: band options can be required before submit."""
    await login(client, STAFF)
    rx = await _draft(client)
    band = await _catalog_id(client, "BND")
    r = await client.put(f"/v1/rx/{rx['id']}/items", json={
        "items": [{"appliance_id": band, "arch": "upper"}]},
        headers={"If-Match": str(rx["version"])})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "required_option_missing"
    rx = (await client.get(f"/v1/rx/{rx['id']}")).json()
    r = await client.put(f"/v1/rx/{rx['id']}/items", json={
        "items": [{"appliance_id": band, "arch": "upper",
                   "options": {"band_tooth": "16"}}]},
        headers={"If-Match": str(rx["version"])})
    assert r.status_code == 200, r.text


async def test_draft_invisible_to_lab(client):
    await login(client, STAFF)
    rx = await _draft(client)
    await login(client, LAB_ADMIN)
    assert (await client.get(f"/v1/rx/{rx['id']}")).status_code == 403
    inbox = (await client.get("/v1/rx")).json()
    assert rx["id"] not in [i["id"] for i in inbox["items"]]


async def test_lab_cannot_issue_or_practice_actions(client):
    await login(client, LAB_ADMIN)
    # labs cannot create Rxs
    assert (await client.post(
        "/v1/rx", json={"patient_id": str(uuid.uuid4())})).status_code in (403,)
    # lab cannot unsubmit or edit a received rx
    await login(client, STAFF)
    rx = await _add_item(client, await _draft(client))
    rx = (await _submit(client, rx)).json()
    await login(client, LAB_ADMIN)
    assert (await client.post(
        f"/v1/rx/{rx['id']}/unsubmit", json={},
        headers={"If-Match": "1"})).status_code == 403
    assert (await client.patch(
        f"/v1/rx/{rx['id']}", json={"notes": "x"})).status_code == 403


async def test_practice_cannot_check_in(client):
    await login(client, STAFF)
    rx = await _add_item(client, await _draft(client))
    rx = (await _submit(client, rx)).json()
    r = await client.post(f"/v1/rx/{rx['id']}/check-in", json={},
                          headers={"If-Match": str(rx["version"])})
    assert r.status_code == 403


async def test_other_lab_and_foreign_tenant_isolated(client, admindb):
    await login(client, STAFF)
    rx = await _add_item(client, await _draft(client))
    rx = (await _submit(client, rx)).json()

    # LB is a lab but NOT the addressed lab -> cannot see or check in
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
    await login(client, "lab2@lb.dev")
    assert (await client.get(f"/v1/rx/{rx['id']}")).status_code == 403
    assert (await client.post(
        f"/v1/rx/{rx['id']}/check-in", json={},
        headers={"If-Match": "1"})).status_code == 403


async def test_version_conflict_and_rx_history(client):
    await login(client, STAFF)
    pid = await _patient_id(client)
    rx = await _draft(client)
    r = await client.patch(f"/v1/rx/{rx['id']}", json={"notes": "v2"},
                           headers={"If-Match": "99"})
    assert r.status_code == 409
    hist = (await client.get(f"/v1/patients/{pid}/rx-history")).json()
    assert rx["id"] in [i["id"] for i in hist["items"]]


async def test_comments_between_parties(client):
    await login(client, STAFF)
    rx = await _add_item(client, await _draft(client))
    rx = (await _submit(client, rx)).json()
    await login(client, LAB_TECH)
    r = await client.post(f"/v1/rx/{rx['id']}/comments",
                          json={"body": "scan looks thin on 16"})
    assert r.status_code == 201, r.text
    await login(client, STAFF)
    items = (await client.get(f"/v1/rx/{rx['id']}/comments")).json()["items"]
    assert any("scan looks thin" in c["body"] for c in items)


async def test_attach_asset_and_lab_reads_it(client, s3ok):
    """Rx-attached file becomes visible to the addressed lab (SRC01)."""
    await login(client, STAFF)
    rx = await _add_item(client, await _draft(client))
    rx = (await _submit(client, rx)).json()

    # upload a synthetic STL as practice
    content = b"solid x\nfacet normal 0 0 0\nendfacet\nendsolid x\n"
    import hashlib
    sha = hashlib.sha256(content).hexdigest()
    sess = (await client.post("/v1/uploads", json={
        "sha256": sha, "bytes": len(content), "kind": "stl",
        "jaw": "upper"})).json()
    import httpx
    put = await httpx.AsyncClient().put(sess["upload_urls"][0],
                                        content=content)
    assert put.status_code == 200
    asset = (await client.post(
        f"/v1/uploads/{sess['id']}/complete",
        json={"sha256": sha})).json()
    r = await client.post(f"/v1/rx/{rx['id']}/attachments",
                          json={"asset_id": asset["id"], "role": "original"})
    assert r.status_code == 201, r.text

    # lab can now download the referenced asset
    await login(client, LAB_ADMIN)
    r = await client.post(f"/v1/assets/{asset['id']}/download", json={})
    assert r.status_code == 200, r.text
    # and bundle lists it
    r = await client.post(f"/v1/rx/{rx['id']}/bundle-download")
    assert r.status_code == 200, r.text
    import httpx as _h
    z = await _h.AsyncClient().get(r.json()["download_url"])
    zf = zipfile.ZipFile(io.BytesIO(z.content))
    assert asset["id"] in zf.read("manifest.json").decode()
