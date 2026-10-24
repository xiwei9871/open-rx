"""Migration correctness: head applied, tables present, RLS enabled."""
import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio

RLS_TABLES = {"organization", "location", "membership", "roster_member",
              "org_connection", "audit_event"}
ALL_TABLES = RLS_TABLES | {"tenant", "user_account", "auth_session",
                           "auth_challenge"}


async def test_alembic_at_head(admindb):
    rev = (await admindb.execute(
        text("SELECT version_num FROM alembic_version"))).scalar_one()
    assert rev == "0001"


async def test_tables_exist(admindb):
    rows = {r[0] for r in (await admindb.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname='public'"))).all()}
    assert ALL_TABLES <= rows, rows


async def test_rls_enabled_on_tenant_scoped(admindb):
    rows = {r[0] for r in (await admindb.execute(text(
        "SELECT relname FROM pg_class WHERE relrowsecurity "
        "AND relnamespace='public'::regnamespace"))).all()}
    assert RLS_TABLES <= rows, rows


async def test_audit_append_only_policy(admindb):
    pols = {r[0] for r in (await admindb.execute(text(
        "SELECT polname FROM pg_policy p JOIN pg_class c ON p.polrelid=c.oid "
        "WHERE c.relname='audit_event'"))).all()}
    assert "audit_tenant_select" in pols and "audit_tenant_insert" in pols
