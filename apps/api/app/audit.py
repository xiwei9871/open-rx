import hashlib
import json
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditEvent


def payload_hash(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()
    ).hexdigest()


def record(
    db: AsyncSession,
    *,
    action: str,
    object_type: str,
    object_id: UUID | str,
    tenant_id: UUID | None = None,
    org_id: UUID | None = None,
    actor_user_id: UUID | None = None,
    request: Request | None = None,
    before=None,
    after=None,
) -> AuditEvent:
    """Append an audit row inside the caller's transaction (no commit here)."""
    ev = AuditEvent(
        tenant_id=tenant_id,
        org_id=org_id,
        actor_user_id=actor_user_id,
        action=action,
        object_type=object_type,
        object_id=str(object_id),
        before_hash=payload_hash(before) if before is not None else None,
        after_hash=payload_hash(after) if after is not None else None,
        ip=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )
    db.add(ev)
    return ev
