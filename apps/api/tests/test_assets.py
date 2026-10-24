"""S1a-03: upload sessions, content verification, immutability, references,
download grants — exercised against the real S3 store (rustfs)."""
import asyncio
import hashlib
import uuid

import httpx
import pytest
import pytest_asyncio

from app.config import get_settings
from app.storage import s3
from tests.conftest import login

pytestmark = pytest.mark.asyncio
_s = get_settings()

ASCII_STL = b"""solid probe
facet normal 0 0 0
  outer loop
    vertex 0 0 0
    vertex 1 0 0
    vertex 0 1 0
  endloop
endfacet
endsolid probe
"""


def _binary_stl(tris: int = 2) -> bytes:
    return b"\x00" * 80 + tris.to_bytes(4, "little") + b"\x00" * (50 * tris)


@pytest_asyncio.fixture
async def s3ok(_database):
    """Real S3 store gate — CI provides rustfs; skip only when truly absent."""
    try:
        await asyncio.to_thread(s3().head_bucket, Bucket=_s.s3_bucket)
    except Exception:
        try:
            await asyncio.to_thread(s3().create_bucket, Bucket=_s.s3_bucket)
        except Exception as e:
            pytest.skip(f"S3 store unavailable: {e}")
    return _s.s3_bucket


async def _put_presigned(url: str, content: bytes) -> int:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.put(url, content=content)
        return r.status_code


async def _upload(client, content: bytes, kind: str = "stl",
                  jaw: str = "upper") -> dict:
    """Full declare -> PUT -> complete round trip."""
    sha = hashlib.sha256(content).hexdigest()
    r = await client.post("/v1/uploads", json={
        "sha256": sha, "bytes": len(content), "kind": kind, "jaw": jaw})
    assert r.status_code == 201, r.text
    sess = r.json()
    if not sess["resumed"]:
        assert (await _put_presigned(sess["upload_urls"][0], content)) == 200
    r = await client.post(f"/v1/uploads/{sess['id']}/complete",
                          json={"sha256": sha})
    return r


async def test_upload_complete_roundtrip_and_hash(client, s3ok):
    await login(client, "staff@pa.dev")
    content = _binary_stl(3)
    r = await _upload(client, content)
    assert r.status_code == 202, r.text
    asset = r.json()
    assert asset["scan_status"] == "clean"
    assert asset["sha256"] == hashlib.sha256(content).hexdigest()
    assert asset["jaw"] == "upper"

    # content actually lives at the content-addressed key
    obj = await asyncio.to_thread(
        s3().get_object, Bucket=_s.s3_bucket, Key=f"assets/{asset['sha256']}")
    assert await asyncio.to_thread(obj["Body"].read) == content


async def test_declared_hash_must_match_bytes(client, s3ok):
    await login(client, "staff@pa.dev")
    content = _binary_stl(1)
    declared = hashlib.sha256(b"different").hexdigest()
    r = await client.post("/v1/uploads", json={
        "sha256": declared, "bytes": len(content), "kind": "stl", "jaw": "na"})
    sess = r.json()
    await _put_presigned(sess["upload_urls"][0], content)
    r = await client.post(f"/v1/uploads/{sess['id']}/complete",
                          json={"sha256": declared})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "content_mismatch"


async def test_invalid_stl_rejected(client, s3ok):
    await login(client, "staff@pa.dev")
    content = b"this is not an stl file at all" * 10
    r = await _upload(client, content)
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "invalid_mesh"


async def test_dedup_returns_same_asset(client, s3ok):
    await login(client, "staff@pa.dev")
    content = _binary_stl(5)
    a1 = (await _upload(client, content)).json()
    a2 = (await _upload(client, content)).json()
    assert a1["id"] == a2["id"], "same org + same content must dedup"


async def test_asset_visibility_and_download(client, s3ok):
    await login(client, "staff@pa.dev")
    content = _binary_stl(2)
    asset = (await _upload(client, content)).json()

    # uploader's org sees metadata + can download
    r = await client.get(f"/v1/assets/{asset['id']}")
    assert r.status_code == 200
    r = await client.post(f"/v1/assets/{asset['id']}/download", json={})
    assert r.status_code == 200
    url = r.json()["url"]
    async with httpx.AsyncClient(timeout=30) as c:
        dl = await c.get(url)
    assert dl.status_code == 200
    assert hashlib.sha256(dl.content).hexdigest() == asset["sha256"]

    # lab side: asset:read exists but the asset is not visible to them
    await login(client, "tech@la.dev")
    assert (await client.get(f"/v1/assets/{asset['id']}")).status_code == 403
    assert (await client.post(f"/v1/assets/{asset['id']}/download",
                              json={})).status_code == 403


async def test_reference_grant_revoke_cycle(client, s3ok):
    await login(client, "admin@pa.dev")
    pr = await client.post("/v1/patients", json={
        "first_name": "Ref", "last_name": "Holder", "dob": "2000-01-01"})
    pid = pr.json()["id"]
    content = _binary_stl(4)
    asset = (await _upload(client, content)).json()

    r = await client.post(f"/v1/assets/{asset['id']}/references", json={
        "subject_type": "patient", "subject_id": pid, "role": "original"})
    assert r.status_code == 201, r.text
    ref_id = r.json()["id"]

    r = await client.get(f"/v1/patients/{pid}/assets")
    items = r.json()["items"]
    assert len(items) == 1 and items[0]["asset"]["sha256"] == asset["sha256"]

    # revoke -> list empty; asset still accessible to the OWNING org
    assert (await client.delete(
        f"/v1/assets/{asset['id']}/references",
        params={"subject_type": "patient", "subject_id": pid})
    ).status_code == 204
    r = await client.get(f"/v1/patients/{pid}/assets")
    assert r.json()["items"] == []
    assert (await client.get(f"/v1/assets/{asset['id']}")).status_code == 200


async def test_lab_cannot_reference_foreign_patient(client, s3ok, admindb):
    """A lab uploading its own asset still cannot attach it to PA's patient —
    subject ownership is checked, not just asset visibility."""
    await login(client, "staff@pa.dev")
    pr = await client.post("/v1/patients", json={
        "first_name": "Guard", "last_name": "Subject"})
    pid = pr.json()["id"]

    await login(client, "admin@la.dev")
    content = _binary_stl(1)
    asset = (await _upload(client, content)).json()
    # lab_admin lacks asset:share -> 403 at the permission layer already;
    # even so the endpoint must double-check subject ownership.
    assert (await client.post(f"/v1/assets/{asset['id']}/references", json={
        "subject_type": "patient", "subject_id": pid,
        "role": "original"})).status_code == 403


async def test_session_owner_only_and_expired(client, s3ok, admindb):
    from sqlalchemy import text
    await login(client, "staff@pa.dev")
    content = _binary_stl(1)
    sha = hashlib.sha256(content).hexdigest()
    r = await client.post("/v1/uploads", json={
        "sha256": sha, "bytes": len(content), "kind": "stl", "jaw": "na"})
    sess = r.json()
    # someone else's session cannot be completed
    await login(client, "admin@la.dev")
    assert (await client.post(f"/v1/uploads/{sess['id']}/complete",
                              json={"sha256": sha})).status_code == 403
    # expired session -> 409 for the owner too
    await admindb.execute(text(
        "UPDATE upload_session SET expires_at = now() - interval '1s' "
        "WHERE id = :i"), {"i": sess["id"]})
    await admindb.commit()
    await login(client, "staff@pa.dev")
    assert (await client.post(f"/v1/uploads/{sess['id']}/complete",
                              json={"sha256": sha})).status_code == 409
