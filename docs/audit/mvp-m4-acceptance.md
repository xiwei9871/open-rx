# MVP M4 Acceptance — 安全、运维与数据保护

Date: 2026-10-25 · Milestone: M4 · Features: ASSET-010, SAFE-003/005/006/009/010

## Delivered

| Feature | Evidence |
|---|---|
| ASSET-010 上传限制 | 200 MB cap (`UPLOAD_MAX_BYTES`), declared sha256/bytes verified byte-exact at completion, STL structural validation, staging object reaper; `tests/test_assets.py` |
| SAFE-003 限时链接 | presigned PUT/GET with TTL; prod HTTPS enforcement via preflight |
| SAFE-005 文件校验 | sha256 + size + extension + STL structure; pluggable scan hook `ASSET_AV_ENGINE` (none/eicar_stub/adapter, fail-closed) |
| SAFE-006 备份/恢复 | `scripts/backup.py` (pg_dump + S3 manifest w/ sha256), `scripts/restore.py` (scratch DB/bucket restore + per-object hash verify); drill: **321/321 objects verified, 0 failed**, row counts restored — `docs/audit/backup-restore-drill.md` |
| SAFE-009 管理员导出 | `GET /v1/admin/export` org-scoped JSON (org, members sans credentials, locations, roster, patients, rx summary, asset manifest, connections); cross-org leakage test |
| SAFE-010 配置检查 | prod guard in `Settings` (dev secrets/TOTP key refused at boot); `scripts/preflight.py` runtime validation (`preflight ok` / fail-closed); deploy checklist |

## Supporting docs added

- `docs/security/permission-matrix.md` — generated from `ROLE_PERMISSIONS` + object-level rules
- `docs/security/data-protection.md` — at-rest/in-transit/upload/retention posture
- `docs/ops/deploy-upgrade-rollback.md` — deploy, upgrade, rollback, prod checklist
- `docs/audit/backup-restore-drill.md` — actual drill output
- `scripts/preflight.py` — env validation tool
- `seed --purge` — verified synthetic-data wipe + reseed cycle (dev/test only)

## Test evidence

- `apps/api/tests/test_m4.py` — 3 passed (export scoping, prod guard, purge guard)
- Full API suite: 139 passed, 6 skipped (local, non-S3-gated)
- Contract tests: 3 passed (adminExport op declared)

## Known gaps (P1)

- S3 bucket SSE/policy enforcement is infra-side; documented, not enforced by app
- Backup scheduling is manual/cron-side; no in-app scheduler
- Restore verifies object hashes + table counts; row-level hash diff is future hardening
