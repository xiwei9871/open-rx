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
import base64
import hashlib
import io
import json
import uuid
import zipfile
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record
from app.deps import (Db, Me, Principal, _deny, limit_writes, require_perm,
                      tenant_commit)
from app.modules.clinical.models import Patient, TreatmentCase
from app.modules.iam.models import (Location, OrgConnection, Organization,
                                    RosterMember)
from app.modules.rx.models import (CatalogItem, Rx, RxComment, RxItem,
                                   RxTransition)
from app.modules.rx.schemas import (AttachmentCreate, CatalogItemOut,
                                    CommentCreate, CommentOut, RxCheckIn,
                                    RxCreate, RxItemOut, RxItemsReplace,
                                    RxOut, RxSubmit, RxTransitionOut,
                                    RxUnsubmit, RxUpdate)

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
    if rx.status != "draft":
        raise _illegal("Only draft (Saved) prescriptions can be edited")
    if if_match is not None and if_match != rx.version:
        raise _vconflict()
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
    if rx.status != "draft":
        raise _illegal("Items can only be changed while status=draft")
    if if_match is not None and if_match != rx.version:
        raise _vconflict()
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
                    body: RxSubmit | None = None,
                    _g=Depends(require_perm("rx:write")),
                    idempotency_key: str | None = Header(default=None),
                    if_match: int | None = Header(default=None)):
    await limit_writes(p)
    if idempotency_key is None:
        raise HTTPException(status_code=422, detail={
            "code": "validation_failed",
            "message": "Idempotency-Key header required"})
    rx = await _rx_for_practice_write(db, p, rx_id, request)
    body = body or RxSubmit()
    # Hash the request payload only — replay must match even after the
    # version bump from the first successful submit.
    ph = _payload_hash(rx_id, body.model_dump())
    if rx.submit_idem_key == idempotency_key:
        if rx.submit_idem_hash == ph:
            return await _rx_out(db, rx)  # replay -> first result
        raise HTTPException(status_code=409, detail={
            "code": "idempotency_payload_mismatch",
            "message": "Idempotency-Key reuse with different payload"})
    if rx.status != "draft":
        raise _illegal("Only draft (Saved) prescriptions can be submitted")
    if if_match is not None and if_match != rx.version:
        raise _vconflict()
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
    rx.status = "submitted"
    rx.submitted_at = datetime.now(UTC)
    rx.submitted_by_user_id = p.user.id
    rx.signature_name = body.signature_name
    rx.submit_idem_key = idempotency_key
    rx.submit_idem_hash = ph
    rx.version += 1
    _record_transition(db, p, rx, "draft", "submitted", via="button",
                       note=body.note)
    record(db, action="rx.submitted", object_type="rx", object_id=rx.id,
           tenant_id=p.tenant_id, org_id=p.org.id, actor_user_id=p.user.id,
           request=request, after={"lab_org_id": str(rx.lab_org_id)})
    await tenant_commit(db, p)
    return await _rx_out(db, rx)


@router.post("/rx/{rx_id}/unsubmit", operation_id="unsubmitRx")
async def unsubmit_rx(rx_id: uuid.UUID, request: Request, db: Db, p: Me,
                      body: RxUnsubmit | None = None,
                      _g=Depends(require_perm("rx:write")),
                      if_match: int | None = Header(default=None)):
    await limit_writes(p)
    rx = await _rx_for_practice_write(db, p, rx_id, request)
    # CONFIRMED rule (SRC03): a checked-in Rx cannot be pulled back.
    if rx.status == "checked_in" or rx.checked_in_at is not None:
        raise HTTPException(status_code=409, detail={
            "code": "already_checked_in",
            "message": "Lab has checked in this prescription; "
                       "it can no longer be unsubmitted"})
    if rx.status != "submitted":
        raise _illegal("Only submitted prescriptions can be unsubmitted")
    if if_match is not None and if_match != rx.version:
        raise _vconflict()
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
                      idempotency_key: str | None = Header(default=None)):
    await limit_writes(p)
    rx = await _rx_for_lab_write(db, p, rx_id, request)
    if rx.status == "checked_in":
        return await _rx_out(db, rx)  # idempotent repeat
    if rx.status != "submitted":
        raise _illegal("Only submitted prescriptions can be checked in")
    _apply_checkin(db, p, rx, via="button", note=(body or RxCheckIn()).note)
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


@router.get("/rx/{rx_id}/bundle", operation_id="downloadRxBundle")
async def download_rx_bundle(rx_id: uuid.UUID, request: Request, db: Db,
                             p: Me, _g=Depends(require_perm("rx:read"))):
    """Rx ZIP bundle. CONFIRMED (SRC03): a lab-side download of the Rx
    bundle IS a check-in — status moves submitted -> checked_in with
    checked_in_via='download'. Practice-side downloads do not transition."""
    rx = await db.get(Rx, rx_id, with_for_update=True)
    if not rx or rx.tenant_id != p.tenant_id or not _is_party(p, rx):
        await _deny(db, request, p, "rx_not_visible")
    if rx.status == "submitted" and rx.lab_org_id == p.org.id:
        _apply_checkin(db, p, rx, via="download",
                       note="bundle download auto check-in")
        record(db, action="rx.checked_in", object_type="rx", object_id=rx.id,
               tenant_id=p.tenant_id, org_id=p.org.id,
               actor_user_id=p.user.id, request=request,
               after={"via": "download"})
        await tenant_commit(db, p)
    payload = await _rx_out(db, rx)
    from app.modules.assets.models import Asset, FileReference
    refs = (await db.execute(
        select(FileReference, Asset)
        .join(Asset, Asset.id == FileReference.asset_id)
        .where(FileReference.subject_type == "rx",
               FileReference.subject_id == rx.id,
               FileReference.revoked_at.is_(None)))).all()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("rx.json", json.dumps(payload, indent=2))
        z.writestr("attachments.json", json.dumps([
            {"asset_id": str(a.id), "kind": a.kind, "jaw": a.jaw,
             "sha256": a.sha256, "bytes": a.bytes, "role": r.role}
            for r, a in refs], indent=2))
    return Response(
        content=buf.getvalue(), media_type="application/zip",
        headers={"Content-Disposition":
                 f'attachment; filename="{rx.rx_number}.zip"'})


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
    c = RxComment(tenant_id=p.tenant_id, rx_id=rx.id,
                  author_membership_id=p.membership.id, body=body.body,
                  parent_id=body.parent_id)
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
        .order_by(RxTransition.created_at))).scalars().all()
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
