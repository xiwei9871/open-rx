"""API contract consistency — implemented operationIds vs the spec
(docs/api/openapi.yaml). B0 implements a subset; the rule is:

  * every REQUIRED spec op must be implemented
  * every implemented op must exist in the spec OR be in EXTRA_AUTH_OPS
    (auth endpoints pending a spec update — kept explicit, not silent)
"""
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.asyncio

SPEC = Path(__file__).resolve().parents[3] / "docs" / "api" / "openapi.yaml"

REQUIRED_SPEC_OPS = {
    "healthz", "listOrgs", "createOrg", "listLocations", "createLocation",
    "listMembers", "inviteMember", "listRoster", "addRosterMember",
    "listOrgConnections", "requestOrgConnection", "transitionOrgConnection",
    "listAuditEvents",
    # S1a: patients / cases / assets
    "searchPatients", "createPatient", "getPatient", "updatePatient",
    "deletePatient", "listCases", "createCase", "listPatientAssets",
    "declareUpload", "completeUpload", "getAsset", "downloadAsset",
    "grantAssetReference", "revokeAssetReference",
    # S1b-Core: rx lifecycle loop
    "listRx", "createRx", "getRx", "updateRx", "replaceRxItems",
    "submitRx", "unsubmitRx", "checkInRx", "downloadRxBundle",
    "listRxBundles",
    "attachToRx", "listRxAttachments", "listRxComments", "createRxComment",
    "listRxTransitions",
    "patientRxHistory", "listParts", "listAppliances",
    # M1: org admin + templates
    "updateOrg", "updateLocation", "updateRosterMember",
    "listTemplates", "createTemplate", "getTemplate", "deleteTemplate",
    # M2: notifications / approvals
    "listNotifications", "createNotification", "markNotificationRead",
    "decideNotification", "completeRx",
    # M3: fulfillment
    "recordRxQc", "shipRx", "receiveRx", "deliverRx", "getRxFulfillment",
    "rxDashboard",
}
EXTRA_AUTH_OPS = {
    "login", "verifyTwoFA", "logout", "me",
    "setupTwoFA", "enableTwoFA", "changePassword",
}


def spec_ops() -> set[str]:
    doc = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    ops = set()
    for item in (doc.get("paths") or {}).values():
        for op in (item or {}).values():
            if isinstance(op, dict) and op.get("operationId"):
                ops.add(op["operationId"])
    return ops


def impl_ops() -> set[str]:
    from app.main import app
    return {r.operation_id for r in app.routes
            if getattr(r, "operation_id", None)}


async def test_required_ops_implemented():
    missing = REQUIRED_SPEC_OPS - impl_ops()
    assert not missing, f"spec ops not implemented: {missing}"


async def test_implemented_ops_declared():
    undeclared = impl_ops() - spec_ops() - EXTRA_AUTH_OPS
    assert not undeclared, f"implemented but not in spec/extras: {undeclared}"


async def test_no_extra_spec_ops_implemented_under_wrong_name():
    """Drift guard: spec ops that ARE in B0 scope must map 1:1 by name."""
    assert impl_ops() & spec_ops() == REQUIRED_SPEC_OPS & impl_ops()
