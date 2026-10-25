# M1 Acceptance — Practice Side & Rx Studio

Date: 2026-10-27 (UTC) · Branch: `devin/easyrs-full-mvp`

## Scope delivered (12 features → VERIFIED)

| Feature | Delivery |
|---|---|
| IAM-001 org profile/defaults | `PATCH /orgs/{id}`: name, timezone, `default_doctor_id`, `default_location_id` (validated same-org/active); OrgSettings UI |
| IAM-002 multi-location | `PATCH /orgs/{id}/locations/{lid}` + create/list; OrgSettings UI |
| IAM-003 doctors + default | roster PATCH; `is_default` exclusive per kind per org; org default prefills Rx create |
| IAM-004 staff roster | roster kind=staff add/disable/enable UI |
| IAM-007 connection handshake | OrgSettings Connections: request / accept / reject / withdraw / revoke against existing API |
| IAM-009 password mgmt | Security section → `POST /auth/password` (rate-limited, other sessions revoked server-side) |
| IAM-010 org timezone (SIMPLIFY) | org-level timezone editable; stored per org |
| PAT-002 search-as-you-type | 300ms debounce on Patients search; duplicate hint banner kept |
| PAT-005 rx history | PatientDetail "Prescription history" section → links into RxDetail |
| RX-008 tooth marking (SIMPLIFY) | ToothPicker: FDI checkbox grid per item (`tooth_ops` validated 11–48 + op enum); no drag canvas — per disposition |
| RX-010 templates | `rx_template` table (migration 0009, RLS); `GET/POST/GET/DELETE /templates`; payload catalog ids re-validated at write; apply/save-as in RxCreate |
| ASSET-003 STL preview (SIMPLIFY) | `StlPreview` — three.js STLLoader over presigned URL; no LOD (documented P1) |

## Migration
`0009_m1_studio`: `organization.default_doctor_id/default_location_id` + `rx_template` (RLS).

## Evidence
- API: `tests/test_studio.py` 9 passed (defaults, invalid-foreign-doctor 422, admin-only, location patch, default exclusivity, template CRUD/validation/isolation/persistence). Full suite **123 passed, 6 skipped** (S3-gated locally only).
- Contract: `test_contract.py` green — new ops declared in `openapi.yaml` (`updateOrg`, `updateLocation`, `updateRosterMember`, `listTemplates`, `createTemplate`, `getTemplate`, `deleteTemplate`).
- E2E: `tests/e2e/studio.spec.ts` 2 passed (settings admin; template save/apply + tooth 16 marking); full suite **9→11 passed** after regressions.

## Not done (honest gaps)
- STL preview lacks LOD/decimation for very large meshes (SIMPLIFY bound).
- Org timezone is stored/displayed only — no per-user rendering conversion yet.
- RxCreate does not yet render the attachments panel (attach lives on RxDetail/PatientDetail).
