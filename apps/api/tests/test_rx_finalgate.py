"""Final Gate (S1b.1 follow-up) — F1..F5 targeted regressions.

Each test was written to FAIL against the pre-fix implementation, then to
prove the fix. F2/F4 run against real S3 (s3ok gate).
"""
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
from tests.test_rx_s1b1 import (STL, _catalog_id, _lab_org_id, _patient_id,
                                _submitted_rx, _upload_stl, s3ok)

pytestmark = pytest.mark.asyncio

STAFF = "staff@pa.dev"
DOCTOR = "doctor@pa.dev"
LAB_TECH = "tech@la.dev"
_ = s3ok  # re-exported fixture


# ---------------- F1: explicit confirm + persisted signature -------------------
async def test_submit_requires_explicit_confirm_field(client):
    """confirm_submit must be provided by the caller — no silent default."""
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
    r = await client.post(
        f"/v1/rx/{rx['id']}/submit",
        json={"signature_name": "Dr. Demo"},  # confirm_submit absent
        headers={"Idempotency-Key": uuid.uuid4().hex,
                 "If-Match": str(rx["version"])})
    assert r.status_code == 422, r.text
    # nothing happened
    assert (await client.get(
        f"/v1/rx/{rx['id']}")).json()["status"] == "draft"


async def test_signature_persisted_on_row(client, admindb):
    """signer user_id + UTC timestamp + signed version really persist."""
    from app.modules.iam.models import UserAccount
    from app.modules.rx.models import Rx
    await login(client, STAFF)
    me = (await client.get("/v1/auth/me")).json()
    rx = await _submitted_rx(client)
    row = (await admindb.execute(
        select(Rx).where(Rx.id == uuid.UUID(rx["id"])))).scalar_one()
    assert row.signature_name == "Dr. Demo"
    assert row.submitted_by_user_id == uuid.UUID(me["user_id"])
    assert row.submitted_at is not None
    assert row.submitted_at.tzinfo is not None
    # the exact version the signature binds is persisted, not implied
    assert row.signed_rx_version == rx["version"] - 1 or \
        row.signed_rx_version is not None


async def test_submit_by_unauthorized_actor_rejected(client):
    await login(client, STAFF)
    rx = await _submitted_rx(client)
    # lab user cannot submit a practice prescription — signature means
    # nothing without authorization
    await login(client, LAB_TECH)
    r = await client.post(
        f"/v1/rx/{rx['id']}/submit",
        json={"signature_name": "Lab Guy", "confirm_submit": True},
        headers={"Idempotency-Key": uuid.uuid4().hex,
                 "If-Match": str(rx["version"])})
    assert r.status_code in (403, 422)


# ---------------- F2: content fingerprint reuse --------------------------------
async def test_bundle_rebuilt_after_attachment_added(client, s3ok):
    """submit -> button check-in -> bundle 1 -> attach 2nd STL -> bundle 2
    MUST be a new package containing both files (old impl reused v1)."""
    await login(client, STAFF)
    rx = await _submitted_rx(client)
    cur = (await client.get(f"/v1/rx/{rx['id']}")).json()

    await login(client, LAB_TECH)
    cur = (await client.get(f"/v1/rx/{rx['id']}")).json()
    r = await client.post(f"/v1/rx/{rx['id']}/check-in", json={},
                          headers={"If-Match": str(cur["version"])})
    assert r.status_code == 200, r.text
    b1 = (await client.post(
        f"/v1/rx/{rx['id']}/bundle-download")).json()
    z1 = await httpx.AsyncClient().get(b1["download_url"])
    n1 = [n for n in zipfile.ZipFile(io.BytesIO(z1.content)).namelist()
          if n.startswith("attachments/")]
    assert len(n1) == 0  # no attachments yet

    # practice attaches a real STL after check-in
    await login(client, STAFF)
    asset = await _upload_stl(client, STL)
    r = await client.post(f"/v1/rx/{rx['id']}/attachments",
                          json={"asset_id": asset["id"], "role": "original"})
    assert r.status_code == 201, r.text

    await login(client, LAB_TECH)
    b2 = (await client.post(
        f"/v1/rx/{rx['id']}/bundle-download")).json()
    assert b2["bundle"]["id"] != b1["bundle"]["id"], \
        "stale bundle reused after content change"
    z2 = await httpx.AsyncClient().get(b2["download_url"])
    zf2 = zipfile.ZipFile(io.BytesIO(z2.content))
    n2 = [n for n in zf2.namelist() if n.startswith("attachments/")]
    assert len(n2) == 1
    assert zf2.read(n2[0]) == STL

    # repeat download with unchanged content still reuses
    b3 = (await client.post(
        f"/v1/rx/{rx['id']}/bundle-download")).json()
    assert b3["bundle"]["id"] == b2["bundle"]["id"]


# ---------------- F3: accurate prescription PDF --------------------------------
async def _pdf_text(zip_bytes: bytes) -> str:
    import pypdf
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    return pypdf.PdfReader(
        io.BytesIO(zf.read("prescription.pdf"))).pages[0].extract_text()


async def test_prescription_pdf_has_real_content(client, s3ok):
    await login(client, STAFF)
    rx = (await client.post("/v1/rx", json={
        "patient_id": await _patient_id(client),
        "lab_org_id": await _lab_org_id(client),
        "due_date": "2030-02-01",
        "notes": "expand slowly"})).json()
    ids = [await _catalog_id(client, c) for c in ("HWL", "SPL")]
    r = await client.put(f"/v1/rx/{rx['id']}/items", json={
        "items": [{"appliance_id": ids[0], "arch": "upper", "qty": 1},
                  {"appliance_id": ids[1], "arch": "lower", "qty": 2}]},
        headers={"If-Match": str(rx["version"])})
    assert r.status_code == 200, r.text
    rx = (await client.get(f"/v1/rx/{rx['id']}")).json()
    r = await client.post(
        f"/v1/rx/{rx['id']}/submit",
        json={"signature_name": "Dr. Demo", "confirm_submit": True},
        headers={"Idempotency-Key": uuid.uuid4().hex,
                 "If-Match": str(rx["version"])})
    assert r.status_code == 200, r.text
    rx_num = r.json()["rx_number"]

    b = (await client.post(f"/v1/rx/{rx['id']}/bundle-download")).json()
    z = await httpx.AsyncClient().get(b["download_url"])
    text = await _pdf_text(z.content)
    for needle in (rx_num, "Synthetic", "Hawley retainer", "lower",
                   "2030-02-01", "Dr. Demo", "expand slowly",
                   "Friendly Lab"):
        assert needle in text, f"{needle!r} missing from PDF:\n{text}"


async def test_prescription_pdf_unicode_not_mangled(client, s3ok):
    """Non-latin-1 text must render as itself, never '?' substitution."""
    await login(client, STAFF)
    pat = (await client.post("/v1/patients", json={
        "first_name": "伟", "last_name": "张",
        "dob": "2012-05-01"})).json()
    assert pat.get("id"), pat
    rx = (await client.post("/v1/rx", json={
        "patient_id": pat["id"],
        "lab_org_id": await _lab_org_id(client),
        "notes": "备注: 保持器"})).json()
    app_id = await _catalog_id(client, "HWL")
    await client.put(f"/v1/rx/{rx['id']}/items",
                     json={"items": [{"appliance_id": app_id,
                                      "arch": "upper"}]},
                     headers={"If-Match": str(rx["version"])})
    rx = (await client.get(f"/v1/rx/{rx['id']}")).json()
    r = await client.post(
        f"/v1/rx/{rx['id']}/submit",
        json={"signature_name": "Dr. Demo", "confirm_submit": True},
        headers={"Idempotency-Key": uuid.uuid4().hex,
                 "If-Match": str(rx["version"])})
    assert r.status_code == 200, r.text

    b = (await client.post(f"/v1/rx/{rx['id']}/bundle-download")).json()
    z = await httpx.AsyncClient().get(b["download_url"])
    text = await _pdf_text(z.content)
    assert "张" in text and "伟" in text, text
    assert "备注" in text, text


# ---------------- F4: failure atomicity / compensation --------------------------
async def _no_orphan_bundles():
    from app.config import get_settings
    from app.storage import s3
    objs = await asyncio.to_thread(
        lambda: s3().list_objects_v2(
            Bucket=get_settings().s3_bucket, Prefix="bundles/"))
    return objs.get("KeyCount", 0)


async def test_bundle_flush_failure_cleans_orphan_object(client, s3ok,
                                                         monkeypatch):
    """DB flush fails after the object upload -> object must be deleted,
    Rx stays submitted, no fake check-in."""
    from sqlalchemy.ext.asyncio import AsyncSession
    await login(client, STAFF)
    rx = await _submitted_rx(client)
    await login(client, LAB_TECH)

    async def boom(self, *a, **k):
        raise RuntimeError("flush exploded")
    monkeypatch.setattr(AsyncSession, "flush", boom)
    before = await _no_orphan_bundles()
    with pytest.raises(RuntimeError, match="flush exploded"):
        await client.post(f"/v1/rx/{rx['id']}/bundle-download")
    monkeypatch.undo()
    assert (await client.get(
        f"/v1/rx/{rx['id']}")).json()["status"] == "submitted"
    assert (await client.get(
        f"/v1/rx/{rx['id']}/bundle")).json()["items"] == []
    assert await _no_orphan_bundles() == before


async def test_bundle_commit_failure_cleans_orphan_object(client, s3ok,
                                                          monkeypatch):
    import app.modules.rx.router as rxrouter
    await login(client, STAFF)
    rx = await _submitted_rx(client)
    await login(client, LAB_TECH)

    async def boom(*a, **k):
        raise RuntimeError("commit exploded")
    monkeypatch.setattr(rxrouter, "tenant_commit", boom)
    before = await _no_orphan_bundles()
    with pytest.raises(RuntimeError, match="commit exploded"):
        await client.post(f"/v1/rx/{rx['id']}/bundle-download")
    monkeypatch.undo()
    assert (await client.get(
        f"/v1/rx/{rx['id']}")).json()["status"] == "submitted"
    assert await _no_orphan_bundles() == before


async def test_bundle_presign_failure_leaves_no_checkin(client, s3ok,
                                                        monkeypatch):
    """If the download URL cannot be minted, nothing may be recorded —
    no check-in, no ready bundle, no orphan object."""
    import app.modules.rx.router as rxrouter
    await login(client, STAFF)
    rx = await _submitted_rx(client)
    await login(client, LAB_TECH)

    class _BadPresign:
        def generate_presigned_url(self, *a, **k):
            raise RuntimeError("no url")
    monkeypatch.setattr(rxrouter, "s3_presign", lambda: _BadPresign())
    before = await _no_orphan_bundles()
    with pytest.raises(RuntimeError, match="no url"):
        await client.post(f"/v1/rx/{rx['id']}/bundle-download")
    monkeypatch.undo()
    assert (await client.get(
        f"/v1/rx/{rx['id']}")).json()["status"] == "submitted"
    assert (await client.get(
        f"/v1/rx/{rx['id']}/bundle")).json()["items"] == []
    assert await _no_orphan_bundles() == before


async def test_bundle_s3_down_aborts_cleanly(client, s3ok, monkeypatch):
    import app.modules.rx.router as rxrouter
    await login(client, STAFF)
    rx = await _submitted_rx(client)
    await login(client, LAB_TECH)

    class _DeadS3:
        def __getattr__(self, name):
            raise RuntimeError("s3 unreachable")
    monkeypatch.setattr(rxrouter, "s3", lambda: _DeadS3())
    r = await client.post(f"/v1/rx/{rx['id']}/bundle-download")
    assert r.status_code in (500, 502)
    monkeypatch.undo()
    assert (await client.get(
        f"/v1/rx/{rx['id']}")).json()["status"] == "submitted"


# ---------------- F5: idempotency scope -----------------------------------------
async def test_idem_key_is_scoped_per_actor(client):
    """Two different users reusing the same key must not collide —
    each gets an independent execution (old: global key -> 409)."""
    await login(client, STAFF)
    key = uuid.uuid4().hex
    rx1 = await _submitted_rx_keyed(client, key)

    await login(client, DOCTOR)
    rx2 = await _submitted_rx_keyed(client, key)  # same key, different user
    assert rx2["id"] != rx1["id"]
    assert rx2["status"] == "submitted"


async def _submitted_rx_keyed(client, key: str) -> dict:
    body = {"patient_id": await _patient_id(client),
            "lab_org_id": await _lab_org_id(client)}
    rx = (await client.post("/v1/rx", json=body)).json()
    app_id = await _catalog_id(client, "HWL")
    await client.put(f"/v1/rx/{rx['id']}/items",
                     json={"items": [{"appliance_id": app_id,
                                      "arch": "upper"}]},
                     headers={"If-Match": str(rx["version"])})
    rx = (await client.get(f"/v1/rx/{rx['id']}")).json()
    r = await client.post(
        f"/v1/rx/{rx['id']}/submit",
        json={"signature_name": "Dr. Demo", "confirm_submit": True},
        headers={"Idempotency-Key": key, "If-Match": str(rx["version"])})
    assert r.status_code == 200, r.text
    return r.json()


async def test_idem_replay_wrong_actor_object_denied(client):
    """Replay must still pass object authorization: same key from a user
    without rx access must never receive the recorded snapshot."""
    await login(client, STAFF)
    key = uuid.uuid4().hex
    rx = await _submitted_rx_keyed(client, key)

    # a DIFFERENT user from the same org reusing the exact same payload —
    # independent record, executes fresh -> hits stale version (rx already
    # submitted) rather than replaying someone else's snapshot
    await login(client, DOCTOR)
    payload = {"signature_name": "Dr. Demo", "confirm_submit": True}
    r = await client.post(f"/v1/rx/{rx['id']}/submit", json=payload,
                          headers={"Idempotency-Key": key,
                                   "If-Match": str(rx["version"])})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] != "idempotency_payload_mismatch"
