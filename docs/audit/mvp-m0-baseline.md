# M0 Baseline — MVP Completion Audit

Date: 2026-10-27 (UTC) · Branch: `devin/easyrs-full-mvp` · Baseline: `main` @ `47ac3cb5`
(contains audited Core `6dd75954bb994c085b1ecf787f216d042f86f317` via PR #1 merge)

## Method

Code-level audit of all 69 MVP Features (56 CORE + 11 SIMPLIFY + 2 MANUAL from
`docs/backlog/feature-disposition.csv`) against actual routers, models,
migrations, web pages and test files. Status definitions:

- **VERIFIED** — user operation + permission + persistence + error handling +
  automated test evidence all present.
- **PARTIAL** — substantive implementation exists but a required behavior is
  absent (most commonly: API verified, no web UI path for the user operation).
- **MISSING** — no working implementation.
- **BLOCKED** — cannot proceed (none at M0).

Authoritative per-row evidence: `docs/planning/mvp-completion-matrix.csv`.

## Totals

| Status | Count | Feature IDs |
|---|---:|---|
| VERIFIED | 37 | ASSET-001/002/005/008/009, FLOW-005/006/008/009/010, IAM-006/011/012, INT-005/011, LAB-001, PAT-001/003/004/006/008/009, RX-001/002/003/004/006/007/009/013/019/020/021, SAFE-001/002/004/008 |
| PARTIAL | 19 | ASSET-010, COM-001, FLOW-001/002/003/016, IAM-001/002/003/004/007/009/010, PAT-002/005, RX-008, SAFE-003/005/010 |
| MISSING | 13 | ASSET-003, COM-002/004/007, FLOW-011/012/013/014, LAB-002/019, RX-010, SAFE-006/009 |
| BLOCKED | 0 | — |

## Remaining work by milestone (from matrix column `milestone`)

### M1 — Practice side & Rx Studio (13 items)
- Org profile edit + defaults: doctor / location / org-level timezone
  (IAM-001/002/003/004/010) incl. roster & location admin UI.
- Connection request/accept UI (IAM-007), change-password UI (IAM-009).
- Search-as-you-type patient lookup (PAT-002), patient Rx history UI (PAT-005).
- Tooth checkbox/marking UI for `tooth_ops` (RX-008, simplified — no canvas).
- Rx template save/apply, practice-owned (RX-010).
- Three.js STL preview (ASSET-003, basic — no LOD).
- Loading/error/permission-denied states across new pages.

### M2 — Lab communication, approvals & completion (4 items)
- Structured issue notifications + approval-requested notifications
  (COM-002/004, E2E-09); lab issue review loop (LAB-002).
- Message center + todo counts (COM-007).
- Attachment-level discussion on Rx comments (COM-001 gap).
- Approval bound to explicit Rx version; stale approval invalidation.
- FLOW-016 gains approval/notification events (partial → full).

### M3 — Fulfillment & delivery loop (7 items)
- Lab Complete (FLOW-011) with manual QC confirmation record.
- Shipped + manual carrier/tracking (FLOW-012 MANUAL), manual
  receive/dispatch (LAB-019 MANUAL), receive ≠ deliver (FLOW-013, E2E-10).
- Dashboards for both realms (FLOW-001 UI), UI filters status/date/lab
  (FLOW-002/003), fixed due-soon highlight (FLOW-014).
- Full lifecycle history already append-only via `rx_transition`
  (FLOW-016 extension to fulfillment events).

### M4 — Security, ops & data protection (5 items)
- Pluggable AV-engine config flag + doc (ASSET-010/SAFE-005 gap).
- TLS/at-rest deployment evidence section (SAFE-003).
- PG + S3 backup scripts + **actual restore drill** with hash verification
  (SAFE-006, E2E-16).
- Admin JSON + file export skeleton (SAFE-009).
- Deploy/upgrade/rollback runbook + prod config checklist (SAFE-010);
  README status refresh.

## Deferred (not in the 69 — recorded for honesty)
IAM-005, IAM-008, RX-011 → P1; 95 NOT_IN_MVP features excluded.

## E2E-01..16 mapping (for M5 gate)
- E2E-01 create Rx w/ doctor/location/lab/due — exists (`rx.spec.ts`)
- E2E-02 draft save/restore — exists
- E2E-03 tenant isolation — exists (test_isolation.py + e2e)
- E2E-04 connection-gated submit — exists
- E2E-05 unsubmit → saved — exists
- E2E-06 check-in blocks unsubmit — exists
- E2E-07 submit idempotency — exists
- E2E-08 attachment hash/jaw/version — exists
- E2E-09 notification→approval→revision→audit — **to build (M2)**
- E2E-10 receive ≠ deliver, actor/time correct — **to build (M3)**
- E2E-11 PDF re-generatable — exists (bundle tests)
- E2E-12 resumable upload, no half-file — exists (upload session tests)
- E2E-13/14 sharing-scope & revoked access — covered via access_grant
  revocation + template copy isolation where applicable (template sharing
  itself is DEFER; grant-expiry path to be evidenced in M4)
- E2E-15 optimistic-lock conflict 409 — exists
- E2E-16 backup→restore hash-verified drill — **to build (M4)**
