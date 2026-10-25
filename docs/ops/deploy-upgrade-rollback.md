# Deploy / upgrade / rollback runbook (Alpha, test environments only)

> Alpha status: this runbook covers self-hosted dev/test deployments.
> Do NOT use with real patient/clinic data — synthetic data only until a
> formal release authorization exists.

## Services

| Service | Image | Notes |
|---|---|---|
| api | `apps/api/Dockerfile` | FastAPI/uvicorn |
| web | `apps/web/Dockerfile` | nginx + built SPA |
| postgres | postgres:16-alpine | RLS-enabled schema |
| redis | redis:7 | sessions/rate limits |
| minio (or RustFS) | minio/minio | S3-compatible assets |
| migrate | api image | `alembic upgrade head` + seed (dev) |

## Deploy (fresh)

```bash
cp .env.example .env          # fill secrets — see checklist
docker compose -f infra/docker-compose.yml build
docker compose -f infra/docker-compose.yml up -d postgres redis minio
docker compose -f infra/docker-compose.yml up -d migrate   # applies head
docker compose -f infra/docker-compose.yml up -d api web
scripts/preflight.py          # must print 'preflight ok'
```

## Upgrade

```bash
git pull --ff-only            # never force local main
docker compose -f infra/docker-compose.yml build api web migrate
docker compose -f infra/docker-compose.yml up -d migrate   # forward-only
docker compose -f infra/docker-compose.yml up -d api web
```

Migrations are forward-only in normal operation. Every migration ships a
`downgrade()` — review it before relying on rollback (see below).

## Rollback

1. **App rollback** (preferred): redeploy the previous image tag. New code
   must stay schema-compatible for one release behind; destructive schema
   changes must be split into expand/contract migrations.
2. **Data rollback**: only if the migration was contract-style and its
   `downgrade()` was reviewed:
   `docker compose ... run migrate alembic downgrade -1`
   Never downgrade across data-writing releases without a backup first.
3. **Disaster recovery**: `scripts/backup.py` regularly; restore verified by
   `scripts/restore.py` into scratch targets (see drill record).

## Production checklist (SAFE-010)

- [ ] `ENV=prod`, all secrets rotated from `.env.example` values
- [ ] `TOTP_ENCRYPTION_KEY` set (base64 Fernet)
- [ ] `DATABASE_ADMIN_URL` empty at runtime (migrate jobs only)
- [ ] `S3_*` real credentials, `S3_PUBLIC_ENDPOINT_URL` https
- [ ] `CORS_ORIGINS` https only
- [ ] `ASSET_AV_ENGINE` chosen deliberately (none|eicar_stub|adapter)
- [ ] `python scripts/preflight.py` → `preflight ok`
- [ ] Backup schedule configured; restore drill executed once
- [ ] No synthetic seed: `python -m app.seed` refuses ENV=prod by design
