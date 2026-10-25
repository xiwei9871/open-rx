# MVP M2 Acceptance — Lab communication, approvals, completion

Date: 2026-10-25 · Branch: `devin/easyrs-full-mvp` · Scope: M2 only

## Features verified in this milestone

| Feature | Evidence |
|---|---|
| COM-001 comments (attachment-anchored) | `rx_comment.file_reference_id` (migration 0010); POST `/rx/{id}/comments` validates the ref is a live attachment on this Rx; UI anchor select on RxDetail; `test_collab.py::test_comment_anchored_to_attachment` (real S3 upload) |
| COM-002 clinical notifications | `notification` table + POST `/notifications` routes the message to the *counterparty* org inbox; `test_issue_notification_flow` |
| COM-004 approval-required loop (E2E-09) | `approval_required` binds `rx_version_at_creation`; decision requires `signature_name` + `Idempotency-Key`; stale version → `409 version_drift` (no silent carry-over); replay-safe (one decision per notification, UK); `test_approval_loop_signed_and_version_bound`, `test_approval_replay_returns_existing`, `test_stale_approval_rejected_on_version_drift` |
| COM-007 message center + todo counts | `GET /notifications?kind=&status=` returns `counts{unread, approval_pending}`; Inbox page with filters, mark-read (ack_required resolves on ack) |
| LAB-002 issue review via approval loop | lab raises `approval_required` → practice inbox → signed approve/reject lands in the Rx transition trail (`via=approval`) and audit log (`approval.decided`) |
| FLOW-011 complete | POST `/rx/{id}/complete` — lab-only, checked_in→completed, `If-Match` required, idempotent repeat, `completed_at`+`completed_by_user_id` persisted (migration 0010); practice caller → 403; `test_lab_complete_and_practice_cannot` |
| FLOW-016 (still PARTIAL) | approval events now emitted into `rx_transition` (`via=approval`, actor_user_id); QC/fulfillment events remain for M3 |

## API additions

`GET/POST /v1/notifications`, `POST /v1/notifications/{id}/read`,
`POST /v1/notifications/{id}/decision`, `POST /v1/rx/{id}/complete`,
`GET /v1/rx/{id}/attachments`. All documented in `docs/api/openapi.yaml`;
`test_contract.py` requires every operationId.

## UI additions

- `Inbox` page (message center): unread + approval-pending counts, kind/status
  filters, mark-read, signed approve/reject with typed-name signature.
- `RxDetail`: attachments list (asset kind/jaw/bytes/sha), STL preview button,
  "Raise issue / request" form (info / ack_required / approval_required),
  comment attachment anchor, `Mark complete` for lab on checked_in orders.

## Test evidence

- `tests/test_collab.py`: **7 passed** (issue flow, signed version-bound
  approval, replay idempotency, version-drift rejection, org isolation,
  lab complete + practice denial, attachment-anchored comment with real S3)
- Full API suite: **130 passed / 6 skipped** (local skips are the S3-gated
  cases when REQUIRE_S3 is unset; the CI asset-integration gate forces them)
- Playwright `collab.spec.ts`: **2 passed**; full e2e **13/13**
- `tsc --noEmit` clean; `npm run build` clean

## Business-rule notes

- Approval decision is bound to the Rx version captured at request creation;
  ANY later content mutation (items/attachments/unsubmit/resubmit) stales the
  request with `409 version_drift`. This is EasyRS-defined policy, not a claim
  of jurisdiction-specific e-signature compliance — `signature_name` is a
  business attribution record only.
- Decisions are immutable: a second POST on a decided notification returns the
  original `Approval` (replay), never a second record.
- Notifications are org-scoped inboxes; cross-org reads return 403 with an
  `access_denied` audit event (verified against the unconnected lab).

## Remaining defects / follow-up

- No push/email delivery — inbox is pull-based (MVP scope).
- Comments are append-only in UI (edit/delete endpoints exist in backend
  permissions but no UI affordance yet).
- `FLOW-016` stays PARTIAL until M3 QC/fulfillment events land.
