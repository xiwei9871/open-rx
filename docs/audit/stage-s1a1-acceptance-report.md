# Stage S1a.1 — Acceptance Report

Asset-isolation corrections and CI verification closure on top of S1a.
No new business scope; no Rx, no lab workflow, no AI.

- Baseline: `devin/easyrs-stage-s1a` @ `8db064e8b894c071d34ed25938a28834cfe18951`
- Branch: `devin/easyrs-stage-s1a1`

## 1. S1a1-01 — Storage namespacing (was a real defect, now proven)

**Defect (reviewed):** `_asset_key` minted global `assets/{sha256}` while the
DB dedups per `(org_id, sha256)` and `storage_key` carries a global UNIQUE
constraint. Two orgs uploading identical bytes → second upload's
`INSERT INTO asset` → **UniqueViolation** (reproduced red: `test_cross_org_
same_bytes_independent_assets` failed on `asset_storage_key_key` before the
fix). It also meant two orgs would have shared one mutable physical object.

**Fix:** new uploads mint `assets/{tenant_id}/{org_id}/{sha256}`.
- Per-org dedup (DB constraint) unchanged.
- Legacy flat-key rows are NOT rewritten: `asset.storage_key` stores the
  exact key and downloads resolve it verbatim → previously uploaded objects
  remain reachable (`test_legacy_flat_key_asset_still_downloadable` inserts a
  flat-key row + object and downloads it through the real pipeline).
- UNIQUE constraint kept — no papering over.

New coverage:
- `test_cross_org_same_bytes_independent_assets` — PA + LA upload identical
  bytes → 2 distinct assets, distinct namespaced keys, both objects exist,
  mutual 403.
- `test_cross_tenant_same_bytes_independent` — second tenant gets
  `assets/{t2}/{org}/{sha}`.
- `test_same_org_reupload_dedups_and_never_overwrites` — same org dedups to
  the original row; stored object stays byte-identical.
- `test_upload_complete_roundtrip_and_hash` now asserts content at the row's
  recorded `storage_key` (DB↔S3 consistency).

## 2. S1a1-02 — Cleanup transaction boundary (was a real defect)

`_expire_stale_sessions()` called `db.commit()` mid-request. The commit ends
the transaction → `SET LOCAL app.tenant_id` dies → the subsequent dedup
SELECT silently returned zero rows and the new-session INSERT violated the
RLS `WITH CHECK` → 500. **Any tenant with a stale upload session could not
declare new uploads.**

Fix (unified strategy, per task): cleanup no longer commits. It marks
`sess.status="expired"` inside the caller's transaction; the request's single
`tenant_commit` persists everything atomically. Storage deletes are
best-effort and now swallow **all** exceptions (object may not exist, store
may be down) — they never block a new upload. Cleanup visibility is
RLS-filtered to the caller's tenant — "only authorized tenant data" by
construction.

New coverage (real PostgreSQL):
- `test_expired_cleanup_keeps_rls_context` — stale session present → new
  declare 201 (was 500), stale row flips to `expired`, new upload completes.
- `test_cleanup_storage_failure_does_not_block_declare` — `delete_object`
  raising `RuntimeError` → declare still 201.
- `test_cleanup_only_touches_caller_tenant` — another tenant's expired
  session is invisible to cleanup and untouched.

## 3. S1a1-03 — CI: assets no longer green-by-skip

New `asset-integration` job: postgres + redis + **rustfs** (same pinned
digest) services, creates `easyrs_app`, installs deps, runs
`pytest tests/test_assets.py` with `REQUIRE_S3=1`. The `s3ok` fixture raises
instead of skipping under that flag; the job parses junit and fails on
`skipped>0 | failures>0 | errors>0 | tests==0`, printing real counts.
Distinct from `s3-compat` (raw S3 API surface) — this exercises the full
upload→hash→dedup→authz→revoke pipeline through the API.

**Honest-semantics rename:** `asset.scan_status` → `asset.format_status`
(migration 0004). `format_ok` now literally means "bytes parse as a
recognizable structure" — no security/mesh-quality scan is implied anywhere
(code, schema, OpenAPI description, UI label). Reference-grant gate updated
to `format_status == "format_ok"`.

## 4. S1a1-04 — Migration history audit

- Fresh `alembic upgrade head`: covered by every test run (`_database`
  fixture rebuilds `easyrs_test` from 0001 each suite run).
- **Old-0002 databases:** the originally published `0002_b01_hardening`
  added `totp_secret_enc` and dropped `totp_secret` **without copying data**.
  A DB that ran it already lost plaintext TOTP secrets — irrecoverable by
  any schema migration. Verified behavior: stamping 0002 on such a DB and
  upgrading to head succeeds; affected accounts keep `totp_enabled=true`
  with `totp_secret_enc=NULL` → login is denied `totp_recovery_required`
  (fail-closed) until re-enrollment. Nothing silently clears `totp_enabled`.
  Regression: `test_db_with_original_0002_upgrades_and_stays_fail_closed`
  replays the legacy column effects, stamps 0002, upgrades to head, asserts
  the fail-closed state is preserved.
- The amended (current) 0002 encrypts plaintext into `totp_secret_enc`
  before dropping — protects DBs that had NOT yet run 0002. Both paths
  tested.
- No old migration files were modified to claim recovery; the rename lives
  in new sequential migration `0004_s1a1_asset_format_status`.

## 5. Evidence

| Suite | Result |
|---|---|
| `pytest apps/api` full | **74 passed, 6 skipped** (was 66+6; skips = gated s3-compat) |
| `test_assets.py` | **15 passed** (8 → 15; all now REQUIRE_S3-capable) |
| `test_security_gate.py` | **6 passed** (+legacy-0002 upgrade) |
| `s3-compat` | 5 passed, 1 deselected |
| `npm run build` | PASS |
| Playwright E2E | **6/6** on rebuilt stack (dev DB migrated 0004, `format_ok` visible) |

## 6. Gates checklist

- [x] S1a tests still pass — 74 total, 0 regressions
- [x] same-org same-STL dedup
- [x] cross-org same-STL independent storage
- [x] cross-tenant same-STL independent storage
- [x] no unexpected object overwrite (content-addressed + dedup)
- [x] upload continues after stale-session cleanup (context preserved)
- [x] cleanup failure + RLS isolation
- [x] legacy-DB upgrade compatibility
- [x] remote asset tests cannot skip (REQUIRE_S3 + junit gate)

## 7. Residuals

- Flat-key legacy objects are reachable forever via stored `storage_key`;
  optional physical backfill to namespaced keys deferred (copy + row update
  must be atomic-ish; not needed for correctness).
- Presigned-URL revocation stays TTL-bound.
- `format_status` rename is honest labeling — a real malware/content scan
  remains future work.
- api-tests job still skips the asset suite there (no rustfs service);
  authoritative coverage is `asset-integration`.

**Verdict: S1a.1 READY.**
