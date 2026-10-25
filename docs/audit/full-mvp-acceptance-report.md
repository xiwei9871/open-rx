# Full MVP Acceptance Report — EasyRS Alpha

Date: 2026-10-25 · Branch: `devin/easyrs-full-mvp` · Scope: 69 MVP features
(56 CORE + 11 SIMPLIFY + 2 MANUAL per `docs/backlog/feature-disposition.csv`;
3 DEFER + 95 NOT_IN_MVP out of scope)

## Verdict: MVP_ALPHA_READY

Authoritative evidence: `tools/mvp_acceptance.py` — a mechanical gate that
fails unless every one of the 69 matrix rows is VERIFIED with existing test
files, API/model references and milestone assignment, and every E2E-01..16
scenario maps to real test files. Runs in CI job `validate`.

## Feature completion

| Status | Count |
|---|---|
| VERIFIED | 69/69 |

Matrix: `docs/planning/mvp-completion-matrix.csv` (per-row API, page,
migration, test evidence, milestone).

## Milestone acceptance docs

- `docs/audit/mvp-m0-baseline.md` — code-level audit baseline
- `docs/audit/mvp-m1-acceptance.md` — practice admin + Rx Studio
- `docs/audit/mvp-m2-acceptance.md` — lab collaboration/approvals/complete
- `docs/audit/mvp-m3-acceptance.md` — fulfillment loop
- `docs/audit/mvp-m4-acceptance.md` — security/ops/data protection
- `docs/audit/backup-restore-drill.md` — E2E-16 drill record

## E2E-01..16 evidence map (enforced by tools/mvp_acceptance.py)

| ID | Scenario | Evidence |
|---|---|---|
| E2E-01 | Rx create→submit full flow | test_rx.py, e2e rx.spec.ts |
| E2E-02 | draft save/restore — real logout→login re-open | test_rx.py; e2e rx.spec.ts "draft persists across logout and fresh login" (browser-verified) |
| E2E-03 | cross-org 403 (RLS) | test_isolation.py, test_rx.py |
| E2E-04 | lab=accepted connection only | test_rx.py, test_connection_security.py |
| E2E-05 | unsubmit before check-in | test_rx.py |
| E2E-06 | lab check-in blocks unsubmit | test_rx.py, test_rx_s1b1.py |
| E2E-07 | submit idempotency | test_rx.py, test_rx_s1b1.py |
| E2E-08 | bundle attachment integrity | test_rx_s1b1.py, test_rx_finalgate.py |
| E2E-09 | notify→approve→audit loop | test_collab.py, e2e collab.spec.ts |
| E2E-10 | receive≠deliver lifecycle | test_fulfill.py, e2e fulfill.spec.ts |
| E2E-11 | PDF regen w/ key fields | test_rx_finalgate.py (pypdf text assert) |
| E2E-12 | interrupted upload → no half-file | test_assets.py::test_interrupted_upload_leaves_no_half_file (real S3: partial PUT → complete 422, 0 asset rows, staging object reaped) |
| E2E-13 | template apply→edit does not mutate source* | test_studio.py::test_template_apply_edit_does_not_mutate_source (*lab sharing DEFER P1) |
| E2E-14 | revoked share → 403+audit | test_assets.py |
| E2E-15 | If-Match 409 concurrency | test_rx.py, test_rx_s1b1.py |
| E2E-16 | backup→restore w/ baseline compare | scripts/backup.py expected_counts + restore.py fail-on-mismatch; drill-2: 11/11 tables + 366/366 objects verified; tampered manifest → DRILL FAILED exit 1 |

## Test totals (latest local run)

| Suite | Result |
|---|---|
| API full | 146 passed, 6 skipped (local non-S3 gate) |
| Contract | 3 passed |
| Playwright | 15 passed (auth/patients/rx/studio/collab/fulfill incl. real logout→login draft persistence) |
| mvp_acceptance.py | MVP_ALPHA_READY |
| Backup/restore drill | 321/321 S3 objects hash-verified; row counts restored |

CI `asset-integration` hard gate runs test_assets.py + test_rx_s1b1.py +
test_rx_finalgate.py + test_collab.py + test_m4.py against real
Postgres+RustFS with `skipped=0` enforced — covers the M2 attachment-anchored
comment test and the M4 AV-hook + export-URL tests on real infrastructure.

## Explicit non-claims

- Alpha ≠ production medical clearance; synthetic data only.
- E2E-13 lab-side template sharing is DEFER'd (IAM-008/RX-011, target P1);
  the in-scope part (copy-edit isolation) is verified.
- No carrier APIs, no AI features, no billing — intentionally absent.
- Presigned URLs rely on short TTL; one-time tokens are future hardening.

## Residual risks / P1 backlog

- Template sharing across orgs (IAM-008), template source kinds (RX-011),
  delegated user admin detail (IAM-005) — all DEFER'd by disposition.
- Restore drill verifies object hashes + table counts; row-level hash diff
  is hardening, not a blocker.
- Anti-virus engine ships as `none|eicar_stub` ONLY — a hook + negative-path
  test, not real malware scanning, not a security certification.
