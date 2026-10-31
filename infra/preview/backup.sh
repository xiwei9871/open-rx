#!/usr/bin/env bash
# EasyRS preview backup: pg_dump + rustfs data snapshot.
# Output: $BACKUP_DIR/easyrs-preview-<ts>/ {db.dump, rustfs.tar.gz}
set -euo pipefail
BACKUP_DIR="${BACKUP_DIR:-$HOME/easyrs-preview-backups}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$BACKUP_DIR/easyrs-preview-$TS"
mkdir -p "$DEST"

cd "$(dirname "$0")/.."
ENV_FILE=preview/.env.preview
set -a; . "./$ENV_FILE"; set +a

echo "== pg_dump"
docker compose -f docker-compose.preview.yml --env-file "$ENV_FILE" \
  exec -T postgres \
  pg_dump -U easyrs_admin -d easyrs -Fc > "$DEST/db.dump"

echo "== rustfs snapshot (via temporary tar in the data container)"
docker compose -f docker-compose.preview.yml --env-file "$ENV_FILE" \
  exec -T rustfs sh -c "cd /data && tar czf - ." > "$DEST/rustfs.tar.gz"

du -sh "$DEST"; echo "backup -> $DEST"
# Retain the last 7 snapshots.
ls -1dt "$BACKUP_DIR"/easyrs-preview-* | tail -n +8 | xargs -r rm -rf
