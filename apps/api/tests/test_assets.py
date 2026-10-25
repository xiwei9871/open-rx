"""S1a-03: upload sessions, content verification, immutability, references,
download grants — exercised against the real S3 store (rustfs)."""
import asyncio
import hashlib
import os
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


def _binary_stl(tris: int = 2, tag: bytes | None = None) -> bytes:
    """tag stamps the header so each call can produce globally-unique bytes."""
    header = (tag or b"\x00" * 16) + b"\x00" * 64
    return header + tris.to_bytes(4, "little") + b"\x00" * (50 * tris)


@pytest_asyncio.fixture
async def s3ok(_database):
    """Real S3 store gate — CI provides rustfs; skip only when truly absent.
    REQUIRE_S3=1 (asset-integration job) turns absence into a hard failure:
    green must never be fabricated by skipping."""
    try:
        await asyncio.to_thread(s3().head_bucket, Bucket=_s.s3_bucket)
    except Exception:
        try:
            await asyncio.to_thread(s3().create_bucket, Bucket=_s.s3_bucket)
        except Exception as e:
            if os.environ.get("REQUIRE_S3"):
                raise AssertionError(f"S3 required but unavailable: {e}")
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
    # Always PUT — a resumed session's staging object may never have landed.
    assert (await _put_presigned(sess["upload_urls"][0], content)) == 200
    r = await client.post(f"/v1/uploads/{sess['id']}/complete",
                          json={"sha256": sha})
    return r


async def _asset_row(admindb, asset_id: str) -> dict:
    from sqlalchemy import text
    return (await admindb.execute(text(
        "SELECT id, tenant_id, org_id, sha256, storage_key, format_status "
        "FROM asset WHERE id = :i"), {"i": asset_id})).mappings().one()


async def _mk_org_user(admindb, email: str, role: str,
                       tenant_id=None, org_name=None):
    """Create org(+membership+user) under an existing or NEW tenant."""
    from sqlalchemy import text as _t
    from app.security import hash_password
    if tenant_id is None:
        tenant_id = (await admindb.execute(_t(
            "INSERT INTO tenant (id, name) VALUES (gen_random_uuid(), :n) "
            "RETURNING id"), {"n": f"T2-{uuid.uuid4().hex[:8]}"})).scalar_one()
    org_id = (await admindb.execute(_t(
        "INSERT INTO organization (id, tenant_id, kind, name, status) VALUES "
        "(gen_random_uuid(), :t, 'lab', :n, 'active') RETURNING id"),
        {"t": tenant_id, "n": org_name or f"Org-{uuid.uuid4().hex[:8]}"})
    ).scalar_one()
    uid = (await admindb.execute(_t(
        "INSERT INTO user_account (id, email, display_name, password_hash, "
        "status) VALUES (gen_random_uuid(), :e, 'T', :h, 'active') "
        "RETURNING id"), {"e": email, "h": hash_password("Passw0rd!dev")}
    )).scalar_one()
    await admindb.execute(_t(
        "INSERT INTO membership (id, tenant_id, org_id, user_id, role, status) "
        "VALUES (gen_random_uuid(), :t, :o, :u, :r, 'active')"),
        {"t": tenant_id, "o": org_id, "u": uid, "r": role})
    await admindb.commit()
    return {"tenant_id": str(tenant_id), "org_id": str(org_id)}


async def test_upload_complete_roundtrip_and_hash(client, s3ok, admindb):
    await login(client, "staff@pa.dev")
    content = _binary_stl(3)
    r = await _upload(client, content)
    assert r.status_code == 202, r.text
    asset = r.json()
    assert asset["format_status"] == "format_ok"  # structure check only, not a scan
    assert asset["sha256"] == hashlib.sha256(content).hexdigest()
    assert asset["jaw"] == "upper"

    # content actually lives at the namespaced content key recorded in the row
    row = await _asset_row(admindb, asset["id"])
    obj = await asyncio.to_thread(
        s3().get_object, Bucket=_s.s3_bucket, Key=row["storage_key"])
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


# ---- S1a1-01: namespaced storage keys --------------------------------------
async def test_cross_org_same_bytes_independent_assets(client, s3ok, admindb):
    """Same bytes, two orgs in one tenant -> two independent assets with
    org-namespaced keys, no shared mutable object, no access cross-over."""
    content = _binary_stl(2, tag=uuid.uuid4().bytes)
    sha = hashlib.sha256(content).hexdigest()

    await login(client, "staff@pa.dev")
    r = await _upload(client, content)
    assert r.status_code == 202, r.text
    a_pa = r.json()

    await login(client, "admin@la.dev")  # same tenant, different org
    r = await _upload(client, content)
    assert r.status_code == 202, r.text
    a_la = r.json()

    assert a_pa["id"] != a_la["id"], "identical bytes must not merge across orgs"
    pa_row = await _asset_row(admindb, a_pa["id"])
    la_row = await _asset_row(admindb, a_la["id"])
    assert pa_row["storage_key"] != la_row["storage_key"]
    assert pa_row["storage_key"].endswith(f"/{sha}") and \
        str(pa_row["org_id"]) in pa_row["storage_key"], pa_row["storage_key"]
    assert str(la_row["org_id"]) in la_row["storage_key"]

    # both objects physically exist at their own keys
    for key in (pa_row["storage_key"], la_row["storage_key"]):
        obj = await asyncio.to_thread(
            s3().get_object, Bucket=_s.s3_bucket, Key=key)
        assert await asyncio.to_thread(obj["Body"].read) == content

    # no implicit cross-org visibility
    assert (await client.get(f"/v1/assets/{a_pa['id']}")).status_code == 403
    await login(client, "staff@pa.dev")
    assert (await client.get(f"/v1/assets/{a_la['id']}")).status_code == 403


async def test_cross_tenant_same_bytes_independent(client, s3ok, admindb):
    """Second tenant uploading the same file gets its own tenant-scoped key."""
    content = _binary_stl(2, tag=uuid.uuid4().bytes)
    await login(client, "staff@pa.dev")
    a_t1 = (await _upload(client, content)).json()

    email = f"t2u-{uuid.uuid4().hex[:6]}@x.dev"
    await _mk_org_user(admindb, email, "lab_admin")  # brand-new tenant
    await login(client, email)
    a_t2 = (await _upload(client, content)).json()

    t1 = await _asset_row(admindb, a_t1["id"])
    t2 = await _asset_row(admindb, a_t2["id"])
    assert t1["tenant_id"] != t2["tenant_id"]
    assert t2["storage_key"].startswith(f"assets/{t2['tenant_id']}/")
    assert (await client.get(f"/v1/assets/{a_t1['id']}")).status_code == 403


async def test_same_org_reupload_dedups_and_never_overwrites(
        client, s3ok, admindb):
    """Same org + same bytes -> the original asset row returns; the stored
    object stays byte-identical (nothing is overwritten in place)."""
    await login(client, "staff@pa.dev")
    content = _binary_stl(2, tag=uuid.uuid4().bytes)
    a1 = (await _upload(client, content)).json()
    a2 = (await _upload(client, content)).json()
    assert a1["id"] == a2["id"]
    row = await _asset_row(admindb, a1["id"])
    obj = await asyncio.to_thread(
        s3().get_object, Bucket=_s.s3_bucket, Key=row["storage_key"])
    assert await asyncio.to_thread(obj["Body"].read) == content


async def test_legacy_flat_key_asset_still_downloadable(client, s3ok, admindb):
    """Pre-S1a1 rows keep storage_key='assets/{sha}' — downloads must still
    resolve the flat key. We never rewrite existing storage_key values."""
    from sqlalchemy import text
    content = _binary_stl(2, tag=uuid.uuid4().bytes)
    sha = hashlib.sha256(content).hexdigest()
    flat_key = f"assets/{sha}"
    await asyncio.to_thread(
        s3().put_object, Bucket=_s.s3_bucket, Key=flat_key, Body=content)

    await login(client, "staff@pa.dev")
    pa = (await admindb.execute(text(
        "SELECT u.id AS uid, o.id AS oid, o.tenant_id AS tid "
        "FROM user_account u JOIN membership m ON m.user_id = u.id "
        "JOIN organization o ON o.id = m.org_id "
        "WHERE u.email = 'staff@pa.dev'"))).mappings().one()
    aid = (await admindb.execute(text(
        "INSERT INTO asset (id, tenant_id, org_id, uploaded_by_user_id, "
        "sha256, kind, jaw, bytes, storage_key, format_status) VALUES "
        "(gen_random_uuid(), :t, :o, :u, :s, 'stl', 'na', :b, :k, 'format_ok') "
        "RETURNING id"), {"t": pa["tid"], "o": pa["oid"], "u": pa["uid"],
                          "s": sha, "b": len(content), "k": flat_key})
    ).scalar_one()
    await admindb.commit()

    assert (await client.get(f"/v1/assets/{aid}")).status_code == 200
    r = await client.post(f"/v1/assets/{aid}/download", json={})
    assert r.status_code == 200
    async with httpx.AsyncClient(timeout=30) as c:
        dl = await c.get(r.json()["url"])
    assert hashlib.sha256(dl.content).hexdigest() == sha


# ---- S1a1-02: cleanup must not drop tenant context --------------------------
async def test_expired_cleanup_keeps_rls_context(client, s3ok, admindb):
    """With a stale session present, declare must still succeed AND write —
    a mid-request commit previously dropped SET LOCAL app.tenant_id and the
    follow-on INSERT hit the RLS WITH CHECK (silent 500)."""
    from sqlalchemy import text
    await login(client, "staff@pa.dev")
    content = _binary_stl(2, tag=uuid.uuid4().bytes)
    stale = await client.post("/v1/uploads", json={
        "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content),
        "kind": "stl", "jaw": "na"})
    assert stale.status_code == 201, stale.text
    await admindb.execute(text(
        "UPDATE upload_session SET expires_at = now() - interval '1s' "
        "WHERE id = :i"), {"i": stale.json()["id"]})
    await admindb.commit()

    fresh = _binary_stl(2, tag=uuid.uuid4().bytes)
    r = await client.post("/v1/uploads", json={
        "sha256": hashlib.sha256(fresh).hexdigest(), "bytes": len(fresh),
        "kind": "stl", "jaw": "na"})
    assert r.status_code == 201, r.text  # would 500 with lost tenant ctx

    status = (await admindb.execute(text(
        "SELECT status FROM upload_session WHERE id = :i"),
        {"i": stale.json()["id"]})).scalar_one()
    assert status == "expired"

    # and the new session really completes (writes survived the cleanup)
    await _put_presigned(r.json()["upload_urls"][0], fresh)
    done = await client.post(f"/v1/uploads/{r.json()['id']}/complete",
                             json={"sha256": hashlib.sha256(fresh).hexdigest()})
    assert done.status_code == 202, done.text


async def test_cleanup_storage_failure_does_not_block_declare(
        client, s3ok, admindb, monkeypatch):
    """If object deletion throws, cleanup must still let the new upload in."""
    from sqlalchemy import text
    import app.modules.assets.router as assets_router
    await login(client, "staff@pa.dev")
    content = _binary_stl(2, tag=uuid.uuid4().bytes)
    stale = await client.post("/v1/uploads", json={
        "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content),
        "kind": "stl", "jaw": "na"})
    assert stale.status_code == 201
    await admindb.execute(text(
        "UPDATE upload_session SET expires_at = now() - interval '1s' "
        "WHERE id = :i"), {"i": stale.json()["id"]})
    await admindb.commit()

    real_s3 = assets_router.s3
    class _FlakyS3:
        def __getattr__(self, name):
            return getattr(real_s3(), name)
        def delete_object(self, **kw):
            raise RuntimeError("storage backend down")
    monkeypatch.setattr(assets_router, "s3", lambda: _FlakyS3())

    fresh = _binary_stl(2, tag=uuid.uuid4().bytes)
    r = await client.post("/v1/uploads", json={
        "sha256": hashlib.sha256(fresh).hexdigest(), "bytes": len(fresh),
        "kind": "stl", "jaw": "na"})
    assert r.status_code == 201, r.text


async def test_cleanup_only_touches_caller_tenant(client, s3ok, admindb):
    """An expired session in ANOTHER tenant must not be expired (nor error)
    by this tenant's cleanup — RLS keeps the stale row invisible."""
    from sqlalchemy import text
    email = f"t3u-{uuid.uuid4().hex[:6]}@x.dev"
    await _mk_org_user(admindb, email, "lab_admin")  # new tenant
    await login(client, email)
    content = _binary_stl(2, tag=uuid.uuid4().bytes)
    stale = await client.post("/v1/uploads", json={
        "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content),
        "kind": "stl", "jaw": "na"})
    assert stale.status_code == 201
    sid = stale.json()["id"]
    await admindb.execute(text(
        "UPDATE upload_session SET expires_at = now() - interval '1s' "
        "WHERE id = :i"), {"i": sid})
    await admindb.commit()

    # tenant-1 user declares -> cleanup runs under THEIR context only
    await login(client, "staff@pa.dev")
    fresh = _binary_stl(2, tag=uuid.uuid4().bytes)
    r = await client.post("/v1/uploads", json={
        "sha256": hashlib.sha256(fresh).hexdigest(), "bytes": len(fresh),
        "kind": "stl", "jaw": "na"})
    assert r.status_code == 201, r.text
    status = (await admindb.execute(text(
        "SELECT status FROM upload_session WHERE id = :i"),
        {"i": sid})).scalar_one()
    assert status == "open", "foreign-tenant session must stay untouched"


async def test_interrupted_upload_leaves_no_half_file(client, s3ok, admindb):
    """E2E-12: a session whose PUT was interrupted (partial bytes staged,
    complete never succeeding) must leave NO downloadable asset — no row,
    no reachable object, and the stale staging object is reaped."""
    from sqlalchemy import text
    await login(client, "staff@pa.dev")
    content = _binary_stl(4, tag=uuid.uuid4().bytes)
    r = await client.post("/v1/uploads", json={
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content), "kind": "stl", "jaw": "upper"})
    assert r.status_code == 201
    sess = r.json()

    # interrupted PUT: only the first half of the file ever lands
    partial = content[: len(content) // 2]
    assert (await _put_presigned(sess["upload_urls"][0], partial)) == 200

    # trying to complete the truncated upload is refused — no asset created
    done = await client.post(f"/v1/uploads/{sess['id']}/complete",
                             json={"sha256": hashlib.sha256(content).hexdigest()})
    assert done.status_code == 422, done.text
    assets = (await admindb.execute(text(
        "SELECT count(*) FROM asset WHERE sha256 = :s"),
        {"s": hashlib.sha256(content).hexdigest()})).scalar_one()
    assert assets == 0

    # expire the session -> next declare reaps the half-written staging object
    staging_key = (await admindb.execute(text(
        "SELECT storage_key FROM upload_session WHERE id = :i"),
        {"i": sess["id"]})).scalar_one()
    await admindb.execute(text(
        "UPDATE upload_session SET expires_at = now() - interval '1s' "
        "WHERE id = :i"), {"i": sess["id"]})
    await admindb.commit()
    fresh = _binary_stl(2, tag=uuid.uuid4().bytes)
    r = await client.post("/v1/uploads", json={
        "sha256": hashlib.sha256(fresh).hexdigest(),
        "bytes": len(fresh), "kind": "stl", "jaw": "na"})
    assert r.status_code == 201, r.text  # triggers cleanup of stale session
    from botocore.exceptions import ClientError
    with pytest.raises(ClientError):
        await asyncio.to_thread(
            s3().head_object, Bucket=_s.s3_bucket, Key=staging_key)
    # the half-file session can never be completed afterwards either
    done2 = await client.post(f"/v1/uploads/{sess['id']}/complete",
                              json={"sha256": hashlib.sha256(content).hexdigest()})
    assert done2.status_code in (404, 409, 422)
