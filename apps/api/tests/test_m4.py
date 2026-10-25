"""M4: admin export scoping + pluggable AV-engine gate."""
import pytest

from tests.conftest import login
from tests.test_rx import s3ok  # noqa: F401  (shared S3 gate fixture)

pytestmark = pytest.mark.asyncio

ADMIN = "admin@pa.dev"
STAFF = "staff@pa.dev"
LAB_ADMIN = "admin@la.dev"


async def test_admin_export_org_scoped(client):
    """SAFE-009: org:manage exports own org only — no secrets, no cross-org."""
    await login(client, ADMIN)
    r = await client.get("/v1/admin/export")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["organization"]["name"] == "Smile Ortho (synthetic)"
    assert any(p["external_ref"] == "SYN-0001" for p in d["patients"])
    assert d["members"] and "password_hash" not in d["members"][0]["user"]
    # lab admin exports ITS org, not the practice's
    await login(client, LAB_ADMIN)
    r = await client.get("/v1/admin/export")
    assert r.status_code == 200
    assert r.json()["organization"]["name"] == "Friendly Lab (synthetic)"
    assert not any(p["external_ref"] == "SYN-0001"
                   for p in r.json()["patients"])


async def test_admin_export_permission_denied(client):
    await login(client, STAFF)
    r = await client.get("/v1/admin/export")
    assert r.status_code == 403


async def test_av_engine_pluggable_gate(client, s3ok):
    """ASSET-010: eicar_stub engine rejects the marker; 'none' passes it.
    Proves the scan hook is real, not a config no-op."""
    import hashlib
    import httpx
    from app.config import get_settings

    stl = (b"solid x\nfacet normal 0 0 0\nouter loop\nvertex 0 0 0\n"
           b"vertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid x\n")

    async def upload(content: bytes) -> int:
        await login(client, ADMIN)
        h = hashlib.sha256(content).hexdigest()
        up = (await client.post("/v1/uploads", json={
            "sha256": h, "bytes": len(content), "kind": "stl",
            "jaw": "upper"})).json()
        assert "id" in up, up
        async with httpx.AsyncClient(timeout=30) as raw:
            pr = await raw.put(up["upload_urls"][0], content=content)
            assert pr.status_code == 200, pr.text
        r = await client.post(f"/v1/uploads/{up['id']}/complete",
                              json={"sha256": h})
        return r.status_code

    s = get_settings()
    orig = s.asset_av_engine
    try:
        s.asset_av_engine = "eicar_stub"
        assert await upload(stl) == 202
        eicar = stl.replace(
            b"solid x",
            b"solid X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-"
            b"ANTIVIRUS-TEST-FILE!$H+H*")
        assert await upload(eicar) == 422
        s.asset_av_engine = "none"
        assert await upload(eicar) == 202
    finally:
        s.asset_av_engine = orig
