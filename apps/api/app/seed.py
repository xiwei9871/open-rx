"""Dev/test seed — SYNTHETIC data only (SAFE-008). Idempotent.

Usage: python -m app.seed
Creates: tenant T1 with orgs PA(practice)/LA(lab)/LB(lab, unconnected),
users admin@pa.dev / doctor@pa.dev / staff@pa.dev / admin@la.dev / tech@la.dev
(password: Passw0rd!dev), PA<->LA accepted connection, Dr. Demo roster member.
"""
import asyncio
from datetime import UTC, date, datetime

from sqlalchemy import select, text

from app.db import admin_session
from app.modules.iam.models import (
    Membership, OrgConnection, Organization, RosterMember, Tenant, UserAccount,
)
from app.security import enc_totp, hash_password

PASSWORD = "Passw0rd!dev"
USERS = [
    ("admin@pa.dev", "PA Admin", "practice_admin", "PA"),
    ("doctor@pa.dev", "Dr. Demo", "practice_doctor", "PA"),
    ("staff@pa.dev", "PA Staff", "practice_staff", "PA"),
    ("admin@la.dev", "LA Admin", "lab_admin", "LA"),
    ("tech@la.dev", "LA Tech", "lab_technician", "LA"),
    # UAT: a principal on the UNCONNECTED lab org (LB) — used to prove
    # cross-org denial; LB has no OrgConnection to PA.
    ("lab2@lb.dev", "LB Tech", "lab_technician", "LB"),
    # UAT: pre-enrolled TOTP user so 2FA browser tests are idempotent —
    # no test needs to mutate another account's 2FA state. Secret is a
    # well-known RFC test vector, synthetic only.
    ("mfa@pa.dev", "MFA Doc", "practice_doctor", "PA"),
]
TOTP_SEED_SECRET = "JBSWY3DPEHPK3PXP"


async def seed() -> None:
    from app.config import get_settings
    if get_settings().env not in ("dev", "test"):
        raise SystemExit("refusing to seed synthetic data outside dev/test")
    async with admin_session() as db:
        tenant = (await db.execute(select(Tenant))).scalars().first()
        if not tenant:
            tenant = Tenant(name="Dev Tenant (synthetic)")
            db.add(tenant)
            await db.flush()

        orgs = {}
        for code, kind, name in [
            ("PA", "practice", "Smile Ortho (synthetic)"),
            ("LA", "lab", "Friendly Lab (synthetic)"),
            ("LB", "lab", "Unconnected Lab (synthetic)"),
        ]:
            org = (await db.execute(
                select(Organization).where(Organization.name == name)
            )).scalar_one_or_none()
            if not org:
                org = Organization(tenant_id=tenant.id, kind=kind, name=name)
                db.add(org)
                await db.flush()
            orgs[code] = org

        for email, display, role, code in USERS:
            user = (await db.execute(
                select(UserAccount).where(UserAccount.email == email)
            )).scalar_one_or_none()
            if not user:
                user = UserAccount(email=email, display_name=display,
                                   password_hash=hash_password(PASSWORD))
                db.add(user)
                await db.flush()
            if not (await db.execute(select(Membership).where(
                    Membership.org_id == orgs[code].id,
                    Membership.user_id == user.id))).scalar_one_or_none():
                db.add(Membership(tenant_id=tenant.id, org_id=orgs[code].id,
                                  user_id=user.id, role=role, status="active"))
            if email == "mfa@pa.dev" and not user.totp_enabled:
                user.totp_secret_enc = enc_totp(TOTP_SEED_SECRET)
                user.totp_enabled = True

        if not (await db.execute(select(OrgConnection).where(
                OrgConnection.practice_org_id == orgs["PA"].id,
                OrgConnection.lab_org_id == orgs["LA"].id))).scalar_one_or_none():
            db.add(OrgConnection(tenant_id=tenant.id,
                                 practice_org_id=orgs["PA"].id,
                                 lab_org_id=orgs["LA"].id,
                                 initiated_by_org_id=orgs["PA"].id,
                                 status="accepted"))

        if not (await db.execute(select(RosterMember).where(
                RosterMember.org_id == orgs["PA"].id))).scalars().first():
            db.add(RosterMember(tenant_id=tenant.id, org_id=orgs["PA"].id,
                                kind="doctor", display_name="Dr. Demo",
                                is_default=True))

        # S1a: synthetic patient + case (dev/test only)
        from app.modules.clinical.models import Patient, TreatmentCase
        pat = (await db.execute(select(Patient).where(
            Patient.external_ref == "SYN-0001"))).scalar_one_or_none()
        if not pat:
            num = (await db.execute(
                text("SELECT nextval('patient_number_seq')"))).scalar()
            pat = Patient(
                tenant_id=tenant.id, org_id=orgs["PA"].id,
                patient_number=f"P{num:06d}",
                first_name="Ava", last_name="Synthetic",
                dob=date(2010, 5, 14), external_ref="SYN-0001",
                notes="fully synthetic patient")
            db.add(pat)
            await db.flush()
            doctor = (await db.execute(select(UserAccount).where(
                UserAccount.email == "doctor@pa.dev"))).scalar_one()
            db.add(TreatmentCase(
                tenant_id=tenant.id, org_id=orgs["PA"].id, patient_id=pat.id,
                label="Initial alignment (synthetic)", stage="active",
                opened_by_user_id=doctor.id,
                opened_at=datetime.now(UTC)))

        # S1b: universal catalog (synthetic, EasyRS-owned names — no EasyRx
        # proprietary library content).
        from app.modules.rx.models import CatalogItem
        CATALOG = [
            ("part", "LB", "Labial bow", "wire"),
            ("part", "AD", "Adams clasp", "retention"),
            ("part", "BC", "Ball clasp", "retention"),
            ("part", "EXP", "Expansion screw", "screw"),
            ("part", "RPE", "RPE screw", "screw"),
            # BND demonstrates the confirmed "required part options" rule
            # (V1.1 / 2023 release note: Prompt for Bands before submit).
            ("part", "BND", "Molar band", "band"),
            ("appliance", "HWL", "Hawley retainer", "retainer"),
            ("appliance", "RPN", "Rapid palatal expander", "expander"),
            ("appliance", "SPL", "Essix splint", "splint"),
            ("appliance", "ALN", "Aligner set", "aligner"),
        ]
        for kind, code, name, cat in CATALOG:
            if not (await db.execute(select(CatalogItem).where(
                    CatalogItem.tenant_id == tenant.id,
                    CatalogItem.code == code,
                    CatalogItem.owner_org_id.is_(None)))).scalar_one_or_none():
                db.add(CatalogItem(
                    tenant_id=tenant.id, owner_org_id=None, kind=kind,
                    code=code, name=name, category=cat,
                    option_schema=({"required": ["band_tooth"]}
                                   if code == "BND" else None)))

        await db.commit()
        print(f"seed ok: tenant={tenant.id} PA={orgs['PA'].id} "
              f"LA={orgs['LA'].id} LB={orgs['LB'].id}")


async def purge() -> None:
    """SAFE-007: remove the synthetic dataset — dev/test only.

    Deletes the seeded orgs (PA/LA/LB), their memberships/roster/locations/
    connections, patients, tenant-wide catalog rows, and the demo users.
    Rx/asset rows disappear via org-scoped deletes below; S3 objects under
    the org prefixes are removed best-effort afterwards by the caller (see
    scripts/cleanup_synthetic.sh) — the DB purge itself stays transactional.
    """
    from app.config import get_settings
    if get_settings().env not in ("dev", "test"):
        raise SystemExit("refusing to purge outside dev/test")
    from sqlalchemy import delete, or_
    from app.modules.assets.models import Asset, FileReference, UploadSession
    from app.modules.clinical.models import Patient, TreatmentCase
    from app.modules.iam.models import Location
    from app.modules.rx.models import (Approval, FulfillmentEvent,
                                       IdempotencyRecord, Notification,
                                       QcRecord, Rx, RxBundle, RxComment,
                                       RxItem, RxTemplate, RxTransition)

    async with admin_session() as db:
        org_ids = [r[0] for r in (await db.execute(
            select(Organization.id).where(
                Organization.name.in_(
                    ["Smile Ortho (synthetic)", "Friendly Lab (synthetic)", "Unconnected Lab (synthetic)"])))
        ).all()]
        if not org_ids:
            print("purge: no synthetic orgs found — nothing to do")
            return
        rx_ids = [r[0] for r in (await db.execute(select(Rx.id).where(
            (Rx.practice_org_id.in_(org_ids))
            | (Rx.lab_org_id.in_(org_ids))))).all()]
        patient_ids = [r[0] for r in (await db.execute(
            select(Patient.id).where(Patient.org_id.in_(org_ids)))).all()]
        case_ids = [r[0] for r in (await db.execute(
            select(TreatmentCase.id).where(
                TreatmentCase.org_id.in_(org_ids)))).all()]
        asset_ids = [r[0] for r in (await db.execute(
            select(Asset.id).where(Asset.org_id.in_(org_ids)))).all()]
        for model, col in ((Approval, Approval.rx_id),
                           (Notification, Notification.rx_id),
                           (QcRecord, QcRecord.rx_id),
                           (FulfillmentEvent, FulfillmentEvent.rx_id),
                           (RxComment, RxComment.rx_id),
                           (RxTransition, RxTransition.rx_id),
                           (RxItem, RxItem.rx_id),
                           (RxBundle, RxBundle.rx_id)):
            if rx_ids:
                await db.execute(delete(model).where(col.in_(rx_ids)))
        # file references point at rx/patient/case subjects AND assets
        subject_ids = rx_ids + patient_ids + case_ids
        ref_conds = [FileReference.granted_by_org_id.in_(org_ids)]
        if subject_ids:
            ref_conds.append(FileReference.subject_id.in_(subject_ids))
        if asset_ids:
            ref_conds.append(FileReference.asset_id.in_(asset_ids))
        await db.execute(delete(FileReference).where(or_(*ref_conds)))
        if rx_ids:
            await db.execute(delete(Rx).where(Rx.id.in_(rx_ids)))
        for model, col in ((RxTemplate, RxTemplate.org_id),
                           (UploadSession, UploadSession.org_id),
                           (Asset, Asset.org_id),
                           (TreatmentCase, TreatmentCase.org_id),
                           (Patient, Patient.org_id),
                           (OrgConnection, OrgConnection.practice_org_id),
                           (RosterMember, RosterMember.org_id),
                           (Location, Location.org_id),
                           (Membership, Membership.org_id)):
            await db.execute(delete(model).where(col.in_(org_ids)))
        await db.execute(delete(OrgConnection).where(
            OrgConnection.lab_org_id.in_(org_ids)))
        await db.execute(delete(Organization).where(
            Organization.id.in_(org_ids)))
        from app.modules.auth.models import AuthChallenge, AuthSession
        user_ids = [r[0] for r in (await db.execute(
            select(UserAccount.id).where(
                UserAccount.email.like("%.dev")))).all()]
        if user_ids:
            await db.execute(delete(IdempotencyRecord).where(
                IdempotencyRecord.user_id.in_(user_ids)))
            await db.execute(delete(AuthSession).where(
                AuthSession.user_id.in_(user_ids)))
            await db.execute(delete(AuthChallenge).where(
                AuthChallenge.user_id.in_(user_ids)))
            await db.execute(delete(UserAccount).where(
                UserAccount.id.in_(user_ids)))
        # drop now-empty tenants
        await db.execute(delete(Tenant).where(Tenant.id.notin_(
            select(Organization.tenant_id))))
        await db.commit()
        print(f"purge ok: removed {len(org_ids)} synthetic orgs, "
              f"{len(rx_ids)} rx, demo users")


if __name__ == "__main__":
    import sys
    asyncio.run(purge() if "--purge" in sys.argv else seed())
