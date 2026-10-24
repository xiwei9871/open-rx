"""Request-scoped dependencies: DB session, authenticated principal,
tenant context (RLS), and permission guards.

403 policy: identical shape whether the object exists or not — no oracle.
Denied access is audited (access_denied) per authz-test-matrix.md.
"""
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal, set_tenant_context
from app.modules.audit.models import AuditEvent
from app.modules.auth.models import AuthSession
from app.modules.iam.models import Membership, Organization, UserAccount
from app.security import ROLE_PERMISSIONS, token_hash

SESSION_COOKIE = "easyrs_session"

FORBIDDEN = HTTPException(
    status_code=403,
    detail={"code": "forbidden", "message": "Access denied"},
)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as s:
        yield s


async def tenant_commit(db: AsyncSession, p: "Principal") -> None:
    """Commit, then re-apply tenant context for the next transaction.

    SET LOCAL dies at commit; without re-applying, subsequent tenant-scoped
    reads hit deny-all RLS and return zero rows.
    """
    await db.commit()
    await set_tenant_context(db, p.tenant_id)


Db = Annotated[AsyncSession, Depends(get_db)]


@dataclass
class Principal:
    user: UserAccount
    session: AuthSession
    membership: Membership
    org: Organization

    @property
    def tenant_id(self) -> UUID:
        return self.org.tenant_id

    @property
    def permissions(self) -> frozenset[str]:
        return ROLE_PERMISSIONS.get(self.membership.role, frozenset())


async def _deny(db: AsyncSession, request: Request, p: "Principal | None", reason: str):
    db.add(AuditEvent(
        tenant_id=p.tenant_id if p else None,
        org_id=p.org.id if p else None,
        actor_user_id=p.user.id if p else None,
        action="access_denied",
        object_type="request",
        object_id=f"{request.method} {request.url.path}",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    raise FORBIDDEN


async def get_principal(request: Request, db: Db) -> Principal:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        raise HTTPException(status_code=401,
                            detail={"code": "unauthorized", "message": "Not authenticated"})
    sess = (await db.execute(
        select(AuthSession).where(AuthSession.token_hash == token_hash(raw))
    )).scalar_one_or_none()
    now = datetime.now(UTC)
    if not sess or sess.revoked_at or sess.expires_at <= now:
        raise HTTPException(status_code=401,
                            detail={"code": "unauthorized", "message": "Session invalid"})

    user = await db.get(UserAccount, sess.user_id)
    if not user or user.status != "active":
        raise HTTPException(status_code=401,
                            detail={"code": "unauthorized", "message": "Account disabled"})

    # Pin tenant FIRST (session carries it; NULL -> all tenant-scoped queries
    # return zero rows under RLS, which is the desired deny-by-default).
    await set_tenant_context(db, sess.tenant_id or "00000000-0000-0000-0000-000000000000")

    org_id = sess.active_org_id
    m = (await db.execute(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.status == "active",
            *((Membership.org_id == org_id,) if org_id else ()),
        ).order_by(Membership.created_at)
    )).scalars().first()
    if not m:
        raise HTTPException(status_code=403,
                            detail={"code": "forbidden", "message": "No active membership"})
    org = await db.get(Organization, m.org_id)
    if not org or org.status != "active":
        await _deny(db, request, None, "org_suspended_or_missing")

    principal = Principal(user=user, session=sess, membership=m, org=org)
    return principal


Me = Annotated[Principal, Depends(get_principal)]


def require_perm(perm: str):
    async def guard(request: Request, db: Db, p: Me) -> Principal:
        if perm not in p.permissions:
            await _deny(db, request, p, f"missing:{perm}")
        return p
    return guard
