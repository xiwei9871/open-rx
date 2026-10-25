# EasyRS Private Preview — Rollback

Two independent rollback planes: **app version** and **data**.

## Roll back the app version

Images are tagged per deploy (`easyrs-api:<tag>`, `easyrs-web:<tag>`).
Previous tags remain on the host until pruned.

```bash
cd ~/easyrs-preview/repo
git checkout <previous-commit>            # or keep working tree, just retag
PREVIEW_IMAGE_TAG=<previous-tag> \
  bash infra/preview/deploy.sh <previous-tag>
```

If the previous image still exists, the build step is a no-op and the
rollback is a container restart. Migrations are forward-only; if the older
code predates a migration that already ran, restore the DB snapshot first.

## Roll back data (restore drill procedure)

```bash
CONFIRM=restore-preview \
  bash infra/preview/restore.sh ~/easyrs-preview-backups/<snapshot-dir>
```

This stops api+web, drops/recreates the `public` schema inside the preview
Postgres only, `pg_restore`s the dump, wipes and re-tars rustfs data, then
restarts. Verified end-to-end on 2026-10-25.

## Disable the preview entirely (zero-impact on neighbours)

```bash
cd ~/easyrs-preview/repo/infra
docker compose -f docker-compose.preview.yml \
  --env-file preview/.env.preview down
```

Deletes only `easyrs-preview-*` containers and its bridge network; named
volumes (`pgdata`, `redisdata`, `rustfsdata` under project prefix) persist
for later re-up. No shared state with stock/water/other services exists —
no host port other than 5190/5191 is used, and no global config
(daemon.json, host nginx, lanproxy) was touched.
