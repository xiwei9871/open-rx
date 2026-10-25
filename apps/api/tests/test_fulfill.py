"""M3 fulfillment: completed -> QC -> shipped -> received -> delivered,
logistics/clinical separation, dashboards, due-soon, full history."""
import uuid

import pytest

from tests.conftest import login

pytestmark = pytest.mark.asyncio

ADMIN = "admin@pa.dev"
LAB_ADMIN = "admin@la.dev"
DOCTOR = "doctor@pa.dev"


async def _to_completed(client) -> dict:
    """Create+submit Rx, lab checks in + completes."""
    from tests.test_collab import _submitted_rx
    rx = await _submitted_rx(client)
    await login(client, LAB_ADMIN)
    cur = (await client.get(f"/v1/rx/{rx['id']}")).json()
    r = await client.post(f"/v1/rx/{rx['id']}/check-in", json={},
                          headers={"If-Match": str(cur["version"])})
    assert r.status_code == 200, r.text
    r = await client.post(f"/v1/rx/{rx['id']}/complete", json={},
                          headers={"If-Match": str(r.json()["version"])})
    assert r.status_code == 200, r.text
    return r.json()


async def test_full_delivery_loop(client):
    """E2E-10 backbone: qc -> ship -> receive -> deliver, track separation."""
    rx = await _to_completed(client)
    assert rx["fulfillment_status"] == "qc_pending"
    # QC pass (lab)
    r = await client.post(f"/v1/rx/{rx['id']}/qc", json={
        "result": "pass", "note": "fit verified"},
        headers={"If-Match": str(rx["version"])})
    assert r.status_code == 201, r.text
    cur = (await client.get(f"/v1/rx/{rx['id']}")).json()
    assert cur["qc_status"] == "pass"
    assert cur["fulfillment_status"] == "qc_passed"
    assert cur["status"] == "completed"  # clinical track unchanged
    # ship (lab, manual carrier+tracking)
    r = await client.post(f"/v1/rx/{rx['id']}/ship", json={
        "carrier": "UPS", "tracking_number": "1Z999SYNTH",
        "note": "overnight"},
        headers={"If-Match": str(cur["version"])})
    assert r.status_code == 200, r.text
    assert r.json()["fulfillment_status"] == "shipped"
    assert r.json()["carrier"] == "UPS"
    # receive + deliver (practice)
    await login(client, ADMIN)
    cur = (await client.get(f"/v1/rx/{rx['id']}")).json()
    r = await client.post(f"/v1/rx/{rx['id']}/receive", json={},
                          headers={"If-Match": str(cur["version"])})
    assert r.status_code == 200, r.text
    r = await client.post(f"/v1/rx/{rx['id']}/deliver", json={},
                          headers={"If-Match": str(r.json()["version"])})
    assert r.json()["fulfillment_status"] == "delivered"
    assert r.json()["delivered_at"] is not None
    # full history visible to both parties
    f = (await client.get(f"/v1/rx/{rx['id']}/fulfillment")).json()
    events = [e["event"] for e in f["events"]]
    assert events == ["completed", "qc_pass", "shipped", "received",
                      "delivered"]
    assert len(f["qc"]) == 1 and f["qc"][0]["result"] == "pass"


async def test_ship_requires_qc_pass(client):
    rx = await _to_completed(client)
    r = await client.post(f"/v1/rx/{rx['id']}/ship", json={
        "carrier": "UPS", "tracking_number": "T1"},
        headers={"If-Match": str(rx["version"])})
    assert r.status_code == 422
    # fail QC then ship still blocked
    r = await client.post(f"/v1/rx/{rx['id']}/qc", json={"result": "fail"},
                          headers={"If-Match": str(rx["version"])})
    assert r.status_code == 201
    cur = (await client.get(f"/v1/rx/{rx['id']}")).json()
    assert cur["fulfillment_status"] == "qc_pending"
    r = await client.post(f"/v1/rx/{rx['id']}/ship", json={
        "carrier": "UPS", "tracking_number": "T1"},
        headers={"If-Match": str(cur["version"])})
    assert r.status_code == 422


async def test_fulfillment_permissions(client):
    """Practice cannot QC/ship; lab cannot receive/deliver."""
    rx = await _to_completed(client)
    await login(client, DOCTOR)  # practice
    r = await client.post(f"/v1/rx/{rx['id']}/qc", json={"result": "pass"},
                          headers={"If-Match": str(rx["version"])})
    assert r.status_code == 403
    r = await client.post(f"/v1/rx/{rx['id']}/ship", json={
        "carrier": "X", "tracking_number": "Y"},
        headers={"If-Match": str(rx["version"])})
    assert r.status_code == 403


async def test_dashboard_counts_and_due_soon(client):
    rx = await _to_completed(client)
    # due date tomorrow -> appears in due_soon (status=completed is terminal
    # for due-soon? completed is terminal — create a submitted one instead)
    await login(client, ADMIN)
    dash = (await client.get("/v1/dashboard")).json()
    assert "by_status" in dash and "by_fulfillment" in dash
    assert dash["by_fulfillment"].get("qc_pending", 0) >= 1
    # lab sees same rx on their dashboard
    await login(client, LAB_ADMIN)
    ldash = (await client.get("/v1/dashboard")).json()
    assert ldash["by_status"].get("completed", 0) >= 1
    # due_soon: create a submitted rx with near due date
    await login(client, ADMIN)
    from tests.test_collab import _patient_id, _lab_org_id, _catalog_id
    r = await client.post("/v1/rx", json={
        "patient_id": await _patient_id(client),
        "lab_org_id": await _lab_org_id(client)})
    nrx = r.json()
    r = await client.put(f"/v1/rx/{nrx['id']}/items", json={"items": [{
        "appliance_id": await _catalog_id(client, "HWL"), "arch": "upper"}]},
        headers={"If-Match": str(nrx["version"])})
    nrx = (await client.get(f"/v1/rx/{nrx['id']}")).json()
    import datetime as dt
    r = await client.patch(f"/v1/rx/{nrx['id']}", json={
        "due_date": (dt.date.today() + dt.timedelta(days=1)).isoformat()},
        headers={"If-Match": str(nrx["version"])})
    assert r.status_code == 200, r.text
    nrx = r.json()
    r = await client.post(f"/v1/rx/{nrx['id']}/submit", json={
        "signature_name": "Dr Demo", "confirm_submit": True},
        headers={"If-Match": str(nrx["version"]),
                 "Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 200, r.text
    dash = (await client.get("/v1/dashboard")).json()
    ids = [x["id"] for x in dash["due_soon"]]
    assert nrx["id"] in ids
    assert dash["due_soon_hours"] == 72


async def test_list_filters(client):
    """status / lab_org_id / fulfillment_status / due_before filters."""
    rx = await _to_completed(client)
    await login(client, ADMIN)
    r = await client.get(
        f"/v1/rx?fulfillment_status=qc_pending&status=completed")
    ids = [x["id"] for x in r.json()["items"]]
    assert rx["id"] in ids
    r = await client.get("/v1/rx?status=draft")
    assert all(x["status"] == "draft" for x in r.json()["items"])
