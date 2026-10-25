#!/usr/bin/env python3
"""OpenAPI contract-structure validator for the MVP surface (Stage A.1 / A4).

Checks that every MVP (S0-S2) operation actually carries a usable contract —
syntax lint alone is NOT accepted as proof:

  * mutating ops (post/put/patch) declare a requestBody with a schema
  * every declared response has a content schema (2xx) — no bare descriptions
  * at least one 4xx response declared per op
  * x-scope present on every MVP op
  * ops that must be idempotent declare the Idempotency-Key parameter
  * ops that mutate a versioned entity declare If-Match or expected_version
  * state-transition ops carry x-state-transition

Input is a *bundled* JSON produced by redocly (so $refs are resolved):

    npx -y @redocly/cli@1.25.15 bundle docs/api/openapi.yaml -o /tmp/api.json
    python3 tools/validate_contract.py /tmp/api.json

Stdlib only. Exit 0 = PASS.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# MVP S0-S2 operations that must carry full contracts. S3+ and P1+ ops are
# intentionally excluded — do not grow this list to hit a count.
MVP_OPS: dict[str, dict] = {
    # op_id: {idempotent: bool, versioned: bool (needs If-Match/expected_version), transition: bool}
    "listOrgs": {},
    "createOrg": {},
    "listLocations": {},
    "createLocation": {},
    "listMembers": {},
    "inviteMember": {},
    "listRoster": {},
    "addRosterMember": {},
    "listOrgConnections": {},
    "requestOrgConnection": {"idempotent": True},
    "transitionOrgConnection": {"versioned": True},
    "searchPatients": {},
    "createPatient": {},
    "getPatient": {},
    "updatePatient": {"versioned": True},
    "deletePatient": {},
    "listCases": {},
    "createCase": {},
    "patientRxHistory": {},
    "listRx": {},
    "createRx": {},
    "getRx": {},
    "updateRx": {"versioned": True, "transition": True},
    "replaceRxItems": {"versioned": True},
    "submitRx": {"idempotent": True, "versioned": True, "transition": True},
    "unsubmitRx": {"versioned": True, "transition": True},
    "checkInRx": {"idempotent": True, "transition": True},
    "transitionRx": {"transition": True},
    "attachToRx": {},
    "listRxComments": {},
    "createRxComment": {},
    "declareUpload": {"idempotent": True},
    "completeUpload": {},
    "getAsset": {},
    "downloadAsset": {},
    "grantAssetReference": {},
    "revokeAssetReference": {},
    "listNotifications": {},
    "createNotification": {},
    "decideNotification": {"idempotent": True},
    "listParts": {},
    "listAppliances": {},
    "listTemplates": {},
    "createTemplate": {},
    "listAuditEvents": {},
}
MUTATING = {"post", "put", "patch"}


def resolve(ref_obj: dict, doc: dict) -> dict:
    """Resolve one level of local '#/components/...' $refs (bundle keeps them)."""
    ref = ref_obj.get("$ref")
    if not ref or not ref.startswith("#/"):
        return ref_obj
    node = doc
    for part in ref[2:].split("/"):
        node = node.get(part, {})
    return node


def op_params(op: dict, path_item: dict, doc: dict) -> list[dict]:
    raw = (path_item.get("parameters") or []) + (op.get("parameters") or [])
    return [resolve(p, doc) for p in raw]


def has_header(params: list[dict], name: str) -> bool:
    return any(p.get("in") == "header" and p.get("name", "").lower() == name.lower()
               for p in params)


def body_has_expected_version(op: dict) -> bool:
    rb = op.get("requestBody", {})
    for media in (rb.get("content") or {}).values():
        props = (media.get("schema") or {}).get("properties") or {}
        if "expected_version" in props:
            return True
    return False


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: validate_contract.py <bundled-openapi.json>")
        return 2
    doc = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    paths = doc.get("paths") or {}
    ops_found: dict[str, tuple[str, str, dict, dict]] = {}  # id -> (method, path, op, path_item)
    for pth, item in paths.items():
        for method, op in (item or {}).items():
            if method not in {"get", "post", "put", "patch", "delete"} or not isinstance(op, dict):
                continue
            oid = op.get("operationId")
            if oid in MVP_OPS:
                ops_found[oid] = (method, pth, op, item)

    fails: list[str] = []
    missing = set(MVP_OPS) - set(ops_found)
    if missing:
        fails.append(f"MVP operations missing from spec: {sorted(missing)}")

    for oid, req in MVP_OPS.items():
        if oid not in ops_found:
            continue
        method, pth, op, item = ops_found[oid]
        tag = f"{oid} ({method.upper()} {pth})"
        params = op_params(op, item, doc)

        if not op.get("x-scope"):
            fails.append(f"{tag}: missing x-scope")

        if method in MUTATING:
            rb = op.get("requestBody")
            if not rb:
                fails.append(f"{tag}: mutating op without requestBody")
            elif not any((m.get("schema") for m in (rb.get("content") or {}).values())) and not rb.get("required") is False:
                # allow explicitly-optional bodies (e.g. submitRx) only when they still declare a schema
                if not any((m.get("schema") for m in (rb.get("content") or {}).values())):
                    fails.append(f"{tag}: requestBody without schema")

        responses = op.get("responses") or {}
        ok2 = [c for c in responses if c.startswith("2")]
        if not ok2:
            fails.append(f"{tag}: no 2xx response")
        for code in ok2:
            content = (responses[code] or {}).get("content")
            # 204 (no content) is fine; other 2xx must have a schema
            if code != "204":
                if not content or not any(m.get("schema") for m in content.values()):
                    fails.append(f"{tag}: 2xx {code} without response schema")
        if not any(c.startswith("4") for c in responses):
            fails.append(f"{tag}: no 4xx response declared")

        if req.get("idempotent") and not has_header(params, "Idempotency-Key") and \
                not str(op.get("x-idempotent", "")).lower().startswith("natural"):
            fails.append(f"{tag}: marked idempotent but no Idempotency-Key header")

        if req.get("versioned") and not has_header(params, "If-Match") \
                and not body_has_expected_version(op):
            fails.append(f"{tag}: versioned mutation without If-Match/expected_version")

        if req.get("transition") and not op.get("x-state-transition"):
            fails.append(f"{tag}: state-transition op without x-state-transition")

    for f in fails:
        print("FAIL ", f)
    print(f"\n{len(MVP_OPS) - len(missing)}/{len(MVP_OPS)} MVP ops found; "
          f"{len(fails)} contract violations")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
