# Alpha Trial Readiness — Virtual Clinic UAT verdict

Date basis: `devin/easyrs-clinic-uat-v1`, suite evidence in
`docs/audit/evidence/virtual-clinic/summary.json` (49/49 UAT cases) plus
23/23 legacy browser regressions and 150 backend tests.

## Verdict: `READY_FOR_INTERNAL_ALPHA`

Rationale against the rubric:

- Core journeys are closed *in the browser*: intake → patient → case →
  dual-arch STL → Rx draft (case selected) → submit → lab inbox → bundle
  + check-in → complete → QC → ship → receive → deliver.
- Permission/tenancy guardrails verified: unconnected lab denied
  deep-links and assets with no leakage; role-gated transitions refuse
  cross-role use; approvals refuse stale Rx versions; delete protection
  releases after delivery.
- File integrity verified: STL validation rejects malformed input
  (defect found and fixed), downloads hash-verified, bundle manifest
  matches zip members.
- Remaining issues are usability/scale, not correctness: 25-row list
  ceilings mitigated by search, tooth-entry ergonomics, unverified
  non-STL attachment paths, PDF content checked only for non-empty.
- Not `READY_FOR_LIMITED_CLINIC_TRIAL` yet because real clinics will hit
  the pagination ceiling, expect FDI-style charting, and need non-STL
  attachments verified before depending on them.

## Recommended pre-trial work

P0 (must before any external clinic touches it): none open.

P1 (strongly recommended):
1. Cursor pagination on patient/Rx/inbox lists (F-05).
2. Verify + harden non-STL attachments through the bundle path (F-07),
   including PDF text-content assertions beyond non-empty.
3. Explicitly re-verify bundle regeneration on rendering-field changes
   (F-08).

P2 (roadmap, non-blocking): graphical FDI chart (F-06), saved views/tags
(F-09), due-date sort hints, approval-version surfacing, labelled
carrier/tracking inputs.

## Invitation answer

If a partner clinic is invited next week: **run it with internal /
system-familiar staff first** (internal Alpha). Do not hand it to
untrained clinic users until the P1 items above land.
