# MVP M3 Acceptance — Fulfillment & delivery loop

Date: 2026-10-25 · Branch: `devin/easyrs-full-mvp` · Scope: M3 only

## End-to-end loop now live

`patient intake -> Rx create -> STL upload -> sign+submit -> lab check-in
-> issue/approval -> complete -> QC pass -> shipped -> received -> delivered`

Verified in a real browser by `apps/web/tests/e2e/fulfill.spec.ts`
(E2E-10 backbone) and `test_fulfill.py` against real Postgres.

## Features verified in this milestone

| Feature | Evidence |
|---|---|
| FLOW-011 complete | `POST /rx/{id}/complete` — lab-only, checked_in→completed, fulfillment track opens at `qc_pending` |
| FLOW-012 manual carrier/tracking | `POST /rx/{id}/ship` requires carrier + tracking number (typed by hand, no carrier API), QC pass gated |
| FLOW-013 receive/deliver (E2E-10) | `POST /rx/{id}/receive` + `/deliver` — practice-only, idempotent, shipped→received→delivered |
| FLOW-014 due-soon | `GET /dashboard` returns `due_soon` (fixed 72h threshold) + `due_soon_hours`; RxList banner + `due_before` filter |
| FLOW-016 event log | `rx_transition` (clinical, seq-ordered) + `fulfillment_event` (logistics, seq-ordered) + `qc_record`; approvals also land in the transition trail (`via=approval`) |
| LAB-019 manual receive/dispatch | ship/receive/deliver endpoints are manual registrations; party-split permissions verified |
| FLOW-001 dashboards | `GET /dashboard` by_status + by_fulfillment + due_soon; UI strip on RxList for lab and practice |
| FLOW-002/003 filters | `GET /rx` gains `lab_org_id`, `fulfillment_status`, `due_before`; RxList exposes status/fulfillment/due controls |

## Logistics vs clinical separation

`rx.status` (clinical) and `rx.fulfillment_status` (logistics) are separate
columns with separate trails. `complete` flips clinical to `completed` and
opens logistics at `qc_pending`; QC `pass` → `qc_passed`; `ship` requires
`qc_passed`. A failing QC record returns the track to `qc_pending`.
Check constraint `ck_rx_fulfillment` widened in migration 0011 — all 0005
values remain valid (no rewrite of accepted history).

## Test evidence

- `tests/test_fulfill.py`: **5 passed** — full loop, QC gate (ship blocked
  before pass and after fail), party permission split, dashboard counts +
  due-soon, list filters.
- `tests/test_collab.py` extended: `test_lab_complete_and_practice_cannot`.
- Full API suite: **135 passed / 6 skipped** (local S3-gated skips only).
- Playwright `fulfill.spec.ts` **1 passed**; suite **14/14** (one timing
  flake on parallel run, passed solo).
- `tsc --noEmit` + `npm run build` clean.

## Remaining defects / follow-up

- One parallel-run Playwright flake on `rx.spec.ts:105` (sign-in raced);
  passed solo — watch in CI.
- No real carrier integration (explicitly out of scope).
- `due_soon` threshold fixed at 72h per SIMPLIFY disposition.
