"""M1 Rx-Studio backend tests — org defaults, roster/location admin,
rx_template CRUD + validation + isolation. Real Postgres, synthetic data.
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from tests.conftest import login

pytestmark = pytest.mark.asyncio

ADMIN = "admin@pa.dev"
DOCTOR = "doctor@pa.dev"
LAB_ADMIN = "admin@la.dev"


@pytest_asyncio.fixture
async def pa_org(client):
    await login(client, ADMIN)
    me = (await client.get("/v1/auth/me")).json()
    return me["org_id"]


async def _catalog_id(client, code: str) -> str:
    for kind in ("parts", "appliances"):
        r = await client.get(f"/v1/catalog/{kind}")
        hit = [i for i in r.json()["items"] if i["code"] == code]
        if hit:
            return hit[0]["id"]
    raise AssertionError(f"catalog code {code} not found")


async def test_org_update_defaults_and_timezone(client, pa_org):
    roster = (await client.get(f"/v1/orgs/{pa_org}/roster")).json()["items"]
    doc = [r for r in roster if r["kind"] == "doctor" and r["status"] == "active"][0]
    loc = (await client.post(f"/v1/orgs/{pa_org}/locations",
                             json={"name": "Main Office",
                                   "address": "1 Synthetic Way"})).json()
    r = await client.patch(f"/v1/orgs/{pa_org}", json={
        "timezone": "America/Vancouver",
        "default_doctor_id": doc["id"],
        "default_location_id": loc["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["timezone"] == "America/Vancouver"
    assert r.json()["default_doctor_id"] == doc["id"]
    assert r.json()["default_location_id"] == loc["id"]
    # persisted
    org = [o for o in (await client.get("/v1/orgs")).json()["items"]
           if o["id"] == pa_org][0]
    assert org["default_doctor_id"] == doc["id"]
    # clearing via explicit null works
    r = await client.patch(f"/v1/orgs/{pa_org}",
                           json={"default_location_id": None})
    assert r.status_code == 200 and r.json()["default_location_id"] is None


async def test_org_update_rejects_foreign_default_doctor(client, pa_org):
    # a roster member of a different org must not be set as default
    r = await client.patch(f"/v1/orgs/{pa_org}",
                           json={"default_doctor_id": str(uuid.uuid4())})
    assert r.status_code == 422


async def test_org_update_requires_admin(client, pa_org):
    await login(client, DOCTOR)
    r = await client.patch(f"/v1/orgs/{pa_org}", json={"timezone": "UTC"})
    assert r.status_code == 403


async def test_location_update(client, pa_org):
    loc = (await client.post(f"/v1/orgs/{pa_org}/locations",
                             json={"name": "Old name"})).json()
    r = await client.patch(f"/v1/orgs/{pa_org}/locations/{loc['id']}",
                           json={"name": "New name", "phone": "555-0100"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "New name" and r.json()["phone"] == "555-0100"


async def test_roster_default_is_exclusive(client, pa_org):
    a = (await client.post(f"/v1/orgs/{pa_org}/roster",
                           json={"kind": "doctor", "display_name": "Dr A",
                                 "is_default": True})).json()
    b = (await client.post(f"/v1/orgs/{pa_org}/roster",
                           json={"kind": "doctor", "display_name": "Dr B",
                                 "is_default": False})).json()
    r = await client.patch(f"/v1/orgs/{pa_org}/roster/{b['id']}",
                           json={"is_default": True})
    assert r.status_code == 200 and r.json()["is_default"] is True
    roster = (await client.get(f"/v1/orgs/{pa_org}/roster")).json()["items"]
    a_row = [x for x in roster if x["id"] == a["id"]][0]
    assert a_row["is_default"] is False


async def test_template_crud(client, pa_org):
    item = await _catalog_id(client, "HWL")
    payload = {"items": [{"catalog_item_id": item, "arch": "upper",
                          "tooth_ops": [{"tooth": "16", "op": "reset"}],
                          "options": {"shade": "clear"}, "qty": 1}],
               "notes": "standard retainer", "due_days_offset": 14}
    r = await client.post("/v1/templates",
                          json={"name": "Retainer std", "payload": payload})
    assert r.status_code == 201, r.text
    t = r.json()
    items = (await client.get("/v1/templates")).json()["items"]
    assert any(x["id"] == t["id"] for x in items)
    got = (await client.get(f"/v1/templates/{t['id']}"))
    assert got.status_code == 200 and got.json()["payload"]["items"]
    r = await client.delete(f"/v1/templates/{t['id']}")
    assert r.status_code == 204
    assert (await client.get(f"/v1/templates/{t['id']}")).status_code == 403


async def test_template_rejects_unknown_catalog_item(client, pa_org):
    r = await client.post("/v1/templates", json={
        "name": "bad", "payload": {"items": [
            {"catalog_item_id": str(uuid.uuid4()), "arch": "upper"}]}})
    assert r.status_code == 422


async def test_template_lab_cannot_create_and_cannot_see(client, pa_org):
    item = await _catalog_id(client, "HWL")
    t = (await client.post("/v1/templates", json={
        "name": "iso", "payload": {"items": [
            {"catalog_item_id": item, "arch": "upper"}]}})).json()
    await login(client, LAB_ADMIN)
    r = await client.post("/v1/templates", json={
        "name": "lab t", "payload": {"items": []}})
    assert r.status_code == 403
    # lab cannot read a practice-owned template
    assert (await client.get(f"/v1/templates/{t['id']}")).status_code == 403


async def test_template_persists_to_db(client, pa_org, admindb):
    from app.modules.rx.models import RxTemplate
    r = await client.post("/v1/templates", json={
        "name": "dbcheck", "payload": {"items": []}})
    assert r.status_code == 201
    row = (await admindb.execute(select(RxTemplate).where(
        RxTemplate.id == uuid.UUID(r.json()["id"])))).scalar_one()
    assert row.org_id == uuid.UUID(pa_org)
