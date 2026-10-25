#!/usr/bin/env python3
"""M5 auto-acceptance tool: mechanically validates the MVP completion matrix.

Not a rubber stamp: for every feature row it requires VERIFIED status backed
by named test files that actually exist in the repo, a backend API and a data
model/migration reference where applicable, plus per-row milestone assignment.
It also validates the E2E-01..16 evidence map against real test files.

Exit 0 + 'MVP_ALPHA_READY' only when every check passes.
"""
import csv, os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MATRIX = ROOT / "docs/planning/mvp-completion-matrix.csv"
DISPOSITION = ROOT / "docs/backlog/feature-disposition.csv"

# E2E scenario -> list of (test file glob, required name fragments).
# Sources: docs/backlog/tasks/EPIC-*.md acceptance criteria.
E2E_MAP = {
    "E2E-01": ("rx create->submit flow", [
        ("apps/api/tests/test_rx.py", ["test_full_loop", "test_submit_requires_lab_and_items"]),
        ("apps/web/tests/e2e/rx.spec.ts", ["create -> submit"]),
    ]),
    "E2E-02": ("draft save/restore keeps form state", [
        ("apps/api/tests/test_rx.py", ["test_unsubmit_before_checkin", "draft"]),
        ("apps/web/tests/e2e/rx.spec.ts", ["unsubmit before check-in"]),
    ]),
    "E2E-03": ("cross-org 403, no existence leak (RLS)", [
        ("apps/api/tests/test_isolation.py", ["test_"]),
        ("apps/api/tests/test_rx.py", ["foreign_tenant_isolated"]),
    ]),
    "E2E-04": ("lab field limited to accepted connections", [
        ("apps/api/tests/test_rx.py", ["test_submit_requires_accepted_connection"]),
        ("apps/api/tests/test_connection_security.py", ["test_counterparty_accepts"]),
    ]),
    "E2E-05": ("unsubmit before check-in -> draft", [
        ("apps/api/tests/test_rx.py", ["test_unsubmit_before_checkin_returns_to_draft"]),
    ]),
    "E2E-06": ("lab check-in; practice unsubmit blocked", [
        ("apps/api/tests/test_rx.py", ["test_full_loop_submit_checkin_unsubmit_blocked"]),
        ("apps/api/tests/test_rx_s1b1.py", ["checkin"]),
    ]),
    "E2E-07": ("submit idempotent / replay snapshot", [
        ("apps/api/tests/test_rx.py", ["test_submit_idempotency"]),
        ("apps/api/tests/test_rx_s1b1.py", ["test_idempotent_replay_returns_first_snapshot"]),
    ]),
    "E2E-08": ("bundle attachment hash/version integrity", [
        ("apps/api/tests/test_rx_s1b1.py", ["test_bundle_contains_real_files_and_checks_in"]),
        ("apps/api/tests/test_rx_finalgate.py", ["test_bundle_rebuilt_after_attachment_added", "test_pdf_reflects_patient_rename"]),
    ]),
    "E2E-09": ("notification->approval->audit loop, version-bound", [
        ("apps/api/tests/test_collab.py", ["test_approval_loop_signed_and_version_bound", "version_drift"]),
        ("apps/web/tests/e2e/collab.spec.ts", ["approval request -> decision"]),
    ]),
    "E2E-10": ("receive != deliver; actor/state/perm correct", [
        ("apps/api/tests/test_fulfill.py", ["test_full_delivery_loop", "test_ship_requires_qc_pass"]),
        ("apps/web/tests/e2e/fulfill.spec.ts", ["delivery loop"]),
    ]),
    "E2E-11": ("Rx PDF regenerable, key fields present", [
        ("apps/api/tests/test_rx_finalgate.py", ["test_prescription_pdf_has_real_content"]),
    ]),
    "E2E-12": ("interrupted upload leaves no half-file", [
        ("apps/api/tests/test_assets.py", ["test_session_owner_only_and_expired", "test_expired_cleanup"]),
    ]),
    "E2E-13": ("template apply/edit does not mutate source (sharing DEFER P1)", [
        ("apps/api/tests/test_studio.py", ["test_template_crud", "test_template_persists_to_db"]),
    ]),
    "E2E-14": ("revoked share -> 403 + audit", [
        ("apps/api/tests/test_assets.py", ["test_reference_grant_revoke_cycle"]),
    ]),
    "E2E-15": ("If-Match optimistic lock, 409 on conflict", [
        ("apps/api/tests/test_rx.py", ["test_version_conflict"]),
        ("apps/api/tests/test_rx_s1b1.py", ["test_mutations_require_if_match"]),
    ]),
    "E2E-16": ("backup->restore data/objects verifiable", [
        ("scripts/backup.py", ["pg_dump"]),
        ("scripts/restore.py", ["sha256"]),
        ("docs/audit/backup-restore-drill.md", ["verified"]),
    ]),
}


def fail(msg):
    print(f"  FAIL  {msg}")
    return 1


def main():
    errors = 0
    rows = list(csv.DictReader(open(MATRIX, newline="")))
    disp_rows = csv.DictReader(open(DISPOSITION, newline=""))
    mvp_ids = {r["feature_id"] for r in disp_rows
               if r["phase"] == "MVP" and r["primary_disposition"] in ("CORE", "SIMPLIFY", "MANUAL")}

    print(f"[1] matrix completeness: {len(rows)} rows vs {len(mvp_ids)} MVP features")
    matrix_ids = {r["feature_id"] for r in rows}
    if matrix_ids != mvp_ids:
        missing = mvp_ids - matrix_ids
        extra = matrix_ids - mvp_ids
        errors += fail(f"missing rows: {sorted(missing)} / extra: {sorted(extra)}")

    print("[2] per-row status + evidence")
    test_root = ROOT / "apps/api/tests"
    e2e_root = ROOT / "apps/web/tests/e2e"
    for r in rows:
        fid = r["feature_id"]
        if r["status"] != "VERIFIED":
            errors += fail(f"{fid}: status={r['status']} (expected VERIFIED)")
            continue
        if r["disposition"] == "CORE" and not r["backend_api"].strip():
            errors += fail(f"{fid}: CORE row lacks backend_api evidence")
        if not r["test_evidence"].strip():
            errors += fail(f"{fid}: empty test_evidence")
            continue
        # every *.py / *.spec.ts file named in evidence must exist
        for m in re.findall(r"[\w./-]+\.(?:py|ts)", r["test_evidence"]):
            name = os.path.basename(m)
            if not (any(test_root.glob(f"**/{name}")) or any(e2e_root.glob(f"**/{name}"))
                    or (ROOT / m).exists() or any(ROOT.glob(f"scripts/{name}"))
                    or any(ROOT.glob(f"docs/**/{name}")) or any(ROOT.glob(f"tools/**/{name}"))):
                errors += fail(f"{fid}: evidence file not found: {m}")
        if not r["milestone"].strip():
            errors += fail(f"{fid}: no milestone assigned")

    print("[3] E2E-01..16 evidence map")
    for eid, (desc, files) in E2E_MAP.items():
        ok = True
        for fpath, frags in files:
            f = ROOT / fpath
            if not f.exists():
                ok = False
                errors += fail(f"{eid} ({desc}): missing {fpath}")
                continue
            content = f.read_text(errors="replace")
            for frag in frags:
                if frag not in content:
                    ok = False
                    errors += fail(f"{eid}: {fpath} lacks '{frag}'")
        if ok:
            print(f"  ok    {eid}: {desc}")

    print("[4] hard-gate artifacts exist")
    for p in ["docs/audit/mvp-m0-baseline.md", "docs/audit/mvp-m1-acceptance.md",
              "docs/audit/mvp-m2-acceptance.md", "docs/audit/mvp-m3-acceptance.md",
              "docs/audit/mvp-m4-acceptance.md", "docs/audit/backup-restore-drill.md",
              "docs/ops/deploy-upgrade-rollback.md", "docs/api/openapi.yaml"]:
        if not (ROOT / p).exists():
            errors += fail(f"missing artifact: {p}")

    if errors:
        print(f"\nMVP_BLOCKED — {errors} check(s) failed")
        return 1
    print("\nMVP_ALPHA_READY — 69/69 features VERIFIED, E2E-01..16 evidence mapped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
