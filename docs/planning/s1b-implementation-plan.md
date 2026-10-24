# S1b Implementation Plan — Rx Studio foundation

Baseline: `devin/easyrs-stage-s1a1` @ `1e0ceb7`. Scope is bounded by V1.1 evidence —
69 features marked `S1B_CANDIDATE` in `docs/research/v1.1-feature-evidence-map.csv`.
No real patient data; synthetic seeds only. This plan defines work packages; it is NOT
authorization to code until this document is reviewed.

## Out of scope (post-S1b)

EDIT-* mesh editing, AI-* processing engines, INT-* scanner/PMS integrations, LAB-005+
VisualDLP MES depth, FIN-004+ invoicing statements, COM-012 forms, LAB-003 written check-in,
LAB-020 printer queue, FLOW-004 saved views (UNKNOWN), FLOW-014 needed-soon (UNKNOWN),
AI-016 print flags (UNKNOWN).

## Work packages

### S1b-01 Rx domain core (RX-001..005, RX-019..021, FLOW-005..010)

- `rx` table: patient_id, case_id NULL, practice_org_id, lab_org_id NULL (universal draft),
  form_type, form_payload jsonb, date_needed, external refs, status, submitted_at,
  checked_in_at, checked_in_via, signature jsonb, price_snapshot jsonb, version.
- `rx_part`, `rx_comment`, `rx_annotation`, `rx_tag`, `rx_attachment` (→asset_reference),
  `rx_reset` (extractions/ipr/resets), `rx_history` (revision entries w/ actor).
- Endpoints: `POST /rx`, `PATCH /rx/{id}` (saved only), `POST /rx/{id}/submit`,
  `POST /rx/{id}/unsubmit`, `GET /rx` (tab filter: saved|submitted|checked_in|completed|
  shipped|received + date range + office/doctor/tag filters), `GET /rx/{id}`,
  `DELETE /rx/{id}` (saved only, soft delete).
- Guards: connection check on submit; date_needed turnaround check; universal-library submit
  block; duplicate-patient hint (reuse PAT dedup); iTero-source attach denied post-submit.
- Events: `rx.created/saved/submitted/unsubmitted/checked_in/completed` → outbox + audit.

### S1b-02 Lab inbox & lifecycle (FLOW-006..013, LAB-001, LAB-002)

- Lab list views (submitted queue; saved-as-tags visibility PARTIAL → PROVISIONAL scope:
  show saved Rxs addressed to that lab in a separate "drafts shared" section only if the
  practice marks them visible — default OFF since EasyRx shows them as tags; keep flag).
- `POST /rx/{id}/check_in` (+ `POST /rx/{id}/download` sets checked_in too — confirmed rule).
- Lab edit of submitted/checked_in Rx → new revision + optional notification.
- `POST /rx/{id}/ship` {carrier, tracking_no}; `POST /rx/{id}/complete` (lab plan flag
  `completed_enabled` — mirrors plan gating).
- Practice `POST /rx/{id}/received`, `POST /rx/{id}/delivered` → fulfillment_status projection.

### S1b-03 Notifications (COM-001..009)

- `rx_notification` {rx, lab_org, regarding enum(general|file), asset_id NULL,
  action enum(notify|require_approval|email_only), message, extra_emails[],
  status enum(pending|acknowledged|approved|commented), signature jsonb NULL}.
- Endpoints: create (lab), list, acknowledge, approve (requires `rx:approve` + signature text),
  comment-back. Email-only sends mail, stores nothing on the Rx (mirrors confirmed semantics).
- Clinical-verification-style list for labs (per-notification status).
- Alert preferences per user {email, popup} → stores settings; actual delivery via existing
  notification plumbing.

### S1b-04 Catalog & templates (RX-006..018, IAM-008, FIN-001..003)

- catalog_part + option_lookup + part_option_dict + product_class_option_set
  (schema per `v1b-template-data-model.md`).
- rx_template + template_grant (Copy/Edit/View, owner-managed, overwrite warning).
- price_list + items + practice_price_tier (≤4); `rx.price_snapshot` on submit.
- Seed: ~12 honest universal parts (clasp, labial bow, ball clasp, RPE screw, expansion screw,
  band, crown, retainer base, Adams clasp, recurve spring, finger spring, acrylic plate) with
  option dictionaries (wire gauge list, screw type, flip) — EasyRS vocabulary, no EasyRx art.

### S1b-05 Sharing & retention (COM-011, PAT-005, PAT-006, FLOW-016, FLOW-017)

- `access_grant` for share-with-colleague: {rx, token, expires_at≤24h, opens_left≤5}
  — mirrors confirmed dual limit; recipient view = read-only Rx + file downloads.
- Soft delete + `deleted_at` + restore endpoint (admin, ≤60d) mirroring confirmed window.
- Remake/repair request stub: `POST /rx/{id}/remake_request` → creates linked draft
  (parent_rx_id) — PARTIAL evidence, minimal implementation.

### S1b-06 Frontend (workbench extension)

- Patients → patient detail adds "Create Rx" + Rx history tab (PAT-005).
- Rx list (tabs by status, date/status/office/doctor/tag filters), Rx create form (F1–F10),
  simplified canvas: part list + arch/tooth selection + option forms (no drag-and-drop canvas
  in S1b — textual placement `arch+teeth[]` sufficient; canvas is S1c).
- Lab inbox: queue, Rx view, check-in, edit, notify, ship, complete actions.
- Notification center + approval signature dialog.
- Templates tab (list/apply/save-as), price preview on submit.

## OpenAPI deltas (`docs/api/openapi.yaml`)

Add tags `rx`, `catalog`, `templates`, `notifications`, `lab-inbox`. Ops:
`createRx listRx getRx updateRx submitRx unsubmitRx deleteRx restoreRx checkInRx
downloadRx shipRx completeRx receiveRx deliverRx listRxNotifications createRxNotification
ackRxNotification approveRxNotification commentRxNotification listCatalogParts
listOptionSets listTemplates createTemplate applyTemplate shareTemplate listTemplateGrants
createShareLink listPriceLists pricePreviewRx remakeRequestRx`.
Keep `format_status` semantics on attachments (S1a.1). State field: `rx.status` enum
`saved|submitted|checked_in|completed|deleted`; `fulfillment_status` enum
`none|shipped|received|delivered`; `in_progress` removed from public status (evidence-based).

## E2E acceptance cases (Playwright + API)

1–10 = the V-01 cases in `v1.1-rx-rules.md` §D. Plus:
11. Lab sees submitted Rx; check-in → practice unsubmit now 409.
12. `download` alone transitions to checked_in (regression for FLOW-007).
13. Lab edit creates revision + notification require-approval → doctor signs → approved.
14. Email-only notification leaves no portal record.
15. Ship with tracking → practice sees shipped; received/delivered progression updates
    fulfillment_status, not rx.status.
16. Deleted saved Rx → restore within window; attachments on patient persist.
17. Template: practice saves template → applies to new Rx; lab shares template with
    copy-grant → practice sees badge; edit-grant overwrite warning shown.
18. Turnaround: lab days_in_lab=10 + transit=2 → practice can't pick date < 12 business days.
19. Share link: 24h/5-open bounds enforced; 6th open 410.
20. Cross-org: disconnected lab blocked at submit; existing Rx remains readable both sides.

## Risks carried into S1b

| Risk | Level | Handling |
|---|---|---|
| Checkout field set undocumented | Med | minimal checkout (signature + confirm); iterate |
| Lab saved-Rx visibility ambiguous | Low | feature-flagged draft sharing, default off |
| Doctor-scope visibility unknown | Med | org-wide default; optional scope later |
| Cancel/reopen semantics unknown | Med | not implemented in S1b; hold/cancel stays PROVISIONAL |
| Price computation depth unknown | Low | snapshot schema only; lab-managed items optional |
