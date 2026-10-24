"""Test harness — real PostgreSQL (docker compose), synthetic data only.

Requires: postgres+redis+minio running (infra/docker-compose.yml) OR the CI
service container. Sets env BEFORE any app import so engines bind to the
dedicated `easyrs_test` database.
"""
import os
import subprocess
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent
PG_HOST = os.environ.get("TEST_PG_HOST", "localhost")
PG_PORT = os.environ.get("TEST_PG_PORT", "55432")
ADMIN_PW = os.environ.get("POSTGRES_ADMIN_PASSWORD", "dev_admin_pw_change_me")
APP_PW = os.environ.get("POSTGRES_APP_PASSWORD", "dev_app_pw_change_me")
PGADMIN = f"postgresql://easyrs_admin:{ADMIN_PW}@{PG_HOST}:{PG_PORT}/postgres"
TEST_DB = "easyrs_test"

os.environ["ENV"] = "test"
os.environ["DATABASE_URL"] = (
    f"postgresql+asyncpg://easyrs_app:{APP_PW}@{PG_HOST}:{PG_PORT}/{TEST_DB}")
os.environ["DATABASE_ADMIN_URL"] = (
    f"postgresql+asyncpg://easyrs_admin:{ADMIN_PW}@{PG_HOST}:{PG_PORT}/{TEST_DB}")
# Shared seed emails would hit the real limits across the suite; the dedicated
# rate-limit test uses a unique bucket identity instead.
os.environ.setdefault("RL_LOGIN_EMAIL_LIMIT", "1000")
os.environ.setdefault("RL_LOGIN_IP_LIMIT", "10000")
os.environ.setdefault("RL_TOTP_IP_LIMIT", "10000")
os.environ.setdefault("RL_WRITE_LIMIT", "10000")

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _psql(db: str, sql: str) -> None:
    subprocess.run(
        ["psql", f"postgresql://easyrs_admin:{ADMIN_PW}@{PG_HOST}:{PG_PORT}/{db}",
         "-v", "ON_ERROR_STOP=1", "-c", sql],
        check=True, capture_output=True, text=True,
    )


@pytest.fixture(scope="session")
def _database():
    """Drop/recreate easyrs_test, grant runtime user, migrate, seed.

    Lazy (not autouse): pure-infra suites (S3 compat, config) run without a
    Postgres. Wired in via the db-bound fixtures below.
    """
    _psql("postgres", f"""
        SELECT pg_terminate_backend(pid) FROM pg_stat_activity
        WHERE datname = '{TEST_DB}' AND pid <> pg_backend_pid()""")
    _psql("postgres", f"DROP DATABASE IF EXISTS {TEST_DB}")
    _psql("postgres", f"CREATE DATABASE {TEST_DB} OWNER easyrs_admin")
    _psql(TEST_DB, f"""
        GRANT CONNECT ON DATABASE {TEST_DB} TO easyrs_app;
        GRANT USAGE ON SCHEMA public TO easyrs_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO easyrs_app;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO easyrs_app;
    """)
    env = dict(os.environ)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                   cwd=API_DIR, env=env, check=True, capture_output=True, text=True)
    subprocess.run([sys.executable, "-m", "app.seed"], cwd=API_DIR, env=env,
                   check=True, capture_output=True, text=True)
    yield


@pytest_asyncio.fixture
async def client(_database):
    from app.main import app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
        # Browser-parity defaults: CSRF header + allowlisted origin.
        headers={"X-Requested-With": "XMLHttpRequest",
                 "Origin": "http://localhost:5173"},
    ) as c:
        yield c


@pytest_asyncio.fixture
async def admindb(_database):
    """Direct admin (RLS-bypass) session — arrange/assert only, never via API."""
    from app.db import AdminSessionLocal
    async with AdminSessionLocal() as s:
        yield s


@pytest_asyncio.fixture
async def appdb(_database):
    """Least-privilege runtime session — for RLS assertions. Caller must set
    app.tenant_id before querying tenant-scoped tables."""
    from app.db import SessionLocal
    async with SessionLocal() as s:
        yield s


async def login(client, email: str, password: str = "Passw0rd!dev"):
    r = await client.post("/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r

# boto3 honours HTTP(S)_PROXY env vars; developer machines often route
# localhost through a debugging proxy -> 502. The S3 compat suite talks to the
# local store directly.
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
