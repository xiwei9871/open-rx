# Stage S1a — Acceptance Report

Synthetic patient / treatment-case / digital-asset foundation, on top of the
B0.1-hardened platform. All data is synthetic (`SEED_SYNTHETIC`, dev/test only);
no real patient information, no PHI, no clinical decision-making.

- Baseline: B0.1 final `a48f233c4f46d24191dcd008b2767918b1df6d12`
- Branch: `devin/easyrs-stage-s1a`
- Scope executed: S1a-00 security pre-gate, S1a-01 patients, S1a-02 cases,
  S1a-03 asset/STL foundation, S1a-04 web workbench.
- Explicitly NOT built: Rx submission/acceptance, production tracking, QC,
  delivery, STL geometry editing, basing, AI bracket removal.

## 1. S1a-00 Security pre-gate — CLOSED

| Gate | Fix | Evidence |
|---|---|---|
| A. TOTP fail closed | `totp_enabled` is now authoritative: enabled + missing `totp_secret_enc` → login denied with `totp_recovery_required`; undecryptable secret at `/2fa/verify` → 401 + `login_2fa_secret_unusable` audit event (was: silently skipped 2FA). Migration `0002` reworked to encrypt existing plaintext secrets into `totp_secret_enc` before dropping the column (was: silent drop). | `test_security_gate.py::test_enabled_without_secret_denies_login`, `::test_corrupt_secret_fails_verify_not_500`, `::test_totp_secret_survives_0002_encryption_migration` |
| B. Audit org isolation | `list_audit()` scopes to tenant AND caller's organization. | `test_security_gate.py::test_audit_events_are_org_scoped` |
| C. Atomic transitions | `transition_connection()` takes `SELECT … FOR UPDATE` on the connection row before the version check — two concurrent transitions on one version can no longer both commit. | `test_security_gate.py::test_concurrent_accepts_exactly_one_wins` (two real asyncio tasks racing; exactly one 200, loser gets 409) |
| D. Frontend 2FA | Login response `requires_2fa` drives a challenge view (code input, error states, attempt feedback); browser E2E enrolls a live TOTP on `doctor@pa.dev`, fails a wrong code, then completes sign-in. | `apps/web/tests/e2e/auth.spec.ts` "2FA-enabled user completes the challenge in the browser"; `totp.ts` helper |

Gate consequence per taskbook: all four closed → patient-domain work proceeded.

## 2. Domain implementation

### S1a-01 Patients (PAT-001/002/003/004/005/009)

- `patient` table: org-owned (exactly one `org_id`), `patient_number`
  human key (`P000001…` via sequence), `external_id`, name/DOB/sex/notes,
  `version` optimistic lock, `deleted_at` soft delete, RLS + org predicates.
- Endpoints: `searchPatients` (q/prefix on name & number), `createPatient`
  (`confirm_duplicate` flag — same last_name+DOB in-org → 409
  `possible_duplicate`), `getPatient`, `updatePatient` (version check → 409),
  `deletePatient` (soft delete only).
- Lab roles have **no** `patient:*` permission; cross-org read/write within a
  tenant returns 403/404-deny via `_deny()` + audit.
- Min-necessary share: labs reach assets only through explicit
  `file_reference` grants — patient rows are never exposed cross-org.

### S1a-02 Treatment cases (PAT-008)

- `treatment_case`: patient FK (org-checked), `label`, `category`, `status`
  (`active/closed/draft` enum), `opened_at/closed_at`, `version`,
  `case_event` history table (type + payload + actor), `rx_id` column
  **reserved as a nullable draft hook only** — no Rx state machine, no
  submission semantics.
- `listCases`, `createCase` (writes `case.opened` history row).

### S1a-03 Assets / STL foundation (ASSET-001/002/005/008/009/010)

- Flow: `declareUpload` → presigned PUT to **staging key** → `completeUpload`
  re-downloads, verifies byte size + SHA-256 + STL structure (binary
  layout 84+50n or ASCII `solid`/`facet`), promotes to content-addressed
  `assets/{sha256}` key, deletes staging.
- `asset` row: immutable by design — no update/delete endpoints; content
  dedup by (org, sha256); `scan_status` gate on reference-granting.
- `file_reference`: `subject_type` ∈ patient/case (rx/notification/order
  rejected 422 — subjects don't exist yet); revocable; revoked refs block
  NEW download grants (issued presigned URLs expire by TTL — documented
  S3 limitation).
- `downloadAsset`: `access_grant` row + presigned GET minted by the backend
  against `S3_PUBLIC_ENDPOINT_URL`; browser never sees storage credentials.
- Upload sessions: TTL expiry, dedup/resume of open same-hash sessions,
  opportunistic staging cleanup on declare (`_expire_stale_sessions`),
  failed-content deletes staging.
- Size cap `upload_max_bytes`, kind allowlist, jaw ∈ upper/lower/na.
- Bucket CORS narrowed to `cors_origin_list` for the browser PUT.
- Bug found & fixed via E2E: frontend skipped the PUT on `resumed` sessions,
  but a resumed session can point at a staging object that never landed —
  permanent 409 loop. PUT is now unconditional (idempotent).

### S1a-04 Web workbench

- `Patients.tsx`: list + search + create form + duplicate-prompt flow.
- `PatientDetail.tsx`: patient header (number/external id), edit with
  version conflict surfacing, case list + create, file list + STL upload
  (jaw picker), loading/error/empty/permission-denied states.
- `App.tsx`: auth gate (login + 2FA challenge), workbench routing.
- `api.ts`: zod runtime validation on every response; `uploadAsset` does
  browser-side SHA-256 + presigned PUT + complete.

## 3. Contract & migrations

- `docs/api/openapi.yaml`: 14 S1a operationIds added and schema-synced;
  `test_contract.py` `REQUIRED_SPEC_OPS` extended to cover them.
- Migration `0003_s1a_patient_case_asset.py`: patient + sequence,
  treatment_case + case_event, upload_session + asset + file_reference +
  access_grant; grants `USAGE/SELECT` on all sequences to `easyrs_app`
  (mirrored in `infra/postgres/init/01-runtime-user.sh` and test bootstrap).
- Migration `0002_b01_hardening.py` amended (pre-merge, history not yet
  published on this branch): plaintext `totp_secret` is Fernet-migrated into
  `totp_secret_enc` before the drop — verified against real row data in
  `test_totp_secret_survives_0002_encryption_migration`.

## 4. Test evidence (local, pre-push)

| Suite | Result |
|---|---|
| `pytest apps/api` (all) | **66 passed, 6 skipped** (was 46+6 at B0.1) |
| — `test_security_gate.py` | 5 passed (4 gate tests + real-migration TOTP test) |
| — `test_patients.py` | 7 passed |
| — `test_assets.py` | 8 passed |
| `test_s3_compat.py` (`S3_COMPAT=1`) | 5 passed, 1 deselected |
| `npm run build` (tsc + vite) | PASS |
| Playwright E2E (real Chrome) | **6 passed** — login/logout, bad creds, 2FA challenge, seeded-patient search→detail→case, create→edit→case→STL upload→file listed, duplicate-prompt |

E2E drives the real stack: nginx → api → postgres RLS → presigned PUT →
rustfs → complete → asset listed. New regression coverage includes the
concurrency race, org-scoped audit, TOTP fail-closed, hash-mismatch,
invalid-STL, revoked-reference, and cross-org denial paths.

## 5. Gates checklist

- [x] Patient CRUD — yes (API + UI + E2E)
- [x] Patient search & duplicate prompt — yes (API + UI + E2E)
- [x] Case create & association — yes
- [x] Cross-tenant denial — yes (`test_patients`, `test_assets`)
- [x] Same-tenant cross-org unauthorized denial — yes
- [x] Lab access only to explicitly granted data — yes (no patient:*/asset
      perms for lab roles; references subject to org ownership)
- [x] STL upload hash equality — yes (server re-hash; E2E verified)
- [x] File version cannot be overwritten — yes (immutable assets, no update
      path; content-addressed keys)
- [x] Revoked reference cannot mint downloads — yes (`test_assets`)
- [x] Real browser E2E — 6 tests
- [x] All B0.1 tests still pass — 66 total, 0 regressions
- [x] TOTP / audit / concurrency regressions — 5 gate tests
- [x] OpenAPI synchronized — contract test enforces
- [x] Migrations — 0002 amended (secret-preserving), 0003 new
- [x] This report

## 6. Residual risks (non-blocking, flagged)

- Presigned URL revocation is TTL-bound (S3 semantics); revoked references
  stop new grants only.
- Upload cleanup is opportunistic on declare; a periodic sweeper is a later
  hardening item.
- `rx_id` on cases is a reserved column, not a commitment — Rx schema/state
  machines await V1.1 verification.
- RustFS CORS is permissive on headers (`*`) within allowed origins;
  acceptable for dev, tighten before any real deployment.
- No retention/purge job for `deleted_at` patients yet — lifecycle policy
  deferred to a later stage.

**Verdict: S1a READY** — patient/case/asset foundation with real browser
evidence; stopped before Rx Studio per instructions.
