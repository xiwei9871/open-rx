# Virtual Clinic UAT — Results

Branch `devin/easyrs-clinic-uat-v1`. Suite: **49 UAT cases + 23 legacy
browser regressions = 72/72 pass**; backend **150 passed / 6 skipped**
(S3-gated locally); `tsc --noEmit` clean. Aggregator output:
`docs/audit/evidence/virtual-clinic/summary.json`.

All verdicts below come from real Playwright Chromium runs against the
dockerised dev stack unless marked `API-assisted` (precondition only) or
`code-review`.

## Verdicts by domain

### UAT-A — Clinic core (browser-verified)
- Login/logout/session: PASS. Both cookies cleared on logout; refresh keeps
  patient + Rx context; legacy no-hint-cookie session degrades to plain
  login (AUTH-01..03, plus legacy specs).
- 2FA: PASS. Pre-enrolled `mfa@pa.dev` — wrong code rejected, TOTP accepted
  (AUTH-04).
- Patients: PASS. Create, required-field validation, warn-style duplicate
  detection (candidates + "Create anyway"), edit persistence, treatment
  case create with label/stage/opened_at, delete blocked while an Rx is
  in-flight and permitted after delivery (PAT-01..05).
- Rx: PASS after this round's fixes. Draft create (patient filter + case
  select + lab/doctor/due/notes), required catalog options block add,
  tooth ops persist across reopen, template save/apply with isolation,
  draft survives logout+re-login, submit requires items+lab+signature and
  records transition, unsubmit→edit→resubmit, unsubmit refused after lab
  check-in with a human-readable error (RX-01..10).

### UAT-B — Lab core (browser-verified)
- Inbox shows submitted only; drafts hidden; unconnected LB sees nothing
  (LAB-01). Detail shows patient label/doctor/items/notes (LAB-02).
- Download & Check-in produces a real ZIP: `prescription.pdf` (non-empty),
  `manifest.json`, `attachments/…`; status → `checked_in` with transition
  (LAB-03). Manifest entries match zip members; a patient STL attached via
  the web is present inside (LAB-04). Unchanged content reuses the bundle
  (LAB-05). Complete marks production done, practice sees the status
  (LAB-06).

### UAT-C — Files & STL (browser-verified)
- Upper + lower STL upload, bytes/sha256/format_status displayed (ASSET-01).
- Preview orbit/zoom/reset verified by canvas pixel diffs, not button smoke
  (ASSET-02). Download bytes non-empty and SHA-256 equals generated source
  (ASSET-03). Aborted PUT leaves no half-registered asset; reaper path
  covered (ASSET-04). Truncated/malformed STL rejected — **real defect
  found and fixed this round** (ASSET-05 + API regression). Unconnected
  lab cannot reach patient assets (ASSET-06).

### UAT-D — Permissions, safety, exceptions
- Unconnected-lab deep link to a foreign Rx: denied, no patient data
  leaked (NEG-01). Practice user cannot run lab-only actions (NEG-02).
- Same-tick double-clicks on Save draft and Post produce single side
  effects (NEG-03). API outage surfaces an explicit error alert
  (NEG-04). Back/forward honours URL routing (NEG-05).
- Approval bound to `rx_version_at_creation`; editing the Rx before
  deciding prevents silently approving the stale version (COLLAB-05).

### UAT-E — UX
- Mechanical checks pass (E-01..05): obvious next actions, labelled
  controls, grouped detail sections, readable lab inbox, no horizontal
  overflow at 390 px. Human scorecard:
  `virtual-clinic-scorecard.csv` — several pages score <4, none block
  internal Alpha.

## Real defects found by this UAT (fixed on this branch)

1. **P0** Patient→Case→STL→Rx was *not* closed in the web UI: RxCreate had
   no treatment-case selector, and no UI existed to attach a patient file
   to an Rx (API supported both). Minimal web UI added; UAT-RX-05 now
   exercises the true browser path.
2. **P1** Patients beyond the first API page (25 rows) were unreachable in
   RxCreate — no search. Added a type-ahead filter bound to
   `searchPatients`. (Patients list itself already had search-as-you-type.)
3. **P1** ASCII STL validation accepted any payload containing `solid` +
   `facet` — truncated files were marked `format_ok` and previewable.
   Tightened to require complete `endfacet`/`endsolid` terminators;
   backend regression added.
4. **P1** Both 2FA browser specs were non-idempotent (they enrolled TOTP
   onto the shared doctor account; second run always failed). Replaced
   with seeded `mfa@pa.dev` carrying a fixed synthetic secret.

## Open gaps (recorded, not blockers)

- **P2** List pagination: patient/Rx/notification lists render the first
  API page only. Reachable via search/filters today; real cursor UI is
  roadmap work.
- **P2** Tooth selection is a numbered button grid, not a graphical FDI
  chart; arch is a per-item select. Usable but below EasyRx ergonomics.
- **P2** Non-STL attachments: patient upload accepts arbitrary files and
  Rx attach links them, but the UAT covered STL only; PDF/photo bundle
  behaviour is unverified.
- **P2** Bundle reuse verified for unchanged content; change-detection
  triggers a new bundle per `bundle` module, but a rendering-field change
  (e.g. patient display name) was not explicitly re-verified in the
  browser.
- **P3** No saved views/tags, no graphical dashboard beyond stat cards,
  no localisation, antivirus scanning is not present (no stub surfaced).
- **P3** Dev database retained earlier duplicate `UAT-P03B` rows from
  pre-idempotency runs; `ensureDataset` keys on `external_ref` so tests
  are unaffected. Data-hygiene note only.

## Answers to the mandated questions

- *Can a clinic user complete a real prescription from zero?* **Yes** —
  intake → patient → case → STL upload → Rx draft (case selected) →
  submit, all in the browser (RX-01..08, JOURNEY).
- *Can a lab user complete intake to delivery?* **Yes** — inbox → detail →
  bundle+check-in → complete → QC → ship → receive → deliver
  (LAB-01..06, FULFILL-01..04, JOURNEY).
- *Is the Patient/Case/STL/Rx loop actually closed in the web?* **Yes,
  after this branch's minimal fixes** — it was genuinely broken before.
- *Top 3 blockers to a real clinic trial:* (1) list pagination ceiling;
  (2) tooth-entry ergonomics for real charting; (3) unverified non-STL
  attachment/bundle paths and no PDF-text verification beyond non-empty.
