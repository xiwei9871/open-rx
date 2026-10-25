# Backup + restore drill record (SAFE-006 / E2E-16)

Date: 2026-10-25 · Environment: dev compose stack (postgres:16, minio)
Scope: full PostgreSQL dump + every object in `easyrs-assets-dev`.

## Commands executed

```bash
PG_DOCKER=easyrs-dev-postgres-1 \
  apps/api/.venv/bin/python scripts/backup.py --out backups/drill-1
# -> backup ok: backups/drill-1 (db.dump 218010 bytes, 321 objects)

PG_DOCKER=easyrs-dev-postgres-1 \
  apps/api/.venv/bin/python scripts/restore.py backups/drill-1
```

## Result

```
restore db: patient = 40
restore db: rx = 59
restore db: asset = 2
restore db: alembic_version = 1
restore s3: 321 verified, 0 failed -> bucket easyrs-assets-dev-restore
restore drill ok
```

- DB restored into scratch database `easyrs_restore` (never the live DB),
  pg_restore ran server-version-matched inside the postgres container
  (`PG_DOCKER`).
- All 321 objects re-uploaded to scratch bucket `easyrs-assets-dev-restore`
  and SHA-256-verified against the manifest after a fresh GET — 0 failures.

## Notes / gaps

- Backup of `db.dump` captures the whole cluster schema incl. RLS policies
  and constraints; verified by row counts + successful restore.
- `PG_DOCKER` path exists because host libpq (v18) predates/succeeds the
  server (v16) dialect — always dump with a matching major version.
- Drill runs on the dev dataset (synthetic). A scheduled CI drill is a P1
  item; the scripts are the same.
- S3 object bytes verified, DB verified by counts only — a row-level hash
  comparison is a possible hardening step.
