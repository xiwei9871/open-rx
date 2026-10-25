#!/usr/bin/env bash
# Restore an easyrs-preview backup snapshot produced by backup.sh.
# Usage: restore.sh <snapshot-dir>   (e.g. ~/easyrs-preview-backups/easyrs-preview-2026…)
# Destructive to the preview stack's OWN data only — requires typed confirm.
set -euo pipefail
SNAP="${1:?snapshot dir required}"
test -f "$SNAP/db.dump" -a -f "$SNAP/rustfs.tar.gz" || {
  echo "snapshot missing db.dump/rustfs.tar.gz"; exit 1; }
[ "${CONFIRM:-}" = "restore-preview" ] || {
  echo "set CONFIRM=restore-preview to proceed"; exit 1; }

cd "$(dirname "$0")/.."
ENV_FILE=preview/.env.preview
set -a; . "./$ENV_FILE"; set +a

echo "== stop app tier"
docker compose -f docker-compose.preview.yml --env-file "$ENV_FILE" \
  stop api web

echo "== restore postgres (drop/recreate public schema)"
docker compose -f docker-compose.preview.yml --env-file "$ENV_FILE" \
  exec -T postgres psql -U easyrs_admin -d easyrs \
  -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; \
      GRANT ALL ON SCHEMA public TO easyrs_admin; \
      GRANT USAGE ON SCHEMA public TO easyrs_app; \
      ALTER DEFAULT PRIVILEGES IN SCHEMA public \
        GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO easyrs_app; \
      ALTER DEFAULT PRIVILEGES IN SCHEMA public \
        GRANT USAGE,SELECT ON SEQUENCES TO easyrs_app;"
docker compose -f docker-compose.preview.yml --env-file "$ENV_FILE" \
  exec -T postgres pg_restore -U easyrs_admin -d easyrs --no-owner \
  < "$SNAP/db.dump"

echo "== restore rustfs data"
docker compose -f docker-compose.preview.yml --env-file "$ENV_FILE" \
  exec -T rustfs sh -c "cd /data && rm -rf ./* && tar xzf -" \
  < "$SNAP/rustfs.tar.gz"

echo "== start"
docker compose -f docker-compose.preview.yml --env-file "$ENV_FILE" up -d
echo "restore complete from $SNAP"
