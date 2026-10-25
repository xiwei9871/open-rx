"""B0.1-03b — environment isolation: prod refuses defaults, seed is dev-only."""
import subprocess
import sys

import pytest
from pydantic import ValidationError

from tests.conftest import API_DIR

pytestmark = pytest.mark.asyncio


def _settings(**env):
    """Build Settings from explicit env (bypasses the lru_cache singleton)."""
    import os
    from app.config import Settings
    base = {k: v for k, v in os.environ.items()}
    base.update(env)
    # pydantic-settings reads process env at construction
    return Settings(_env_file=None, **{
        k.lower(): v for k, v in env.items() if isinstance(v, str)})


async def test_prod_fails_closed_on_defaults():
    with pytest.raises(ValidationError):
        _settings(ENV="prod")


async def test_prod_passes_with_explicit_config():
    s = _settings(
        ENV="prod",
        DATABASE_URL="postgresql+asyncpg://easyrs_app:realpw@db:5432/easyrs",
        SESSION_SECRET="prod-secret-0123456789abcdef0123",
        TOTP_ENCRYPTION_KEY="dGVzdC1rZXktMzItYnl0ZXMtZm9yLWZlcm5ldA==",
        S3_ACCESS_KEY="prodkey", S3_SECRET_KEY="prodsecret-0123456789",
    )
    assert s.env == "prod"


async def test_seed_refuses_prod():
    """`python -m app.seed` must exit nonzero when ENV is not dev/test."""
    r = subprocess.run(
        [sys.executable, "-m", "app.seed"], cwd=API_DIR, capture_output=True,
        text=True, env={"ENV": "prod", "PATH": "/usr/bin:/bin"},
        timeout=30)
    assert r.returncode != 0
