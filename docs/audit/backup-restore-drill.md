# Backup + restore drill record (SAFE-006 / E2E-16)

Date: 2026-10-25 · Environment: dev compose stack (postgres:16, minio)
Scope: full PostgreSQL dump + every object in `easyrs-assets-dev`.

## Commands executed

```bash
PG_DOCKER=easyrs-dev-postgres-1 \
  apps/api/.venv/bin/python scripts/backup.py --out backups/drill-2
# -> backup ok: backups/drill-2 (db.dump 207085 bytes, 366 objects)

PG_DOCKER=easyrs-dev-postgres-1 \
  apps/api/.venv/bin/python scripts/restore.py backups/drill-2
```

## Result (drill-2)

The backup manifest now records a DB acceptance baseline
(`expected_counts` for 11 core tables); restore **fails hard** on any
mismatch rather than just printing numbers:

```
restore db: patient = 13 (expected 13) ok
restore db: treatment_case = 5 (expected 5) ok
restore db: rx = 27 (expected 27) ok
restore db: rx_item = 23 (expected 23) ok
restore db: rx_transition = 77 (expected 77) ok
restore db: asset = 1 (expected 1) ok
restore db: file_reference = 4 (expected 4) ok
restore db: organization = 6 (expected 6) ok
restore db: user_account = 5 (expected 5) ok
restore db: audit_event = 1064 (expected 1064) ok
restore db: alembic_version = 1 (expected 1) ok
restore s3: 366 verified, 0 failed -> bucket easyrs-assets-dev-restore
restore drill ok
```

## Negative-test evidence (failure actually triggers)

A copy of the drill-2 manifest was tampered with
(`expected_counts.patient += 999`) and restored:

```
restore db: patient = 13 (expected 1012) MISMATCH
...
DRILL FAILED — row-count mismatch: ['patient']
```

Exit code 1. A missing manifest likewise exits 1. The drill cannot pass
silently on a short restore.

## Notes / gaps

- `PG_DOCKER` runs version-matched pg tools inside the postgres container
  (host libpq major ≠ server major otherwise).
- S3 verification: every manifest object re-uploaded to the scratch bucket,
  re-downloaded and sha256-verified — 366/366 passed, 0 failed.
- Drill runs on the dev dataset (synthetic). A scheduled CI drill is a P1
  item; the scripts and the fail-closed checks are the same.
