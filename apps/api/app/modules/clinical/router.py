"""S1a-01/02: patient + treatment-case endpoints (docs/api/openapi.yaml).

Authorization model (owning-org boundary):
- patients/cases live in exactly one org; only members of that org may see or
  mutate them. Cross-org ids get the same 403 shape as nonexistent ids.
- there is NO lab-side projection in S1a: lab roles hold no patient:* perms,
  and even a lab principal with perms would still fail the org-ownership
  check. Minimal-share to a lab requires the Rx channel (S1b+).
"""
import base64
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record
from app.deps import (Db, Me, Principal, limit_writes, require_perm,
                      tenant_commit, _deny)
from app.modules.clinical.models import Patient, TreatmentCase
from app.modules.rx.models import Rx
from app.modules.clinical.schemas import (CaseCreate, CaseOut, PatientCreate,
                                          PatientOut, PatientUpdate)

router = APIRouter(tags=["patients"])


async def _patient(db: AsyncSession, p: Principal,
                   patient_id: uuid.UUID, request: Request) -> Patient:
    """Fetch + org-ownership gate. Other orgs' patients are invisible (403)."""
    row = await db.get(Patient, patient_id)
    if not row or row.tenant_id != p.tenant_id or row.org_id != p.org.id \
            or row.deleted_at is not None:
        await _deny(db, request, p, "patient_not_in_org")
    return row


def _dup_where(p: Principal, body: PatientCreate):
    """Suspected-duplicate predicate: same org + (same last name & dob)
    or same external_ref. Deterministic and explainable."""
    conds = []
    if body.dob is not None:
        conds.append((func.lower(Patient.last_name) == body.last_name.lower())
                     & (Patient.dob == body.dob))
    if body.external_ref:
        conds.append(Patient.external_ref == body.external_ref)
    if not conds:
        return None
    return (Patient.org_id == p.org.id, Patient.deleted_at.is_(None), or_(*conds))


# ---------------- patients ---------------------------------------------------
@router.get("/patients", response_model=dict, operation_id="searchPatients")
async def search_patients(db: Db, p: Me,
                          _g=Depends(require_perm("patient:read")),
                          q: str | None = None,
                          external_ref: str | None = None,
                          dob: str | None = None,
                          limit: int = 25, cursor: str | None = None):
    lim = min(max(limit, 1), 100)
    qy = (select(Patient)
          .where(Patient.org_id == p.org.id, Patient.deleted_at.is_(None))
          .order_by(Patient.created_at, Patient.id))
    if q:
        like = f"%{q.lower()}%"
        qy = qy.where(or_(
            func.lower(Patient.first_name).like(like),
            func.lower(Patient.last_name).like(like),
            func.lower(Patient.external_ref).like(like)))
    if external_ref:
        qy = qy.where(Patient.external_ref == external_ref)
    if dob:
        qy = qy.where(Patient.dob == dob)
    offset = int(base64.b64decode(cursor)) if cursor else 0
    rows = (await db.execute(qy.offset(offset).limit(lim + 1))).scalars().all()
    nxt = (base64.b64encode(str(offset + lim).encode()).decode()
           if len(rows) > lim else None)
    return {"items": [PatientOut.model_validate(r) for r in rows[:lim]],
            "next_cursor": nxt}


@router.post("/patients", response_model=PatientOut, status_code=201,
             operation_id="createPatient")
async def create_patient(body: PatientCreate, request: Request, db: Db,
                         p: Me, _g=Depends(require_perm("patient:write"))):
    await limit_writes(p)
    pred = _dup_where(p, body)
    if pred is not None and not body.confirm_duplicate:
        cands = (await db.execute(
            select(Patient).where(*pred).limit(5))).scalars().all()
        if cands:
            raise HTTPException(status_code=409, detail={
                "code": "possible_duplicate",
                "message": "Possible existing patient — confirm or merge",
                "candidates": [{"patient_id": str(c.id),
                                "last_name": c.last_name,
                                "dob": str(c.dob) if c.dob else None}
                               for c in cands]})
    num = (await db.execute(text("SELECT nextval('patient_number_seq')"))).scalar()
    pat = Patient(
        tenant_id=p.tenant_id, org_id=p.org.id,
        patient_number=f"P{num:06d}",
        first_name=body.first_name, last_name=body.last_name,
        dob=body.dob, external_ref=body.external_ref, notes=body.notes)
    db.add(pat)
    await db.flush()
    record(db, action="patient.created", object_type="patient",
           object_id=pat.id, tenant_id=p.tenant_id, org_id=p.org.id,
           actor_user_id=p.user.id, request=request,
           after={"patient_number": pat.patient_number})
    await tenant_commit(db, p)
    return pat


@router.get("/patients/{patient_id}", response_model=PatientOut,
            operation_id="getPatient")
async def get_patient(patient_id: uuid.UUID, request: Request, db: Db, p: Me,
                      _g=Depends(require_perm("patient:read"))):
    return await _patient(db, p, patient_id, request)


@router.patch("/patients/{patient_id}", response_model=PatientOut,
              operation_id="updatePatient")
async def update_patient(patient_id: uuid.UUID, body: PatientUpdate,
                         request: Request, db: Db, p: Me,
                         _g=Depends(require_perm("patient:write")),
                         if_match: int | None = Header(default=None)):
    await limit_writes(p)
    pat = await db.get(Patient, patient_id, with_for_update=True)
    if not pat or pat.tenant_id != p.tenant_id or pat.org_id != p.org.id \
            or pat.deleted_at is not None:
        await _deny(db, request, p, "patient_not_in_org")
    if if_match is not None and if_match != pat.version:
        raise HTTPException(status_code=409, detail={
            "code": "version_conflict", "message": "Patient changed; reload"})
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(pat, k, v)
    pat.version += 1
    record(db, action="patient.updated", object_type="patient",
           object_id=pat.id, tenant_id=p.tenant_id, org_id=p.org.id,
           actor_user_id=p.user.id, request=request,
           after={k: str(v) for k, v in data.items()})
    await tenant_commit(db, p)
    return pat


@router.delete("/patients/{patient_id}", status_code=204,
               operation_id="deletePatient")
async def delete_patient(patient_id: uuid.UUID, request: Request, db: Db,
                         p: Me, _g=Depends(require_perm("patient:delete"))):
    await limit_writes(p)
    pat = await db.get(Patient, patient_id, with_for_update=True)
    if not pat or pat.tenant_id != p.tenant_id or pat.org_id != p.org.id \
            or pat.deleted_at is not None:
        await _deny(db, request, p, "patient_not_in_org")
    # PAT-009: in-flight Rx guard. A patient may only be soft-deleted when
    # every Rx is terminal: clinically finished AND logistically settled.
    #   in-flight = clinical status not in {completed, cancelled}
    #             OR completed but fulfillment still moving
    #                (qc_pending/qc_passed/shipped/received).
    # released  = cancelled, or completed with fulfillment in {none,delivered}
    # The delete is a soft tombstone only — rx rows, signatures, attachments
    # and approval history are never touched.
    inflight = (await db.execute(select(Rx.id, Rx.rx_number, Rx.status)
        .where(Rx.patient_id == patient_id,
               or_(Rx.status.notin_(("completed", "cancelled")),
                   Rx.fulfillment_status.notin_(("none", "delivered"))))
        .order_by(Rx.rx_number))).all()
    if inflight:
        record(db, action="patient.delete_blocked", object_type="patient",
               object_id=pat.id, tenant_id=p.tenant_id, org_id=p.org.id,
               actor_user_id=p.user.id, request=request,
               after={"inflight_rx": [str(r.rx_number) for r in inflight]})
        await tenant_commit(db, p)
        raise HTTPException(status_code=409, detail={
            "code": "patient_has_inflight_rx",
            "message": f"Patient has {len(inflight)} in-flight "
                       f"prescription(s); complete and deliver or cancel "
                       f"them before deleting",
            "inflight_rx": [{"id": str(r.id), "rx_number": r.rx_number,
                             "status": r.status} for r in inflight]})
    pat.deleted_at = datetime.now(UTC)
    record(db, action="patient.deleted", object_type="patient",
           object_id=pat.id, tenant_id=p.tenant_id, org_id=p.org.id,
           actor_user_id=p.user.id, request=request)
    await tenant_commit(db, p)


# ---------------- treatment cases --------------------------------------------
@router.get("/patients/{patient_id}/cases", response_model=dict,
            operation_id="listCases")
async def list_cases(patient_id: uuid.UUID, request: Request, db: Db, p: Me,
                     _g=Depends(require_perm("patient:read"))):
    await _patient(db, p, patient_id, request)
    rows = (await db.execute(
        select(TreatmentCase).where(TreatmentCase.patient_id == patient_id)
        .order_by(TreatmentCase.opened_at.desc()))).scalars().all()
    return {"items": [CaseOut.model_validate(c) for c in rows]}


@router.post("/patients/{patient_id}/cases", response_model=CaseOut,
             status_code=201, operation_id="createCase")
async def create_case(patient_id: uuid.UUID, body: CaseCreate,
                      request: Request, db: Db, p: Me,
                      _g=Depends(require_perm("patient:write"))):
    await limit_writes(p)
    await _patient(db, p, patient_id, request)
    c = TreatmentCase(
        tenant_id=p.tenant_id, org_id=p.org.id, patient_id=patient_id,
        label=body.label, stage="active",
        opened_by_user_id=p.user.id, opened_at=datetime.now(UTC))
    db.add(c)
    await db.flush()
    record(db, action="case.created", object_type="treatment_case",
           object_id=c.id, tenant_id=p.tenant_id, org_id=p.org.id,
           actor_user_id=p.user.id, request=request)
    await tenant_commit(db, p)
    return c


# ---------------- patient assets (S1a extension op) ---------------------------
@router.get("/patients/{patient_id}/assets", response_model=dict,
            operation_id="listPatientAssets")
async def list_patient_assets(patient_id: uuid.UUID, request: Request,
                              db: Db, p: Me,
                              _g=Depends(require_perm("patient:read"))):
    """Live file_references whose subject is this patient or one of its cases —
    joined to asset metadata. Extension op beyond the MVP contract surface."""
    from app.modules.assets.models import Asset, FileReference
    from app.modules.assets.router import _asset_join_out
    pat = await _patient(db, p, patient_id, request)
    case_ids = select(TreatmentCase.id).where(
        TreatmentCase.patient_id == pat.id).scalar_subquery()
    rows = (await db.execute(
        select(FileReference, Asset)
        .join(Asset, Asset.id == FileReference.asset_id)
        .where(FileReference.revoked_at.is_(None),
               ((FileReference.subject_type == "patient")
                & (FileReference.subject_id == patient_id))
               | ((FileReference.subject_type == "case")
                  & (FileReference.subject_id.in_(case_ids))))
        .order_by(FileReference.created_at.desc()))).all()
    return {"items": [_asset_join_out(ref, asset) for ref, asset in rows]}
