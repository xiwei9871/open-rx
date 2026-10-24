"""Engine + session helpers.

Two engines on purpose:
- `engine`      — least-privilege runtime user (subject to RLS policies)
- `admin_engine`— migration/seed user (table owner, bypasses RLS)
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import get_settings

_s = get_settings()
# NullPool under test: pytest-asyncio uses a fresh loop per test; pooled
# connections would bind to a dead loop ("Event loop is closed").
_pool = {"poolclass": NullPool} if _s.env == "test" else {}
engine = create_async_engine(_s.database_url, pool_pre_ping=True, **_pool)
admin_engine = create_async_engine(_s.database_admin_url, pool_pre_ping=True, **_pool)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
AdminSessionLocal = async_sessionmaker(admin_engine, expire_on_commit=False)


@asynccontextmanager
async def admin_session() -> AsyncIterator[AsyncSession]:
    async with AdminSessionLocal() as s:
        yield s


async def set_tenant_context(session: AsyncSession, tenant_id) -> None:
    """Bind the request tenant into the CURRENT TRANSACTION (SET LOCAL).

    Transaction-scoped on purpose: the GUC dies at commit, so tenant-scoped
    work after a commit must go through deps.tenant_commit() which re-applies
    it. Connection pooling is untrusted (NullPool in tests) — never rely on a
    session-level SET surviving.
    """
    from sqlalchemy import text
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_id)}
    )
