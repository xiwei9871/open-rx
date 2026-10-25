#!/usr/bin/env bash
# Controlled demo-data reset for one preview tenant slug.
# Scope: ONLY the tenant named "preview-demo:<slug>" — cannot touch other
# tenants or any non-preview workload on the host.
#
# Implementation: wipe demo tenant rows via SQL scoped by tenant name, then
# re-run the demo seed. Requires PREVIEW_DEMO_* env from .env.preview.
set -euo pipefail
SLUG="${1:-demo}"
cd "$(dirname "$0")/.."
ENV_FILE=preview/.env.preview
set -a; . "./$ENV_FILE"; set +a

if [ "${PREVIEW_DEMO_SEED:-false}" != "true" ]; then
  echo "refusing: PREVIEW_DEMO_SEED is not true in $ENV_FILE" >&2; exit 1
fi

echo "== reset demo tenant preview-demo:$SLUG"
docker compose -f docker-compose.preview.yml --env-file "$ENV_FILE" \
  exec -T postgres psql -U easyrs_admin -d easyrs <<SQL
DO \$\$
DECLARE t uuid;
BEGIN
  SELECT id INTO t FROM tenant WHERE name = 'preview-demo:${SLUG}';
  IF t IS NULL THEN RAISE NOTICE 'no demo tenant'; RETURN; END IF;
  -- children first; relies on ON DELETE CASCADE where present.
  DELETE FROM access_grant WHERE tenant_id = t;
  DELETE FROM idempotency_record WHERE tenant_id = t;
  DELETE FROM audit_event WHERE tenant_id = t;
  DELETE FROM file_reference WHERE tenant_id = t;
  DELETE FROM upload_session WHERE tenant_id = t;
  DELETE FROM asset WHERE tenant_id = t;
  DELETE FROM rx_comment WHERE tenant_id = t;
  DELETE FROM approval WHERE tenant_id = t;
  DELETE FROM qc_record WHERE tenant_id = t;
  DELETE FROM fulfillment_event WHERE tenant_id = t;
  DELETE FROM notification WHERE tenant_id = t;
  DELETE FROM rx_bundle WHERE tenant_id = t;
  DELETE FROM rx_transition WHERE tenant_id = t;
  DELETE FROM rx_item WHERE tenant_id = t;
  DELETE FROM rx WHERE tenant_id = t;
  DELETE FROM treatment_case WHERE tenant_id = t;
  DELETE FROM patient WHERE tenant_id = t;
  DELETE FROM rx_template WHERE tenant_id = t;
  DELETE FROM catalog_item WHERE tenant_id = t;
  DELETE FROM org_connection WHERE tenant_id = t;
  DELETE FROM roster_member WHERE tenant_id = t;
  DELETE FROM location WHERE tenant_id = t;
  DELETE FROM membership WHERE tenant_id = t;
  DELETE FROM organization WHERE tenant_id = t;
  DELETE FROM tenant WHERE id = t;
END \$\$;
SQL

echo "== reseed"
docker compose -f docker-compose.preview.yml --env-file "$ENV_FILE" \
  run --rm --no-deps migrate \
  sh -c 'python -m app.preview_seed --token "$PREVIEW_DEMO_TOKEN"'
echo "demo reset complete for slug '$SLUG'"
