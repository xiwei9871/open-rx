#!/usr/bin/env python3
"""Feature-level MVP disposition — single source of truth (Stage A.1 / A5).

Every one of the 167 features gets exactly ONE primary disposition:

  CORE        — built in MVP per acceptance criteria
  SIMPLIFY    — built in MVP with explicitly reduced scope (reduction named)
  MANUAL      — capability delivered via manual operation in MVP
  DEFER       — research-MVP feature moved out of the MVP release
  NOT_IN_MVP  — research phase P1/P2/P3; never an MVP-phase candidate
                (derived — not listed here; anything not in DISPOSITIONS)

Optional `labels` attach implementation-method notes (e.g. security-critical,
partial scope, incidental task coverage). Labels never replace the primary
disposition. `detail` records the reduction / deferral target / manual
substitute — a disposition without its detail is invalid.

The mapping below normalizes docs/planning/mvp-release-plan.md §2, whose
multi-label scheme (CORE+SIMPLIFY, KEEP-SEC+SIMPLIFY, SIMPLIFY/DEFER) is why
the old 55/5/3 summary never reconciled to 72. KEEP-SEC → CORE + label
"security-critical"; "CORE + MANUAL" → MANUAL; "SIMPLIFY/DEFER" partial ships
→ SIMPLIFY. Reconciliation vs the old summary is documented in
docs/backlog/feature-disposition.csv (generated) and mvp-scope.md.
"""
from __future__ import annotations

# feature_id -> (primary_disposition, labels, detail)
DISPOSITIONS: dict[str, tuple[str, list[str], str]] = {
    # ---------------- IAM (12) ----------------
    "IAM-001": ("CORE", [], "org profile — foundation"),
    "IAM-002": ("CORE", [], "multi-location; ship-to depends on it"),
    "IAM-003": ("CORE", [], "doctor list + default — Rx required attribution"),
    "IAM-004": ("CORE", [], "staff roster — submitter attribution"),
    "IAM-005": ("DEFER", ["target:P1"], "staff-required toggles; MVP hard-codes doctor-required"),
    "IAM-006": ("CORE", [], "staff login"),
    "IAM-007": ("CORE", [], "practice-lab connection — E2E-04 path"),
    "IAM-008": ("DEFER", ["target:P1"], "lab template sharing; MVP = practice-built templates only"),
    "IAM-009": ("CORE", ["security-critical"], "password management"),
    "IAM-010": ("SIMPLIFY", [], "org-level timezone only; per-user switching deferred"),
    "IAM-011": ("CORE", ["security-critical"], "least-privilege matrix (was KEEP-SEC)"),
    "IAM-012": ("CORE", ["security-critical"], "2FA + access audit (was KEEP-SEC)"),
    # ---------------- PAT (8) ----------------
    "PAT-001": ("CORE", [], "patient registration"),
    "PAT-002": ("CORE", [], "search-as-you-type / duplicate hint"),
    "PAT-003": ("CORE", [], "external_ref — migration key"),
    "PAT-004": ("CORE", [], "dob duplicate-name disambiguation (display only)"),
    "PAT-005": ("CORE", [], "patient rx history"),
    "PAT-006": ("SIMPLIFY", [], "patient-side attachment entry reduced; Rx-side is primary"),
    "PAT-008": ("CORE", [], "treatment case entity"),
    "PAT-009": ("CORE", ["security-critical"], "soft delete + retention (was KEEP-SEC)"),
    # ---------------- RX (14) ----------------
    "RX-001": ("CORE", [], "create entry"),
    "RX-002": ("CORE", [], "doctor/location/lab/due-date — E2E-01"),
    "RX-003": ("CORE", [], "unique rx number"),
    "RX-004": ("CORE", [], "draft — E2E-02"),
    "RX-006": ("SIMPLIFY", [], "curated starter catalog (tens), not 500+ (GAP-04)"),
    "RX-007": ("SIMPLIFY", [], "appliance library seeded from curated parts only"),
    "RX-008": ("SIMPLIFY", ["target:P1"], "tooth checkbox/marking instead of drag canvas; canvas -> P1"),
    "RX-009": ("CORE", [], "part options"),
    "RX-010": ("CORE", [], "template save/apply"),
    "RX-011": ("DEFER", ["target:P1"], "template-source kinds depend on IAM-008 sharing"),
    "RX-013": ("CORE", [], "free text"),
    "RX-019": ("CORE", [], "attachments on rx"),
    "RX-020": ("CORE", [], "checkout/submit — E2E-07 idempotent"),
    "RX-021": ("CORE", [], "rx PDF export — E2E-11"),
    # ---------------- FLOW (13) ----------------
    "FLOW-001": ("CORE", [], "dashboard + counts"),
    "FLOW-002": ("CORE", [], "date/status filters"),
    "FLOW-003": ("SIMPLIFY", [], "filter subset (status/date/lab); full multi-dim -> P1"),
    "FLOW-005": ("CORE", [], "saved/submitted lists"),
    "FLOW-006": ("CORE", [], "check-in"),
    "FLOW-008": ("CORE", [], "unsubmit blocked after check-in — SRC24"),
    "FLOW-009": ("CORE", [], "unsubmit returns to saved — E2E-05"),
    "FLOW-010": ("CORE", [], "post-submit manual attach — SRC24"),
    "FLOW-011": ("CORE", [], "complete"),
    "FLOW-012": ("MANUAL", [], "carrier/tracking no. entered by hand; no carrier API"),
    "FLOW-013": ("CORE", [], "receive/deliver — E2E-10"),
    "FLOW-014": ("SIMPLIFY", ["target:P1"], "fixed due-soon threshold; configurable -> P1"),
    "FLOW-016": ("CORE", ["security-critical"], "version/approval event log (was KEEP-SEC)"),
    # ---------------- COM (4) ----------------
    "COM-001": ("CORE", [], "comments"),
    "COM-002": ("CORE", [], "clinical notifications"),
    "COM-004": ("CORE", [], "approval-required notification — E2E-09"),
    "COM-007": ("CORE", [], "message center"),
    # ---------------- ASSET (7) ----------------
    "ASSET-001": ("CORE", [], "STL upload + jaw"),
    "ASSET-002": ("CORE", [], "original/optimized distinction — version chain"),
    "ASSET-003": ("SIMPLIFY", ["target:P1"], "basic Three.js preview; large-mesh LOD -> P1"),
    "ASSET-005": ("CORE", [], "cross-context file access via references"),
    "ASSET-008": ("CORE", ["security-critical"], "hash dedup (was KEEP-SEC)"),
    "ASSET-009": ("CORE", ["security-critical"], "immutable version chain (was KEEP-SEC)"),
    "ASSET-010": ("SIMPLIFY", ["security-critical"], "type/size/mesh sanity mandatory; AV engine pluggable"),
    # ---------------- LAB (3) ----------------
    "LAB-001": ("CORE", [], "check-in / accept"),
    "LAB-002": ("CORE", [], "issue review via approval loop"),
    "LAB-019": ("MANUAL", [], "manual receive/dispatch registration; no carrier API"),
    # ---------------- INT (2) ----------------
    "INT-005": ("CORE", [], "generic scanner import via asset pipeline — the ONLY MVP integration"),
    "INT-011": ("SIMPLIFY", ["target:P1"], "internal v1 API contract exists; public webhook subscribe -> P1"),
    # ---------------- SAFE (9) ----------------
    "SAFE-001": ("CORE", ["security-critical"], "audit + signature attribution"),
    "SAFE-002": ("CORE", ["security-critical"], "tenant isolation"),
    "SAFE-003": ("CORE", ["security-critical"], "encryption at rest/in transit"),
    "SAFE-004": ("CORE", ["security-critical"], "time-boxed download links"),
    "SAFE-005": ("CORE", ["security-critical"], "upload limits + scan"),
    "SAFE-006": ("CORE", ["security-critical"], "backup + restore drill — E2E-16"),
    "SAFE-008": ("CORE", ["security-critical"], "synthetic data only — zero PHI"),
    "SAFE-009": ("SIMPLIFY", ["target:post-MVP-iter1"], "admin JSON+file export skeleton; full migration tool later (GAP-09)"),
    "SAFE-010": ("CORE", ["security-critical"], "compliance deploy baseline"),
}

VALID_PRIMARY = {"CORE", "SIMPLIFY", "MANUAL", "DEFER", "NOT_IN_MVP"}


def disposition_table(feats: dict[str, dict]) -> tuple[list[dict], list[str]]:
    """Return (rows, errors) for all features.

    Rows: {feature_id, phase, primary_disposition, labels, detail}.
    Errors: any MVP-phase feature missing a decision, a decision assigned to a
    non-MVP feature, or a disallowed primary value.
    """
    errs = []
    rows = []
    for fid, r in feats.items():
        phase = r["phase"]
        if phase == "MVP":
            if fid not in DISPOSITIONS:
                errs.append(f"{fid}: MVP-phase feature missing disposition")
                continue
            prim, labels, detail = DISPOSITIONS[fid]
            if prim not in VALID_PRIMARY - {"NOT_IN_MVP"}:
                errs.append(f"{fid}: invalid primary {prim}")
            if prim in {"SIMPLIFY", "DEFER", "MANUAL"} and not detail:
                errs.append(f"{fid}: {prim} requires detail")
            rows.append({"feature_id": fid, "phase": phase,
                         "primary_disposition": prim,
                         "labels": ";".join(labels), "detail": detail})
        else:
            if fid in DISPOSITIONS:
                errs.append(f"{fid}: disposition assigned to {phase} feature")
            rows.append({"feature_id": fid, "phase": phase,
                         "primary_disposition": "NOT_IN_MVP",
                         "labels": "", "detail": ""})
    return rows, errs
