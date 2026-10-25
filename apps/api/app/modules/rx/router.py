"""S1b-Core Rx endpoints (docs/api/openapi.yaml, v1.1-rx-rules.md).

Visibility: practice members see Rxs their org issued; lab members see Rxs
addressed to their org once submitted. Draft rows are never lab-visible.

Transitions (all row-locked, all recorded in rx_transition + audit):
  draft -> submitted    POST /rx/{id}/submit      (practice; needs accepted
                                                 org_connection to lab_org_id)
  submitted -> draft    POST /rx/{id}/unsubmit    (practice; 409 once
                                                 checked_in — CONFIRMED rule)
  submitted -> checked_in  POST /rx/{id}/check-in (lab) or lab bundle download
Lab-side bundle download IS a check-in act (SRC03, V-02) — checked_in_via
records which path fired.
"""
import asyncio
import base64
import hashlib
import json
import os
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record
from app.deps import (Db, Me, Principal, _deny, limit_writes, require_perm,
                      tenant_commit)
from app.modules.clinical.models import Patient, TreatmentCase
from app.modules.iam.models import (Location, OrgConnection, Organization,
                                    RosterMember)
from app.storage import s3, s3_presign
from app.modules.rx.models import (Approval, CatalogItem, IdempotencyRecord,
                                   Notification, Rx, RxBundle, RxComment,
                                   RxItem, RxTemplate, RxTransition)
from app.modules.rx.schemas import (ApprovalOut, AttachmentCreate,
                                    CatalogItemOut, CommentCreate, CommentOut,
                                    DecisionRequest, NotificationCreate,
                                    NotificationOut, RxBundleOut, RxCheckIn,
                                    RxCreate, RxItemOut, RxItemsReplace, RxOut,
                                    RxSubmit, RxTemplateCreate, RxTemplateOut,
                                    RxTransitionOut, RxUnsubmit, RxUpdate)

router = APIRouter(tags=["prescriptions"])

LAB_VISIBLE_STATUSES = ("submitted", "checked_in", "in_progress", "on_hold",
                        "completed", "reopened")


# ---------------- helpers ----------------------------------------------------
def _is_party(p: Principal, rx: Rx) -> bool:
    if rx.practice_org_id == p.org.id:
        return True
    return (rx.lab_org_id == p.org.id
            and rx.status in LAB_VISIBLE_STATUSES)


async def _rx_for_read(db: AsyncSession, p: Principal, rx_id: uuid.UUID,
                       request: Request) -> Rx:
    rx = await db.get(Rx, rx_id)
    if not rx or rx.tenant_id != p.tenant_id or not _is_party(p, rx):
        await _deny(db, request, p, "rx_not_visible")
    return rx


async def _rx_for_practice_write(db: AsyncSession, p: Principal,
                                 rx_id: uuid.UUID, request: Request) -> Rx:
    """Issuing-org mutation gate — row-locked."""
    rx = await db.get(Rx, rx_id, with_for_update=True)
    if (not rx or rx.tenant_id != p.tenant_id
            or rx.practice_org_id != p.org.id):
        await _deny(db, request, p, "rx_not_owned")
    return rx


async def _rx_for_lab_write(db: AsyncSession, p: Principal,
                            rx_id: uuid.UUID, request: Request) -> Rx:
    """Receiving-lab mutation gate — row-locked."""
    rx = await db.get(Rx, rx_id, with_for_update=True)
    if (not rx or rx.tenant_id != p.tenant_id or rx.lab_org_id != p.org.id
            or rx.status not in LAB_VISIBLE_STATUSES):
        await _deny(db, request, p, "rx_not_addressed_to_lab")
    return rx


def _vconflict() -> HTTPException:
    return HTTPException(status_code=409, detail={
        "code": "version_conflict", "message": "Rx changed; reload"})


def _require_if_match(if_match: int | None, version: int) -> None:
    """Optimistic-locking gate (S1b1-04): mutating endpoints REQUIRE the
    client's last-seen version. Missing -> 428, stale -> 409."""
    if if_match is None:
        raise HTTPException(status_code=428, detail={
            "code": "precondition_required",
            "message": "If-Match header required"})
    if if_match != version:
        raise _vconflict()


def _illegal(msg: str) -> HTTPException:
    return HTTPException(status_code=422, detail={
        "code": "illegal_transition", "message": msg})


def _record_transition(db: AsyncSession, p: Principal, rx: Rx,
                       frm: str | None, to: str, via: str,
                       note: str | None = None) -> None:
    db.add(RxTransition(
        tenant_id=p.tenant_id, rx_id=rx.id, from_status=frm, to_status=to,
        via=via, actor_user_id=p.user.id, actor_org_id=p.org.id, note=note))


async def _rx_out(db: AsyncSession, rx: Rx) -> dict:
    items = (await db.execute(
        select(RxItem).where(RxItem.rx_id == rx.id)
        .order_by(RxItem.created_at, RxItem.id))).scalars().all()
    out = RxOut.model_validate(rx).model_dump(mode="json")
    out["items"] = [
        {**RxItemOut(
            id=i.id, appliance_id=i.catalog_item_id, arch=i.arch,
            tooth_ops=i.tooth_ops, options=i.options, qty=i.qty,
        ).model_dump(mode="json")}
        for i in items]
    return out


def _payload_hash(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, default=str, sort_keys=True)
                          .encode()).hexdigest()


# ---------------- catalog ----------------------------------------------------
@router.get("/catalog/parts", response_model=dict, operation_id="listParts")
async def list_parts(db: Db, p: Me, _g=Depends(require_perm("rx:read"))):
    """Universal library + items owned by labs this org may address."""
    rows = (await db.execute(
        select(CatalogItem)
        .where(CatalogItem.active.is_(True),
               CatalogItem.kind == "part",
               or_(CatalogItem.owner_org_id.is_(None),
                   CatalogItem.owner_org_id.in_(
                       select(OrgConnection.lab_org_id).where(
                           OrgConnection.practice_org_id == p.org.id,
                           OrgConnection.status == "accepted"))))
        .order_by(CatalogItem.code))).scalars().all()
    return {"items": [CatalogItemOut.model_validate(r) for r in rows]}


@router.get("/catalog/appliances", response_model=dict,
            operation_id="listAppliances")
async def list_appliances(db: Db, p: Me, _g=Depends(require_perm("rx:read"))):
    rows = (await db.execute(
        select(CatalogItem)
        .where(CatalogItem.active.is_(True),
               CatalogItem.kind == "appliance",
               or_(CatalogItem.owner_org_id.is_(None),
                   CatalogItem.owner_org_id.in_(
                       select(OrgConnection.lab_org_id).where(
                           OrgConnection.practice_org_id == p.org.id,
                           OrgConnection.status == "accepted"))))
        .order_by(CatalogItem.code))).scalars().all()
    return {"items": [CatalogItemOut.model_validate(r) for r in rows]}


# ---------------- rx templates (RX-010, practice-owned; sharing DEFER) --------
def _template_visible(t: RxTemplate | None, p: Principal) -> RxTemplate:
    if not t or t.tenant_id != p.tenant_id or t.org_id != p.org.id:
        raise HTTPException(status_code=403, detail={
            "code": "forbidden", "message": "Access denied"})
    return t


async def _validate_template_payload(db: AsyncSession, p: Principal,
                                     payload: dict) -> dict:
    items = payload.get("items")
    if not isinstance(items, list):
        raise HTTPException(status_code=422, detail={
            "code": "invalid_template",
            "message": "payload.items must be a list"})
    ids = []
    for it in items:
        if not isinstance(it, dict) or not it.get("catalog_item_id"):
            raise HTTPException(status_code=422, detail={
                "code": "invalid_template",
                "message": "each item needs catalog_item_id"})
        try:
            ids.append(uuid.UUID(str(it["catalog_item_id"])))
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail={
                "code": "invalid_template",
                "message": "catalog_item_id must be a UUID"}) from None
    if ids:
        found = (await db.execute(select(CatalogItem.id).where(
            CatalogItem.id.in_(ids), CatalogItem.active.is_(True),
            or_(CatalogItem.owner_org_id.is_(None),
                CatalogItem.owner_org_id == p.org.id,
                CatalogItem.owner_org_id.in_(
                    select(OrgConnection.lab_org_id).where(
                        OrgConnection.practice_org_id == p.org.id,
                        OrgConnection.status == "accepted"))))
        )).scalars().all()
        if len(found) != len(set(ids)):
            raise HTTPException(status_code=422, detail={
                "code": "invalid_template",
                "message": "template references an unknown or inactive catalog item"})
    return payload


@router.get("/templates", response_model=dict, operation_id="listTemplates")
async def list_rx_templates(db: Db, p: Me,
                            _g=Depends(require_perm("rx:read"))):
    rows = (await db.execute(
        select(RxTemplate).where(RxTemplate.org_id == p.org.id,
                                 RxTemplate.tenant_id == p.tenant_id)
        .order_by(RxTemplate.name))).scalars().all()
    return {"items": [RxTemplateOut.model_validate(t) for t in rows]}


@router.post("/templates", response_model=RxTemplateOut, status_code=201,
             operation_id="createTemplate")
async def create_rx_template(body: RxTemplateCreate, request: Request, db: Db,
                             p: Me, _g=Depends(require_perm("rx:write"))):
    await limit_writes(p)
    if p.org.kind == "lab":
        await _deny(db, request, p, "lab_template_forbidden")
    payload = await _validate_template_payload(db, p, body.payload)
    t = RxTemplate(tenant_id=p.tenant_id, org_id=p.org.id,
                   created_by_user_id=p.user.id, name=body.name,
                   payload=payload)
    db.add(t)
    await db.flush()
    record(db, action="rx_template.created", object_type="rx_template",
           object_id=t.id, tenant_id=p.tenant_id, org_id=p.org.id,
           actor_user_id=p.user.id, request=request,
           after={"name": body.name})
    await tenant_commit(db, p)
    return t


@router.get("/templates/{template_id}", response_model=RxTemplateOut,
            operation_id="getTemplate")
async def get_rx_template(template_id: uuid.UUID, request: Request, db: Db,
                          p: Me, _g=Depends(require_perm("rx:read"))):
    t = await db.get(RxTemplate, template_id)
    try:
        return _template_visible(t, p)
    except HTTPException:
        await _deny(db, request, p, "rx_template_not_visible")


@router.delete("/templates/{template_id}", status_code=204,
               operation_id="deleteTemplate")
async def delete_rx_template(template_id: uuid.UUID, request: Request, db: Db,
                             p: Me, _g=Depends(require_perm("rx:write"))):
    await limit_writes(p)
    t = await db.get(RxTemplate, template_id)
    try:
        _template_visible(t, p)
    except HTTPException:
        await _deny(db, request, p, "rx_template_not_visible")
    await db.delete(t)
    record(db, action="rx_template.deleted", object_type="rx_template",
           object_id=template_id, tenant_id=p.tenant_id, org_id=p.org.id,
           actor_user_id=p.user.id, request=request)
    await tenant_commit(db, p)


# ---------------- rx ----------------------------------------------------------
@router.get("/rx", response_model=dict, operation_id="listRx")
async def list_rx(db: Db, p: Me, _g=Depends(require_perm("rx:read")),
                  status: str | None = None, date_from: str | None = None,
                  date_to: str | None = None,
                  location_id: uuid.UUID | None = None,
                  doctor_id: uuid.UUID | None = None,
                  tag_id: uuid.UUID | None = None,
                  limit: int = 25, cursor: str | None = None):
    lim = min(max(limit, 1), 100)
    # Lab principals (no patient access) list their receiving inbox; practice
    # and hybrid orgs list issued Rxs.
    if "patient:read" not in p.permissions:
        conds = [Rx.lab_org_id == p.org.id,
                 Rx.status.in_(LAB_VISIBLE_STATUSES)]
    else:
        conds = [Rx.practice_org_id == p.org.id]
    if status:
        conds.append(Rx.status == status)
    if date_from:
        conds.append(Rx.created_at >= date_from)
    if date_to:
        conds.append(Rx.created_at <= f"{date_to}T23:59:59+00:00")
    if location_id:
        conds.append(Rx.location_id == location_id)
    if doctor_id:
        conds.append(Rx.doctor_id == doctor_id)
    counts = dict((await db.execute(
        select(Rx.status, func.count()).where(*conds)
        .group_by(Rx.status))).all())
    offset = int(base64.b64decode(cursor)) if cursor else 0
    rows = (await db.execute(
        select(Rx).where(*conds)
        .order_by(Rx.created_at.desc(), Rx.id).offset(offset)
        .limit(lim + 1))).scalars().all()
    nxt = (base64.b64encode(str(offset + lim).encode()).decode()
           if len(rows) > lim else None)
    return {"items": [RxOut.model_validate(r) for r in rows[:lim]],
            "next_cursor": nxt, "counts": counts}


@router.post("/rx", status_code=201, operation_id="createRx")
async def create_rx(body: RxCreate, request: Request, db: Db, p: Me,
                    _g=Depends(require_perm("rx:write"))):
    await limit_writes(p)
    if p.org.kind == "lab":
        await _deny(db, request, p, "labs_cannot_issue_rx")
    pat = await db.get(Patient, body.patient_id)
    if not pat or pat.tenant_id != p.tenant_id or pat.org_id != p.org.id \
            or pat.deleted_at is not None:
        await _deny(db, request, p, "patient_not_in_org")
    if body.case_id:
        c = await db.get(TreatmentCase, body.case_id)
        if not c or c.patient_id != pat.id:
            raise HTTPException(status_code=422, detail={
                "code": "case_mismatch",
                "message": "case_id does not belong to this patient"})
    if body.lab_org_id:
        await _validate_lab(db, p, body.lab_org_id, request)
    if body.location_id:
        loc = await db.get(Location, body.location_id)
        if not loc or loc.org_id != p.org.id:
            raise HTTPException(status_code=422, detail={
                "code": "invalid_location",
                "message": "location_id is not a location of this org"})
    if body.doctor_id:
        doc = await db.get(RosterMember, body.doctor_id)
        if not doc or doc.org_id != p.org.id or doc.status != "active":
            raise HTTPException(status_code=422, detail={
                "code": "invalid_doctor",
                "message": "doctor_id is not an active roster member"})
    num = (await db.execute(text("SELECT nextval('rx_number_seq')"))).scalar()
    rx = Rx(
        tenant_id=p.tenant_id, practice_org_id=p.org.id,
        rx_number=f"RX{num:06d}", patient_id=pat.id, case_id=body.case_id,
        lab_org_id=body.lab_org_id, location_id=body.location_id,
        doctor_id=body.doctor_id, form_type=body.form_type,
        due_date=body.due_date, notes=body.notes,
        created_by_user_id=p.user.id)
    db.add(rx)
    await db.flush()
    _record_transition(db, p, rx, None, "draft", via="button",
                       note="created")
    record(db, action="rx.created", object_type="rx", object_id=rx.id,
           tenant_id=p.tenant_id, org_id=p.org.id, actor_user_id=p.user.id,
           request=request, after={"rx_number": rx.rx_number})
    await tenant_commit(db, p)
    return await _rx_out(db, rx)


async def _validate_lab(db: AsyncSession, p: Principal, lab_org_id: uuid.UUID,
                        request: Request) -> None:
    lab = await db.get(Organization, lab_org_id)
    if (not lab or lab.tenant_id != p.tenant_id
            or lab.kind not in ("lab", "hybrid") or lab.status != "active"):
        raise HTTPException(status_code=422, detail={
            "code": "invalid_lab", "message": "lab_org_id is not a lab org"})


@router.get("/rx/{rx_id}", operation_id="getRx")
async def get_rx(rx_id: uuid.UUID, request: Request, db: Db, p: Me,
                 _g=Depends(require_perm("rx:read"))):
    rx = await _rx_for_read(db, p, rx_id, request)
    return await _rx_out(db, rx)


@router.patch("/rx/{rx_id}", operation_id="updateRx")
async def update_rx(rx_id: uuid.UUID, body: RxUpdate, request: Request,
                    db: Db, p: Me, _g=Depends(require_perm("rx:write")),
                    if_match: int | None = Header(default=None)):
    await limit_writes(p)
    rx = await _rx_for_practice_write(db, p, rx_id, request)
    _require_if_match(if_match, rx.version)
    if rx.status != "draft":
        raise _illegal("Only draft (Saved) prescriptions can be edited")
    data = body.model_dump(exclude_unset=True)
    if "lab_org_id" in data and data["lab_org_id"]:
        await _validate_lab(db, p, data["lab_org_id"], request)
    if "location_id" in data and data["location_id"]:
        loc = await db.get(Location, data["location_id"])
        if not loc or loc.org_id != p.org.id:
            raise HTTPException(status_code=422, detail={
                "code": "invalid_location",
                "message": "location_id is not a location of this org"})
    if "doctor_id" in data and data["doctor_id"]:
        doc = await db.get(RosterMember, data["doctor_id"])
        if not doc or doc.org_id != p.org.id or doc.status != "active":
            raise HTTPException(status_code=422, detail={
                "code": "invalid_doctor",
                "message": "doctor_id is not an active roster member"})
    for k, v in data.items():
        setattr(rx, k, v)
    rx.version += 1
    record(db, action="rx.updated", object_type="rx", object_id=rx.id,
           tenant_id=p.tenant_id, org_id=p.org.id, actor_user_id=p.user.id,
           request=request, after={k: str(v) for k, v in data.items()})
    await tenant_commit(db, p)
    return await _rx_out(db, rx)


@router.put("/rx/{rx_id}/items", operation_id="replaceRxItems")
async def replace_rx_items(rx_id: uuid.UUID, body: RxItemsReplace,
                           request: Request, db: Db, p: Me,
                           _g=Depends(require_perm("rx:write")),
                           if_match: int | None = Header(default=None)):
    await limit_writes(p)
    rx = await _rx_for_practice_write(db, p, rx_id, request)
    _require_if_match(if_match, rx.version)
    if rx.status != "draft":
        raise _illegal("Items can only be changed while status=draft")
    ids = {i.appliance_id for i in body.items}
    cat = (await db.execute(
        select(CatalogItem).where(CatalogItem.id.in_(ids or {uuid.uuid4()}),
                                  CatalogItem.active.is_(True))
    )).scalars().all()
    by_id = {c.id: c for c in cat}
    for item in body.items:
        c = by_id.get(item.appliance_id)
        if not c:
            raise HTTPException(status_code=422, detail={
                "code": "unknown_catalog_item",
                "message": f"{item.appliance_id} is not an active catalog item"})
        if (c.owner_org_id is not None
                and c.owner_org_id != rx.lab_org_id):
            raise HTTPException(status_code=422, detail={
                "code": "catalog_item_not_for_lab",
                "message": f"{c.code} is owned by a different lab"})
        if c.arch_scope != "both" and item.arch != c.arch_scope:
            raise HTTPException(status_code=422, detail={
                "code": "arch_mismatch",
                "message": f"{c.code} only supports arch={c.arch_scope}"})
        # V1.1 evidence: option fields can be mandatory (Prompt for Bands).
        required = (c.option_schema or {}).get("required", [])
        missing = [k for k in required if not (item.options or {}).get(k)]
        if missing:
            raise HTTPException(status_code=422, detail={
                "code": "required_option_missing",
                "message": f"{c.code} requires options: {', '.join(missing)}"})
    old = (await db.execute(
        select(RxItem).where(RxItem.rx_id == rx.id))).scalars().all()
    for i in old:
        await db.delete(i)
    for item in body.items:
        db.add(RxItem(
            tenant_id=p.tenant_id, rx_id=rx.id,
            catalog_item_id=item.appliance_id, arch=item.arch,
            tooth_ops=[t.model_dump() for t in item.tooth_ops],
            options=item.options, qty=item.qty))
    rx.version += 1
    record(db, action="rx.items_replaced", object_type="rx", object_id=rx.id,
           tenant_id=p.tenant_id, org_id=p.org.id, actor_user_id=p.user.id,
           request=request, after={"count": len(body.items)})
    await tenant_commit(db, p)
    return {"items": (await _rx_out(db, rx))["items"]}


@router.post("/rx/{rx_id}/submit", operation_id="submitRx")
async def submit_rx(rx_id: uuid.UUID, request: Request, db: Db, p: Me,
                    body: RxSubmit,
                    _g=Depends(require_perm("rx:write")),
                    idempotency_key: str | None = Header(default=None),
                    if_match: int | None = Header(default=None)):
    await limit_writes(p)
    if idempotency_key is None:
        raise HTTPException(status_code=422, detail={
            "code": "validation_failed",
            "message": "Idempotency-Key header required"})
    # S1b1-03 signature gate — validated BEFORE any state work so a rejected
    # submit leaves no transition, no audit row, no idempotency record.
    if not body.signature_name or not body.signature_name.strip():
        raise HTTPException(status_code=422, detail={
            "code": "signature_required",
            "message": "A non-empty signature_name is required to submit"})
    if not body.confirm_submit:
        raise HTTPException(status_code=422, detail={
            "code": "confirmation_required",
            "message": "confirm_submit must be true to submit"})
    ph = _payload_hash(rx_id, body.model_dump(), if_match)
    # Replay short-circuit, scoped to (tenant, org, user, endpoint, key):
    # first result wins, later state never leaks back (Final Gate F5).
    prior = (await db.execute(select(IdempotencyRecord).where(
        IdempotencyRecord.tenant_id == p.tenant_id,
        IdempotencyRecord.org_id == p.org.id,
        IdempotencyRecord.user_id == p.user.id,
        IdempotencyRecord.endpoint == "submitRx",
        IdempotencyRecord.key == idempotency_key))).scalar_one_or_none()
    if prior:
        if prior.request_hash != ph:
            raise HTTPException(status_code=409, detail={
                "code": "idempotency_payload_mismatch",
                "message": "Idempotency-Key reuse with different payload"})
        # Object authorization still applies on replay — a principal who
        # lost access must not receive the recorded snapshot.
        rid = (prior.response_json or {}).get("id")
        snap_rx = await db.get(Rx, uuid.UUID(rid)) if rid else None
        if (not snap_rx or snap_rx.tenant_id != p.tenant_id
                or not _is_party(p, snap_rx)):
            await _deny(db, request, p, "rx_not_visible")
        return prior.response_json
    rx = await _rx_for_practice_write(db, p, rx_id, request)
    _require_if_match(if_match, rx.version)
    if rx.status != "draft":
        raise _illegal("Only draft (Saved) prescriptions can be submitted")
    if rx.lab_org_id is None:
        raise HTTPException(status_code=422, detail={
            "code": "no_lab_selected",
            "message": "A laboratory must be selected before submit"})
    conn = (await db.execute(select(OrgConnection).where(
        OrgConnection.practice_org_id == p.org.id,
        OrgConnection.lab_org_id == rx.lab_org_id,
        OrgConnection.status == "accepted"))).scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=422, detail={
            "code": "no_accepted_connection",
            "message": "No accepted connection to this laboratory"})
    n_items = (await db.execute(
        select(func.count()).select_from(RxItem)
        .where(RxItem.rx_id == rx.id))).scalar_one()
    if n_items == 0:
        raise HTTPException(status_code=422, detail={
            "code": "validation_failed",
            "message": "At least one part/appliance is required"})
    signed_version = rx.version  # the version the signature binds
    rx.status = "submitted"
    rx.submitted_at = datetime.now(UTC)
    rx.submitted_by_user_id = p.user.id
    rx.signature_name = body.signature_name.strip()
    rx.signed_rx_version = signed_version
    rx.version += 1
    _record_transition(db, p, rx, "draft", "submitted", via="button",
                       note=body.note)
    record(db, action="rx.submitted", object_type="rx", object_id=rx.id,
           tenant_id=p.tenant_id, org_id=p.org.id, actor_user_id=p.user.id,
           request=request,
           after={"lab_org_id": str(rx.lab_org_id),
                  "signature_name": rx.signature_name,
                  "signed_rx_version": signed_version})
    out = await _rx_out(db, rx)
    db.add(IdempotencyRecord(
        tenant_id=p.tenant_id, org_id=p.org.id, user_id=p.user.id,
        endpoint="submitRx", key=idempotency_key, request_hash=ph,
        response_status=200, response_json=out))
    await tenant_commit(db, p)
    return out


@router.post("/rx/{rx_id}/unsubmit", operation_id="unsubmitRx")
async def unsubmit_rx(rx_id: uuid.UUID, request: Request, db: Db, p: Me,
                      body: RxUnsubmit | None = None,
                      _g=Depends(require_perm("rx:write")),
                      if_match: int | None = Header(default=None)):
    await limit_writes(p)
    rx = await _rx_for_practice_write(db, p, rx_id, request)
    _require_if_match(if_match, rx.version)
    # CONFIRMED rule (SRC03): a checked-in Rx cannot be pulled back.
    if rx.status == "checked_in" or rx.checked_in_at is not None:
        raise HTTPException(status_code=409, detail={
            "code": "already_checked_in",
            "message": "Lab has checked in this prescription; "
                       "it can no longer be unsubmitted"})
    if rx.status != "submitted":
        raise _illegal("Only submitted prescriptions can be unsubmitted")
    rx.status = "draft"
    rx.submitted_at = None
    rx.submitted_by_user_id = None
    rx.submit_idem_key = None
    rx.submit_idem_hash = None
    rx.version += 1
    _record_transition(db, p, rx, "submitted", "draft", via="button",
                       note=(body or RxUnsubmit()).reason)
    record(db, action="rx.unsubmitted", object_type="rx", object_id=rx.id,
           tenant_id=p.tenant_id, org_id=p.org.id, actor_user_id=p.user.id,
           request=request)
    await tenant_commit(db, p)
    return await _rx_out(db, rx)


@router.post("/rx/{rx_id}/check-in", operation_id="checkInRx")
async def check_in_rx(rx_id: uuid.UUID, request: Request, db: Db, p: Me,
                      body: RxCheckIn | None = None,
                      _g=Depends(require_perm("rx:write")),
                      idempotency_key: str | None = Header(default=None),
                      if_match: int | None = Header(default=None)):
    await limit_writes(p)
    rx = await _rx_for_lab_write(db, p, rx_id, request)
    if rx.status == "checked_in":
        return await _rx_out(db, rx)  # idempotent repeat — no second event
    _require_if_match(if_match, rx.version)
    if rx.status != "submitted":
        raise _illegal("Only submitted prescriptions can be checked in")
    _apply_checkin(db, p, rx, via="button", note=(body or RxCheckIn()).note)
    await tenant_commit(db, p)
    return await _rx_out(db, rx)


@router.post("/rx/{rx_id}/complete", operation_id="completeRx")
async def complete_rx(rx_id: uuid.UUID, request: Request, db: Db, p: Me,
                      body: RxCheckIn | None = None,
                      _g=Depends(require_perm("rx:write")),
                      if_match: int | None = Header(default=None)):
    """LAB-019: lab marks the order complete (production done). checked_in
    -> completed; idempotent repeat returns the same state."""
    await limit_writes(p)
    rx = await _rx_for_lab_write(db, p, rx_id, request)
    if rx.status == "completed":
        return await _rx_out(db, rx)  # idempotent repeat
    _require_if_match(if_match, rx.version)
    if rx.status != "checked_in":
        raise _illegal("Only checked-in prescriptions can be completed")
    rx.status = "completed"
    rx.completed_at = datetime.now(UTC)
    rx.completed_by_user_id = p.user.id
    rx.version += 1
    _record_transition(db, p, rx, "checked_in", "completed", via="button",
                       note=(body or RxCheckIn()).note)
    record(db, action="rx.completed", object_type="rx", object_id=rx.id,
           tenant_id=p.tenant_id, org_id=p.org.id, actor_user_id=p.user.id,
           request=request)
    await tenant_commit(db, p)
    return await _rx_out(db, rx)


def _apply_checkin(db: AsyncSession, p: Principal, rx: Rx, via: str,
                   note: str | None = None) -> None:
    rx.status = "checked_in"
    rx.checked_in_at = datetime.now(UTC)
    rx.checked_in_by_user_id = p.user.id
    rx.checked_in_via = via
    rx.version += 1
    _record_transition(db, p, rx, "submitted", "checked_in", via=via,
                       note=note)


@router.get("/rx/{rx_id}/bundle", response_model=dict,
            operation_id="listRxBundles")
async def list_rx_bundles(rx_id: uuid.UUID, request: Request, db: Db,
                          p: Me, _g=Depends(require_perm("rx:read"))):
    """Read-only list of prepared delivery bundles. No state change —
    safe for browser prefetch (S1b1-02)."""
    rx = await _rx_for_read(db, p, rx_id, request)
    rows = (await db.execute(
        select(RxBundle).where(RxBundle.rx_id == rx.id,
                               RxBundle.status == "ready")
        .order_by(RxBundle.created_at.desc()))).scalars().all()
    return {"items": [RxBundleOut.model_validate(b) for b in rows]}


_BUNDLE_URL_TTL = 900


@router.post("/rx/{rx_id}/bundle-download", operation_id="downloadRxBundle")
async def download_rx_bundle(rx_id: uuid.UUID, request: Request, db: Db,
                             p: Me, _g=Depends(require_perm("rx:write"))):
    """Two-phase delivery (S1b1-02):
    Phase A — build+verify the ZIP outside any state transition. Any
              storage/hash failure aborts BEFORE the Rx row is touched.
    Phase B — atomically persist the bundle record; for a lab caller on a
              submitted Rx this IS the check-in act (SRC03:
              checked_in_via='download'). Practice callers never trigger
              check-in. Repeat calls reuse the ready bundle for the same
              Rx version — no duplicate package or second check-in event.
    Returns a short-lived presigned URL; the actual byte fetch is a pure
    GET against object storage."""
    await limit_writes(p)
    from app.config import get_settings
    from app.modules.rx.bundle import (BundleError, build_bundle,
                                       bundle_key, rx_snapshot,
                                       snapshot_fingerprint)
    rx = await db.get(Rx, rx_id, with_for_update=True)
    if not rx or rx.tenant_id != p.tenant_id or not _is_party(p, rx):
        await _deny(db, request, p, "rx_not_visible")
    if rx.status == "draft":
        raise _illegal("Draft prescriptions have no delivery bundle")

    # Content-fingerprint reuse (Final Gate F2 + consistency fix): the
    # canonical rx_snapshot feeds BOTH the fingerprint and the rendered
    # PDF/manifest, so a reuse decision can never disagree with what the
    # package would contain. Status/version are volatile — excluded.
    snap = await rx_snapshot(db, rx)
    fp = snapshot_fingerprint(snap)
    existing = (await db.execute(select(RxBundle).where(
        RxBundle.rx_id == rx.id, RxBundle.status == "ready",
        RxBundle.content_fingerprint == fp)
        .order_by(RxBundle.created_at.desc()))).scalars().first()
    s = get_settings()
    created_new = False

    if existing is None:
        # Phase A — build outside the state transition, from the SAME
        # snapshot the fingerprint was computed on.
        try:
            path, sha, size, _manifest = await build_bundle(
                db, rx, snap)
        except BundleError as e:
            raise HTTPException(status_code=502, detail={
                "code": "bundle_build_failed", "message": str(e)})
        bundle_id = uuid.uuid4()
        key = bundle_key(p.tenant_id, rx.id, bundle_id)
        try:
            with open(path, "rb") as fh:
                await asyncio.to_thread(
                    s3().put_object, Bucket=s.s3_bucket, Key=key, Body=fh)
        except Exception as e:
            raise HTTPException(status_code=502, detail={
                "code": "bundle_upload_failed",
                "message": f"delivery package could not be stored: {e}"})
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        existing = RxBundle(
            tenant_id=p.tenant_id, rx_id=rx.id, org_id=p.org.id,
            created_by_user_id=p.user.id, rx_version=rx.version,
            content_fingerprint=fp,
            storage_key=key, sha256=sha, bytes=size, status="ready")
        db.add(existing)
        created_new = True

    # Phase B — flush, presign and commit inside one compensated region.
    # PostgreSQL and S3 share no ACID transaction: if ANY step after the
    # upload fails (flush, URL minting, commit) the uploaded object is
    # deleted so storage never claims a delivery the database did not
    # record, and the Rx is never left half-checked-in.
    try:
        if created_new:
            await db.flush()
        url = await asyncio.to_thread(
            s3_presign().generate_presigned_url, "get_object",
            Params={"Bucket": s.s3_bucket, "Key": existing.storage_key},
            ExpiresIn=_BUNDLE_URL_TTL)
        if rx.status == "submitted" and rx.lab_org_id == p.org.id:
            _apply_checkin(db, p, rx, via="download",
                           note="bundle download accepted check-in")
            record(db, action="rx.checked_in", object_type="rx",
                   object_id=rx.id, tenant_id=p.tenant_id, org_id=p.org.id,
                   actor_user_id=p.user.id, request=request,
                   after={"via": "download", "bundle_id": str(existing.id)})
        record(db, action="rx.bundle_downloaded", object_type="rx",
               object_id=rx.id, tenant_id=p.tenant_id, org_id=p.org.id,
               actor_user_id=p.user.id, request=request,
               after={"bundle_id": str(existing.id),
                      "sha256": existing.sha256})
        await tenant_commit(db, p)
    except Exception:
        if created_new:
            try:
                await asyncio.to_thread(
                    s3().delete_object, Bucket=s.s3_bucket,
                    Key=existing.storage_key)
            except Exception:
                pass
        raise

    return {"bundle": RxBundleOut.model_validate(existing),
            "download_url": url, "expires_in": _BUNDLE_URL_TTL}


@router.get("/rx/{rx_id}/attachments", response_model=dict,
            operation_id="listRxAttachments")
async def list_rx_attachments(rx_id: uuid.UUID, request: Request, db: Db,
                              p: Me, _g=Depends(require_perm("rx:read"))):
    """Live file references on the Rx + asset metadata (id/kind/jaw/bytes)."""
    from app.modules.assets.models import Asset, FileReference
    await _rx_for_read(db, p, rx_id, request)
    rows = (await db.execute(
        select(FileReference, Asset)
        .join(Asset, Asset.id == FileReference.asset_id)
        .where(FileReference.subject_type == "rx",
               FileReference.subject_id == rx_id,
               FileReference.revoked_at.is_(None)))).all()
    return {"items": [{
        "id": str(ref.id), "asset_id": str(asset.id),
        "subject_type": "rx", "subject_id": str(rx_id),
        "role": ref.role, "revoked_at": None,
        "asset": {"id": str(asset.id), "kind": asset.kind,
                  "jaw": asset.jaw, "bytes": asset.bytes,
                  "sha256": asset.sha256, "format_status": asset.format_status,
                  "created_at": asset.created_at.isoformat()},
    } for ref, asset in rows]}


@router.post("/rx/{rx_id}/attachments", status_code=201,
             operation_id="attachToRx")
async def attach_to_rx(rx_id: uuid.UUID, body: AttachmentCreate,
                       request: Request, db: Db, p: Me,
                       _g=Depends(require_perm("rx:write"))):
    """File reference onto the Rx. Post-submit manual attach is allowed
    (SRC24). The asset must be visible to the caller (own org, or via an
    existing live reference)."""
    await limit_writes(p)
    from app.modules.assets.models import Asset, FileReference
    from app.modules.assets.router import _asset_visible
    rx = await db.get(Rx, rx_id, with_for_update=True)
    if not rx or rx.tenant_id != p.tenant_id or not _is_party(p, rx):
        await _deny(db, request, p, "rx_not_visible")
    asset = await db.get(Asset, body.asset_id)
    if (not asset or asset.tenant_id != p.tenant_id
            or not await _asset_visible(db, p, asset)
            or asset.format_status != "format_ok"):
        raise HTTPException(status_code=422, detail={
            "code": "asset_not_attachable",
            "message": "Asset must exist, be format_ok, and be visible"})
    existing = (await db.execute(select(FileReference).where(
        FileReference.asset_id == asset.id,
        FileReference.subject_type == "rx",
        FileReference.subject_id == rx.id,
        FileReference.role == body.role,
        FileReference.revoked_at.is_(None)))).scalar_one_or_none()
    if existing:
        return {"id": str(existing.id), "asset_id": str(asset.id),
                "subject_type": "rx", "subject_id": str(rx.id),
                "role": existing.role, "revoked_at": None}
    ref = FileReference(
        tenant_id=p.tenant_id, asset_id=asset.id, subject_type="rx",
        subject_id=rx.id, role=body.role, granted_by_org_id=p.org.id,
        granted_by_user_id=p.user.id)
    db.add(ref)
    rx.version += 1  # content change -> optimistic-lock bump (bundle reuse)
    await db.flush()
    record(db, action="rx.attachment_added", object_type="rx",
           object_id=rx.id, tenant_id=p.tenant_id, org_id=p.org.id,
           actor_user_id=p.user.id, request=request,
           after={"asset_id": str(asset.id), "role": body.role})
    await tenant_commit(db, p)
    return {"id": str(ref.id), "asset_id": str(asset.id),
            "subject_type": "rx", "subject_id": str(rx.id),
            "role": ref.role, "revoked_at": None}


@router.get("/rx/{rx_id}/comments", response_model=dict,
            operation_id="listRxComments")
async def list_rx_comments(rx_id: uuid.UUID, request: Request, db: Db,
                           p: Me, _g=Depends(require_perm("rx:read"))):
    await _rx_for_read(db, p, rx_id, request)
    rows = (await db.execute(
        select(RxComment).where(RxComment.rx_id == rx_id)
        .order_by(RxComment.created_at))).scalars().all()
    return {"items": [CommentOut.model_validate(c) for c in rows]}


@router.post("/rx/{rx_id}/comments", status_code=201,
             operation_id="createRxComment")
async def create_rx_comment(rx_id: uuid.UUID, body: CommentCreate,
                            request: Request, db: Db, p: Me,
                            _g=Depends(require_perm("rx:read"))):
    await limit_writes(p)
    rx = await _rx_for_read(db, p, rx_id, request)
    if body.parent_id:
        parent = await db.get(RxComment, body.parent_id)
        if not parent or parent.rx_id != rx.id:
            raise HTTPException(status_code=422, detail={
                "code": "invalid_parent",
                "message": "parent_id is not a comment on this Rx"})
    if body.file_reference_id:
        from app.modules.assets.models import FileReference
        ref = await db.get(FileReference, body.file_reference_id)
        if (not ref or ref.tenant_id != p.tenant_id
                or ref.subject_type != "rx" or ref.subject_id != rx.id
                or ref.revoked_at is not None):
            raise HTTPException(status_code=422, detail={
                "code": "invalid_file_reference",
                "message": "file_reference_id is not a live attachment on this Rx"})
    c = RxComment(tenant_id=p.tenant_id, rx_id=rx.id,
                  author_membership_id=p.membership.id, body=body.body,
                  parent_id=body.parent_id,
                  file_reference_id=body.file_reference_id)
    db.add(c)
    await db.flush()
    record(db, action="rx.comment_created", object_type="rx", object_id=rx.id,
           tenant_id=p.tenant_id, org_id=p.org.id, actor_user_id=p.user.id,
           request=request)
    await tenant_commit(db, p)
    return CommentOut.model_validate(c)


@router.get("/rx/{rx_id}/transitions", response_model=dict,
            operation_id="listRxTransitions")
async def list_rx_transitions(rx_id: uuid.UUID, request: Request, db: Db,
                              p: Me, _g=Depends(require_perm("rx:read"))):
    """Auditable status trail — extension op, registered in the spec."""
    await _rx_for_read(db, p, rx_id, request)
    rows = (await db.execute(
        select(RxTransition).where(RxTransition.rx_id == rx_id)
        .order_by(RxTransition.seq))).scalars().all()
    return {"items": [RxTransitionOut.model_validate(t) for t in rows]}


@router.get("/patients/{patient_id}/rx-history", response_model=dict,
            operation_id="patientRxHistory")
async def patient_rx_history(patient_id: uuid.UUID, request: Request,
                             db: Db, p: Me,
                             _g=Depends(require_perm("patient:read")),
                             limit: int = 25, cursor: str | None = None):
    pat = await db.get(Patient, patient_id)
    if not pat or pat.tenant_id != p.tenant_id or pat.org_id != p.org.id \
            or pat.deleted_at is not None:
        await _deny(db, request, p, "patient_not_in_org")
    lim = min(max(limit, 1), 100)
    offset = int(base64.b64decode(cursor)) if cursor else 0
    rows = (await db.execute(
        select(Rx).where(Rx.patient_id == patient_id)
        .order_by(Rx.created_at.desc(), Rx.id).offset(offset)
        .limit(lim + 1))).scalars().all()
    nxt = (base64.b64encode(str(offset + lim).encode()).decode()
           if len(rows) > lim else None)
    return {"items": [RxOut.model_validate(r) for r in rows[:lim]],
            "next_cursor": nxt}


# ---------------- notifications / approvals (M2) -----------------------------
@router.get("/notifications", response_model=dict,
            operation_id="listNotifications")
async def list_notifications(db: Db, p: Me,
                             kind: str | None = None,
                             status: str | None = None):
    """Own-org inbox — message center (COM-007) with todo counts."""
    conds = [Notification.org_id == p.org.id,
             Notification.tenant_id == p.tenant_id]
    if kind:
        conds.append(Notification.kind == kind)
    if status:
        conds.append(Notification.status == status)
    rows = (await db.execute(
        select(Notification).where(*conds)
        .order_by(Notification.created_at.desc()))).scalars().all()
    unread = (await db.execute(select(func.count()).select_from(Notification)
        .where(Notification.org_id == p.org.id,
               Notification.status == "unread"))).scalar_one()
    pending_approvals = (await db.execute(
        select(func.count()).select_from(Notification).where(
            Notification.org_id == p.org.id,
            Notification.kind == "approval_required",
            Notification.status != "resolved"))).scalar_one()
    return {"items": [NotificationOut.model_validate(n) for n in rows],
            "counts": {"unread": unread,
                       "approval_pending": pending_approvals}}


@router.post("/notifications", response_model=NotificationOut, status_code=201,
             operation_id="createNotification")
async def create_notification(body: NotificationCreate, request: Request,
                              db: Db, p: Me,
                              _g=Depends(require_perm("rx:write"))):
    """Structured issue/clinical message to the OTHER Rx party's inbox:
    lab -> practice or practice -> lab (LAB-002, COM-002/004)."""
    await limit_writes(p)
    rx = await _rx_for_read(db, p, body.rx_id, request)
    if rx.practice_org_id == p.org.id:
        recipient = rx.lab_org_id
    elif rx.lab_org_id == p.org.id:
        recipient = rx.practice_org_id
    else:  # pragma: no cover — _rx_for_read already gates party visibility
        await _deny(db, request, p, "not_rx_party")
    if not recipient:
        raise HTTPException(status_code=422, detail={
            "code": "no_counterparty",
            "message": "Rx has no receiving lab yet"})
    n = Notification(
        tenant_id=p.tenant_id, org_id=recipient, rx_id=rx.id,
        created_by_org_id=p.org.id, created_by_user_id=p.user.id,
        kind=body.kind, subject=body.subject, body=body.body,
        rx_version_at_creation=(rx.version
                                if body.kind == "approval_required" else None))
    db.add(n)
    await db.flush()
    record(db, action="notification.created", object_type="rx", object_id=rx.id,
           tenant_id=p.tenant_id, org_id=p.org.id, actor_user_id=p.user.id,
           request=request,
           after={"kind": body.kind, "to_org": str(recipient)})
    await tenant_commit(db, p)
    return n


@router.post("/notifications/{notification_id}/read",
             response_model=NotificationOut, operation_id="markNotificationRead")
async def mark_notification_read(notification_id: uuid.UUID, request: Request,
                                 db: Db, p: Me):
    n = await db.get(Notification, notification_id, with_for_update=True)
    if not n or n.tenant_id != p.tenant_id or n.org_id != p.org.id:
        await _deny(db, request, p, "notification_not_visible")
    if n.status == "unread":
        # ack_required is consumed by an acknowledge-read; info stays 'read'
        n.status = "resolved" if n.kind == "ack_required" else "read"
        if n.status == "resolved":
            n.resolved_at = datetime.now(UTC)
            n.resolved_by_user_id = p.user.id
        await db.flush()
        await tenant_commit(db, p)
    return n


@router.post("/notifications/{notification_id}/decision",
             response_model=ApprovalOut, operation_id="decideNotification")
async def decide_notification(notification_id: uuid.UUID, body: DecisionRequest,
                              request: Request, db: Db, p: Me,
                              _g=Depends(require_perm("rx:write")),
                              idem: str | None = Header(
                                  default=None, alias="Idempotency-Key")):
    """Signed approve/reject bound to the Rx version at request time.
    Stale (rx mutated since request) -> 409 version_drift; the lab must
    re-request — old conclusions never carry over silently (E2E-09)."""
    await limit_writes(p)
    if not idem:
        raise HTTPException(status_code=428, detail={
            "code": "precondition_required",
            "message": "Idempotency-Key required"})
    n = await db.get(Notification, notification_id, with_for_update=True)
    if not n or n.tenant_id != p.tenant_id or n.org_id != p.org.id:
        await _deny(db, request, p, "notification_not_visible")
    if n.kind != "approval_required":
        raise HTTPException(status_code=422, detail={
            "code": "not_approval", "message": "Notification is not an approval request"})
    existing = (await db.execute(select(Approval).where(
        Approval.notification_id == n.id))).scalar_one_or_none()
    if existing:
        return existing  # immutable decision — replay-safe (double-click)
    if not body.signature_name.strip():
        raise HTTPException(status_code=422, detail={
            "code": "signature_required", "message": "signature_name required"})
    rx = await db.get(Rx, n.rx_id)
    if not rx or rx.version != n.rx_version_at_creation:
        raise HTTPException(status_code=409, detail={
            "code": "version_drift",
            "message": "Rx changed since the request; re-confirm required"})
    ap = Approval(tenant_id=p.tenant_id, notification_id=n.id, rx_id=rx.id,
                  rx_version=rx.version, decision=body.decision,
                  signature_name=body.signature_name.strip(),
                  comment=body.comment, decided_by_user_id=p.user.id,
                  decided_at=datetime.now(UTC))
    db.add(ap)
    n.status = "resolved"
    n.resolved_at = datetime.now(UTC)
    n.resolved_by_user_id = p.user.id
    # FLOW-016: approval lands in the auditable transition trail.
    db.add(RxTransition(tenant_id=p.tenant_id, rx_id=rx.id,
                        from_status=rx.status, to_status=rx.status,
                        via="approval", actor_user_id=p.user.id,
                        actor_org_id=p.org.id,
                        note=f"{body.decision}: {body.signature_name.strip()}"))
    await db.flush()
    record(db, action="approval.decided", object_type="rx", object_id=rx.id,
           tenant_id=p.tenant_id, org_id=p.org.id, actor_user_id=p.user.id,
           request=request,
           after={"decision": body.decision, "rx_version": rx.version})
    await tenant_commit(db, p)
    return ap
