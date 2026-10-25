"""SAFE-009: org-scoped administrator data export (JSON skeleton).

Exports the caller's own org only — never cross-tenant, never credentials,
password hashes, sessions, or TOTP secrets. Asset entries are a manifest
(id/sha256/bytes/key) — bytes are fetched through the normal signed-URL
flow, so export carries pointers, not copies.
"""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.audit import record
from app.deps import Db, Me, require_perm
from app.modules.assets.models import Asset
from app.modules.clinical.models import Patient
from app.modules.iam.models import (Location, Membership, Organization,
                                    RosterMember, UserAccount)
from app.modules.rx.models import Rx

router = APIRouter(tags=["admin"])


@router.get("/admin/export", response_model=dict, operation_id="adminExport")
async def admin_export(request: Request, db: Db, p: Me,
                       _g=Depends(require_perm("org:manage"))):
    org = await db.get(Organization, p.org.id)
    members = (await db.execute(
        select(Membership, UserAccount)
        .join(UserAccount, UserAccount.id == Membership.user_id)
        .where(Membership.org_id == p.org.id))).all()
    locations = (await db.execute(select(Location).where(
        Location.org_id == p.org.id))).scalars().all()
    roster = (await db.execute(select(RosterMember).where(
        RosterMember.org_id == p.org.id))).scalars().all()
    patients = (await db.execute(select(Patient).where(
        Patient.org_id == p.org.id,
        Patient.deleted_at.is_(None)))).scalars().all()
    rxs = (await db.execute(select(Rx).where(
        (Rx.practice_org_id == p.org.id) | (Rx.lab_org_id == p.org.id))
    )).scalars().all()
    assets = (await db.execute(select(Asset).where(
        Asset.org_id == p.org.id))).scalars().all()

    record(db, action="admin.export", object_type="organization",
           object_id=p.org.id, tenant_id=p.tenant_id, org_id=p.org.id,
           actor_user_id=p.user.id, request=request,
           after={"patients": len(patients), "rx": len(rxs)})

    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "organization": {
            "id": str(org.id), "name": org.name, "kind": org.kind,
            "timezone": org.timezone},
        "members": [{
            "membership_id": str(m.id), "role": m.role, "status": m.status,
            "user": {"id": str(u.id), "email": u.email,
                     "display_name": u.display_name},
        } for m, u in members],
        "locations": [{"id": str(l.id), "name": l.name}
                      for l in locations],
        "roster": [{"id": str(r.id), "display_name": r.display_name,
                    "credentials": r.credentials, "status": r.status}
                   for r in roster],
        "patients": [{
            "id": str(pt.id), "patient_number": pt.patient_number,
            "external_ref": pt.external_ref,
            "first_name": pt.first_name, "last_name": pt.last_name,
            "dob": pt.dob.isoformat() if pt.dob else None,
        } for pt in patients],
        "prescriptions": [{
            "id": str(r.id), "rx_number": r.rx_number, "status": r.status,
            "fulfillment_status": r.fulfillment_status,
            "patient_id": str(r.patient_id),
            "lab_org_id": str(r.lab_org_id) if r.lab_org_id else None,
            "due_date": r.due_date.isoformat() if r.due_date else None,
            "submitted_at": (r.submitted_at.isoformat()
                             if r.submitted_at else None),
        } for r in rxs],
        "asset_manifest": [{
            "id": str(a.id), "sha256": a.sha256, "kind": a.kind,
            "jaw": a.jaw, "bytes": a.bytes,
            "format_status": a.format_status, "storage_key": a.storage_key,
        } for a in assets],
    }
