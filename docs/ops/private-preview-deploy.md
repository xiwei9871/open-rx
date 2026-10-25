# EasyRS Private Preview — Deployment Guide

Scope: the invitation-only, synthetic-data preview on `192.168.3.185`
(SSH alias `stock-prod`). This stack is fully isolated from every other
workload on the host.

## Layout

| Piece | Where |
|---|---|
| Compose file | `infra/docker-compose.preview.yml` (project `easyrs-preview`) |
| Secrets | `infra/preview/.env.preview` on the host (chmod 600, gitignored) |
| Secrets template | `infra/preview/env.preview.example` |
| Deploy dir | `/home/jqz/easyrs-preview/repo` (git clone of the branch) |
| Backups | `/home/jqz/easyrs-preview-backups/` |
| Demo credentials | `/home/jqz/easyrs-preview/demo-accounts.txt` (600, host-only) |

## Services

| Container | Image | Host binding | Limits |
|---|---|---|---|
| `easyrs-preview-postgres-1` | postgres:16.4-alpine | none (network-only) | 1G / 1 cpu |
| `easyrs-preview-redis-1` | redis:7.4-alpine | none | 256M / 0.5 |
| `easyrs-preview-rustfs-1` | rustfs@sha256:9ca9559… | `192.168.3.185:5191` | 512M / 0.5 |
| `easyrs-preview-api-1` | easyrs-api:TAG | none | 1G / 1 |
| `easyrs-preview-web-1` | easyrs-web:TAG | `192.168.3.185:5190` | 128M / 0.5 |
| `easyrs-preview-migrate-1` | easyrs-api:TAG | one-shot | — |

DB/Redis/RustFS-console have **no host port**. Only `5190` (web) and `5191`
(S3 presigned endpoint) bind the LAN IP for the external ingress.

## Registry note (this host cannot reach docker.io directly)

Base images were pulled through `docker.m.daocloud.io` and re-tagged
locally; `rustfs` was pulled by the **same sha256** used in dev/CI
(`9ca9559…`) and retagged `rustfs/rustfs:9ca9559`. Set
`RUSTFS_IMAGE=rustfs/rustfs:9ca9559` in `.env.preview`. `PIP_INDEX_URL`
supports a PyPI mirror for builds (tsinghua used on this host).

## Deploy / update

```bash
cd ~/easyrs-preview/repo && git pull
bash infra/preview/deploy.sh <new-tag>     # builds easyrs-*:<tag>, restarts
```

`migrate` runs `alembic upgrade head` plus the controlled demo seed when
`PREVIEW_DEMO_SEED=true`. Demo seeding additionally requires
`--token "$PREVIEW_DEMO_TOKEN"` — the flag alone is inert, and `ENV=prod`
guards remain fully enforced (prod boot refuses dev defaults).

## Public HTTPS path (operator action required)

Public reachability goes through the existing lanproxy server
(`www.manqiaotechnology.com:8090` admin console). Two mappings are needed:

| Public hostname | Target |
|---|---|
| `easyrx.manqiaotechnology.com` | `192.168.3.185:5190` (web, proxies /api) |
| `easyrx-s3.manqiaotechnology.com` (or a path-based route) | `192.168.3.185:5191` (rustfs) |

Then set in `.env.preview`:

```
CORS_ORIGINS=https://easyrx.manqiaotechnology.com
S3_PUBLIC_ENDPOINT_URL=https://easyrx-s3.manqiaotechnology.com
```

and `docker compose … up -d api`. Verify: browser PUT/GET presigned URLs,
CORS preflight, HTTPS certificate, and that `easyrx` host does not collide
with the existing wildcard nginx config (it must be a NEW vhost/route —
never edit the Dify `server_name _` file).

## Demo data reset

```bash
bash infra/preview/reset-demo.sh <slug>   # default slug "demo"
```

Deletes only the `preview-demo:<slug>` tenant (guarded by
`PREVIEW_DEMO_SEED=true`) and reseeds. Other tenants/hosts untouched.

## Backup / restore

```bash
bash infra/preview/backup.sh                 # -> ~/easyrs-preview-backups/<ts>/
CONFIRM=restore-preview bash infra/preview/restore.sh <snapshot-dir>
```

Restore verified 2026-10-25: snapshot restored, API healthy, all seeded
rows present. Cron suggestion: `0 4 * * * ~/easyrs-preview/repo/infra/preview/backup.sh`
