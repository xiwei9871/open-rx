#!/usr/bin/env bash
# EasyRS private-preview deploy — run from the repo checkout on the host.
# Usage: PREVIEW_DIR=<repo> infra/preview/deploy.sh [image-tag]
set -euo pipefail
cd "$(dirname "$0")/.."          # infra/
TAG="${1:-v0.1.0}"
ENV_FILE=preview/.env.preview
test -f "$ENV_FILE" || { echo "missing $ENV_FILE — copy env.preview.example"; exit 1; }
set -a; . "./$ENV_FILE"; set +a
export PREVIEW_IMAGE_TAG="$TAG"

echo "== build easyrs-api:$TAG / easyrs-web:$TAG"
docker compose -f docker-compose.preview.yml --env-file "$ENV_FILE" build

echo "== up"
docker compose -f docker-compose.preview.yml --env-file "$ENV_FILE" up -d

echo "== wait for migrate"
docker compose -f docker-compose.preview.yml --env-file "$ENV_FILE" \
  wait migrate 2>/dev/null || true
docker compose -f docker-compose.preview.yml ps
