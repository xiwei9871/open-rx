"""TASK-0001 endpoints. Every query is double-walled: explicit tenant/org
filter in the app layer + PostgreSQL RLS (app.tenant_id set by get_principal).

Cross-org object ids that are invisible are answered 403 — never 404 — so
existence cannot be probed (authz-test-matrix AZ-30..36).
"""
import secrets
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import payload_hash, record
from app.config import get_settings
from app.deps import Db, Me, Principal, require_perm, tenant_commit, _deny
from app.ratelimit import allow
from app.modules.audit.models import AuditEvent
from app.modules.iam.models import (
    Location, Membership, OrgConnection, Organization, RosterMember, UserAccount,
)
from app.modules.iam.schemas import (
    AuditEventOut, ConnectionTransition, LocationCreate, LocationOut,
    MemberInvite, MembershipOut, OrgConnectionOut, OrgConnectionRequest,
    OrgCreate, OrgOut, RosterMemberCreate, RosterMemberOut,
)
from app.security import hash_password

router = APIRouter(tags=["iam"])
_s = get_settings()


async def _limit_writes(p: Principal) -> None:
    """Sensitive-write throttle: per-user fixed window (B0.1)."""
    if not await allow("write", str(p.user.id),
                       _s.rl_write_limit, _s.rl_write_window):
        raise HTTPException(status_code=429, detail={
            "code": "rate_limited", "message": "Too many write operations"})


def _org_in_tenant(org: Organization | None, p: Principal) -> Organization:
    """Same-tenant check (RLS already scoped; belt for app-layer clarity)."""
    if not org or org.tenant_id != p.tenant_id:
        raise HTTPException(status_code=403, detail={
            "code": "forbidden", "message": "Access denied"})
    return org


async def _require_member_of(db: AsyncSession, p: Principal, org_id: uuid.UUID):
    if p.org.id != org_id:
        raise HTTPException(status_code=403, detail={
            "code": "forbidden", "message": "Access denied"})


# ---------------- organizations ----------------
@router.get("/orgs", response_model=dict, operation_id="listOrgs")
async def list_orgs(db: Db, p: Me):
    rows = (await db.execute(
        select(Organization).where(Organization.tenant_id == p.tenant_id)
        .order_by(Organization.created_at)
    )).scalars().all()
    return {"items": [OrgOut.model_validate(o) for o in rows], "next_cursor": None}


@router.post("/orgs", response_model=OrgOut, status_code=201, operation_id="createOrg")
async def create_org(body: OrgCreate, request: Request, db: Db,
                     p: Me, _g=Depends(require_perm("org:manage"))):
    await _limit_writes(p)
    org = Organization(tenant_id=p.tenant_id, kind=body.kind,
                       name=body.name, timezone=body.timezone)
    db.add(org)
    await db.flush()
    record(db, action="org.created", object_type="organization", object_id=org.id,
           tenant_id=p.tenant_id, org_id=org.id, actor_user_id=p.user.id,
           request=request, after=body.model_dump())
    await tenant_commit(db, p)
    return org


# ---------------- locations ----------------
@router.get("/orgs/{org_id}/locations", response_model=dict,
            operation_id="listLocations")
async def list_locations(org_id: uuid.UUID, db: Db, p: Me):
    await _require_member_of(db, p, org_id)
    rows = (await db.execute(
        select(Location).where(Location.org_id == org_id,
                               Location.tenant_id == p.tenant_id)
    )).scalars().all()
    return {"items": [LocationOut.model_validate(x) for x in rows]}


@router.post("/orgs/{org_id}/locations", response_model=LocationOut,
             status_code=201, operation_id="createLocation")
async def create_location(org_id: uuid.UUID, body: LocationCreate,
                          request: Request, db: Db,
                          p: Me, _g=Depends(require_perm("location:write"))):
    await _limit_writes(p)
    await _require_member_of(db, p, org_id)
    loc = Location(tenant_id=p.tenant_id, org_id=org_id, **body.model_dump())
    db.add(loc)
    await db.flush()
    record(db, action="location.created", object_type="location", object_id=loc.id,
           tenant_id=p.tenant_id, org_id=org_id, actor_user_id=p.user.id,
           request=request, after=body.model_dump())
    await tenant_commit(db, p)
    return loc


# ---------------- memberships ----------------
@router.get("/orgs/{org_id}/members", response_model=dict,
            operation_id="listMembers")
async def list_members(org_id: uuid.UUID, db: Db,
                       p: Me, _g=Depends(require_perm("member:write"))):
    await _require_member_of(db, p, org_id)
    rows = (await db.execute(
        select(Membership).where(Membership.org_id == org_id,
                                 Membership.tenant_id == p.tenant_id)
    )).scalars().all()
    return {"items": [MembershipOut.from_row(m) for m in rows]}


@router.post("/orgs/{org_id}/members", response_model=MembershipOut,
             status_code=201, operation_id="inviteMember")
async def invite_member(org_id: uuid.UUID, body: MemberInvite, request: Request,
                        db: Db, p: Me, _g=Depends(require_perm("member:write"))):
    await _limit_writes(p)
    await _require_member_of(db, p, org_id)
    email = body.email.lower()
    user = (await db.execute(
        select(UserAccount).where(UserAccount.email == email)
    )).scalar_one_or_none()
    if not user:
        pw = body.initial_password or secrets.token_urlsafe(12)
        user = UserAccount(email=email,
                           display_name=body.display_name or email.split("@")[0],
                           password_hash=hash_password(pw))
        db.add(user)
        await db.flush()
        record(db, action="user.created", object_type="user_account",
               object_id=user.id, tenant_id=p.tenant_id, org_id=org_id,
               actor_user_id=p.user.id, request=request)
    existing = (await db.execute(
        select(Membership).where(Membership.org_id == org_id,
                                 Membership.user_id == user.id)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail={
            "code": "conflict", "message": "Membership already exists"})
    m = Membership(tenant_id=p.tenant_id, org_id=org_id, user_id=user.id,
                   role=body.role, status="active")
    db.add(m)
    await db.flush()
    record(db, action="member.invited", object_type="membership", object_id=m.id,
           tenant_id=p.tenant_id, org_id=org_id, actor_user_id=p.user.id,
           request=request,
           after={"user_id": str(user.id), "role": body.role})
    m.user = user  # avoid lazy-load after flush (async cannot lazy-load)
    await tenant_commit(db, p)
    return MembershipOut.from_row(m)


# ---------------- roster ----------------
@router.get("/orgs/{org_id}/roster", response_model=dict,
            operation_id="listRoster")
async def list_roster(org_id: uuid.UUID, db: Db, p: Me):
    await _require_member_of(db, p, org_id)
    rows = (await db.execute(
        select(RosterMember).where(RosterMember.org_id == org_id,
                                   RosterMember.tenant_id == p.tenant_id)
    )).scalars().all()
    return {"items": [RosterMemberOut.model_validate(r) for r in rows]}


@router.post("/orgs/{org_id}/roster", response_model=RosterMemberOut,
             status_code=201, operation_id="addRosterMember")
async def add_roster(org_id: uuid.UUID, body: RosterMemberCreate,
                     request: Request, db: Db,
                     p: Me, _g=Depends(require_perm("roster:write"))):
    await _limit_writes(p)
    await _require_member_of(db, p, org_id)
    r = RosterMember(tenant_id=p.tenant_id, org_id=org_id, **body.model_dump())
    db.add(r)
    await db.flush()
    record(db, action="roster.created", object_type="roster_member",
           object_id=r.id, tenant_id=p.tenant_id, org_id=org_id,
           actor_user_id=p.user.id, request=request, after=body.model_dump(mode="json"))
    await tenant_commit(db, p)
    return r


# ---------------- org connections ----------------
@router.get("/org-connections", response_model=dict,
            operation_id="listOrgConnections")
async def list_connections(org_id: uuid.UUID, db: Db, p: Me):
    await _require_member_of(db, p, org_id)
    rows = (await db.execute(
        select(OrgConnection).where(
            OrgConnection.tenant_id == p.tenant_id,
            (OrgConnection.practice_org_id == org_id)
            | (OrgConnection.lab_org_id == org_id))
    )).scalars().all()
    return {"items": [OrgConnectionOut.model_validate(c) for c in rows]}


@router.post("/org-connections", response_model=OrgConnectionOut,
             status_code=201, operation_id="requestOrgConnection")
async def request_connection(body: OrgConnectionRequest, request: Request,
                             db: Db,
                             p: Me, _g=Depends(require_perm("connection:write"))):
    await _limit_writes(p)
    if p.org.id not in (body.practice_org_id, body.lab_org_id):
        raise HTTPException(status_code=403, detail={
            "code": "forbidden", "message": "Connection must involve caller's org"})
    pa = _org_in_tenant(await db.get(Organization, body.practice_org_id), p)
    la = _org_in_tenant(await db.get(Organization, body.lab_org_id), p)
    if pa.kind not in ("practice", "hybrid") or la.kind not in ("lab", "hybrid"):
        raise HTTPException(status_code=422, detail={
            "code": "validation_failed",
            "message": "practice_org_id must be practice, lab_org_id must be lab"})
    existing = (await db.execute(
        select(OrgConnection).where(
            OrgConnection.practice_org_id == body.practice_org_id,
            OrgConnection.lab_org_id == body.lab_org_id)
    )).scalar_one_or_none()
    if existing:
        if existing.status in ("pending", "accepted"):  # natural-key idempotency
            return existing
        # revoked/rejected/withdrawn -> re-request restarts as pending, with
        # the (possibly other side) caller stamped as the new initiator.
        before = payload_hash({"status": existing.status, "version": existing.version})
        existing.status = "pending"
        existing.initiated_by_org_id = p.org.id
        existing.decided_by_user_id = None
        existing.decided_at = None
        existing.granted_scopes = body.granted_scopes
        existing.version += 1
        record(db, action="connection.re_requested", object_type="org_connection",
               object_id=existing.id, tenant_id=p.tenant_id, org_id=p.org.id,
               actor_user_id=p.user.id, request=request,
               before={"status": before},
               after=body.model_dump(mode="json"))
        await tenant_commit(db, p)
        return existing
    c = OrgConnection(tenant_id=p.tenant_id, initiated_by_org_id=p.org.id,
                      **body.model_dump())
    db.add(c)
    await db.flush()
    record(db, action="connection.requested", object_type="org_connection",
           object_id=c.id, tenant_id=p.tenant_id, org_id=p.org.id,
           actor_user_id=p.user.id, request=request,
           after=body.model_dump(mode="json"))
    await tenant_commit(db, p)
    return c


@router.patch("/org-connections/{connection_id}",
              response_model=OrgConnectionOut,
              operation_id="transitionOrgConnection")
async def transition_connection(connection_id: uuid.UUID,
                                body: ConnectionTransition, request: Request,
                                db: Db,
                                p: Me, _g=Depends(require_perm("connection:write"))):
    await _limit_writes(p)
    c = await db.get(OrgConnection, connection_id)
    if not c or c.tenant_id != p.tenant_id \
            or p.org.id not in (c.practice_org_id, c.lab_org_id):
        await _deny(db, request, p, "connection_not_party")
    if body.expected_version != c.version:
        raise HTTPException(status_code=409, detail={
            "code": "version_conflict", "message": "Connection changed; reload"})

    # Direction rule (EasyRS security decision, V-14 pending): the side that
    # did NOT initiate decides accept/reject; the initiator may only withdraw;
    # revoke is bilateral on an accepted connection. Actor is always stamped.
    is_initiator = p.org.id == c.initiated_by_org_id
    if body.action in ("accept", "reject") and is_initiator:
        await _deny(db, request, p, "initiator_cannot_decide")
    if body.action == "withdraw" and not is_initiator:
        await _deny(db, request, p, "counterparty_cannot_withdraw")
    legal = {("pending", "accept"): "accepted",
             ("pending", "reject"): "rejected",
             ("pending", "withdraw"): "withdrawn",
             ("accepted", "revoke"): "revoked"}
    target = legal.get((c.status, body.action))
    if not target:
        raise HTTPException(status_code=422, detail={
            "code": "illegal_transition",
            "message": f"{body.action} not allowed from {c.status}"})
    if body.action == "accept" and body.granted_scopes is not None \
            and not set(body.granted_scopes) <= set(c.granted_scopes):
        raise HTTPException(status_code=422, detail={
            "code": "scope_expansion",
            "message": "accept may only narrow the requested scopes"})
    before = payload_hash({"status": c.status, "version": c.version})
    c.status = target
    c.version += 1
    if body.action in ("accept", "reject"):
        c.decided_by_user_id = p.user.id
        c.decided_at = datetime.now(UTC)
    if body.action == "accept" and body.granted_scopes is not None:
        c.granted_scopes = body.granted_scopes
    record(db, action=f"connection.{target}", object_type="org_connection",
           object_id=c.id, tenant_id=p.tenant_id, org_id=p.org.id,
           actor_user_id=p.user.id, request=request,
           before={"status": before}, after={"status": c.status})
    await tenant_commit(db, p)
    return c


# ---------------- audit ----------------
@router.get("/audit-events", response_model=dict, operation_id="listAuditEvents")
async def list_audit(db: Db, p: Me, _g=Depends(require_perm("audit:read")),
                     object_type: str | None = None,
                     object_id: str | None = None,
                     limit: int = 50):
    q = (select(AuditEvent)
         .where((AuditEvent.tenant_id == p.tenant_id) | AuditEvent.tenant_id.is_(None))
         .order_by(AuditEvent.ts.desc()).limit(min(limit, 200)))
    if object_type:
        q = q.where(AuditEvent.object_type == object_type)
    if object_id:
        q = q.where(AuditEvent.object_id == object_id)
    rows = (await db.execute(q)).scalars().all()
    return {"items": [AuditEventOut.model_validate(e) for e in rows],
            "next_cursor": None}
