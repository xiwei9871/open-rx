#!/bin/bash
# Creates the least-privilege runtime DB user (RLS enforced) alongside the
# migration/seed admin (BYPASSRLS). Dev-only credentials — overridden via env.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE USER easyrs_app WITH PASSWORD '${POSTGRES_APP_PASSWORD:-dev_app_pw_change_me}';
    GRANT CONNECT ON DATABASE $POSTGRES_DB TO easyrs_app;
    GRANT USAGE ON SCHEMA public TO easyrs_app;
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO easyrs_app;
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO easyrs_app;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO easyrs_app;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT USAGE, SELECT ON SEQUENCES TO easyrs_app;
EOSQL
