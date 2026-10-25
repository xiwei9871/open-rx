"""Private-preview demo seed — controlled synthetic initialization.

Distinct from app.seed (dev/test only). This seed is allowed under ENV=prod
but only when ALL of the following hold:

  * settings.env == "prod"            (prod guards still apply — this module
                                       never weakens them)
  * PREVIEW_DEMO_SEED == "true"       (explicit operator opt-in)
  * PREVIEW_DEMO_TOKEN env matches the --token CLI arg (seed runs only when
                                       the operator supplies the deploy-time
                                       token, so a stray env flag alone is
                                       inert)

Everything it creates is synthetic demo data, namespaced to a demo tenant so
customer trials stay isolated from each other:

  Usage:  python -m app.preview_seed --token "$PREVIEW_DEMO_TOKEN" \
              [--slug acme] [--practice "Acme Ortho"] [--lab "Acme Lab"]

Accounts come from PREVIEW_DEMO_ACCOUNTS (JSON list), e.g.
  [{"email":"doc@acme.test","name":"Dr. A","role":"practice_admin",
    "org":"practice","password":"<from secret>"}]
Passwords are ONLY read from env/args — never hardcoded — and are printed
once to stdout for the operator to deliver out-of-band.
"""
import argparse
import asyncio
import json
import os
import secrets
import sys
from datetime import UTC, date, datetime

from sqlalchemy import select, text

from app.db import admin_session
from app.modules.iam.models import (
    Location, Membership, OrgConnection, Organization, RosterMember, Tenant,
    UserAccount,
)
from app.security import hash_password

DEMO_TENANT_PREFIX = "preview-demo"


def _guard() -> None:
    from app.config import get_settings
    s = get_settings()
    if s.env != "prod":
        raise SystemExit("preview_seed requires ENV=prod (with prod guards)")
    if os.environ.get("PREVIEW_DEMO_SEED") != "true":
        raise SystemExit("set PREVIEW_DEMO_SEED=true to enable demo seeding")


DEMO_PATIENTS = [
    # (first, last, dob, external_ref, case label)
    ("Emma", "Whitfield", date(2011, 3, 22), "DEMO-001",
     "Hawley Retainer Case"),
    ("Liam", "Tremblay", date(2010, 8, 9), "DEMO-002",
     "Expansion Appliance Case"),
    ("Sophia", "Nguyen", date(2012, 1, 30), "DEMO-003",
     "Clinical Approval Case"),
    ("Noah", "Campbell", date(2009, 11, 17), "DEMO-004",
     "Upper & Lower STL Case"),
    ("Olivia", "MacLeod", date(2011, 6, 4), "DEMO-005",
     "Complete Lab Delivery Case"),
]

CATALOG = [
    ("part", "LB", "Labial bow", "wire"),
    ("part", "AD", "Adams clasp", "retention"),
    ("part", "BC", "Ball clasp", "retention"),
    ("part", "EXP", "Expansion screw", "screw"),
    ("part", "RPE", "RPE screw", "screw"),
    ("part", "BND", "Molar band", "band"),
    ("appliance", "HWL", "Hawley retainer", "retainer"),
    ("appliance", "RPN", "Rapid palatal expander", "expander"),
    ("appliance", "SPL", "Essix splint", "splint"),
    ("appliance", "ALN", "Aligner set", "aligner"),
]


async def seed_demo(slug: str, practice_name: str, lab_name: str,
                    practice_tz: str, lab_tz: str) -> None:
    _guard()
    accounts = json.loads(os.environ.get("PREVIEW_DEMO_ACCOUNTS", "[]"))

    async with admin_session() as db:
        tname = f"{DEMO_TENANT_PREFIX}:{slug}"
        tenant = (await db.execute(
            select(Tenant).where(Tenant.name == tname))).scalar_one_or_none()
        if not tenant:
            tenant = Tenant(name=tname)
            db.add(tenant)
            await db.flush()

        orgs: dict[str, Organization] = {}
        for code, kind, name, tz in [
            ("practice", "practice", practice_name, practice_tz),
            ("lab", "lab", lab_name, lab_tz),
        ]:
            org = (await db.execute(
                select(Organization).where(Organization.name == name)
            )).scalar_one_or_none()
            if not org:
                org = Organization(tenant_id=tenant.id, kind=kind, name=name,
                                   timezone=tz)
                db.add(org)
                await db.flush()
            orgs[code] = org

        # One location each (Canadian address formats).
        for code, lname, addr in [
            ("practice", "Main Clinic",
             "1200 Burrard St, Vancouver, BC V6Z 2C7"),
            ("lab", "Main Lab", "88 Queen St E, Toronto, ON M5C 1S6"),
        ]:
            if not (await db.execute(select(Location).where(
                    Location.org_id == orgs[code].id,
                    Location.name == lname))).scalar_one_or_none():
                db.add(Location(tenant_id=tenant.id, org_id=orgs[code].id,
                                name=lname, address=addr))
        await db.flush()

        # Default location for the practice.
        loc = (await db.execute(select(Location).where(
            Location.org_id == orgs["practice"].id))).scalars().first()
        if loc and not orgs["practice"].default_location_id:
            orgs["practice"].default_location_id = loc.id

        # Demo users from env-provided account spec; missing passwords get a
        # generated one printed once for the operator.
        for spec in accounts:
            org = orgs[spec["org"]]
            user = (await db.execute(select(UserAccount).where(
                UserAccount.email == spec["email"]))).scalar_one_or_none()
            if not user:
                pw = spec.get("password") or secrets.token_urlsafe(12)
                user = UserAccount(
                    email=spec["email"], display_name=spec["name"],
                    password_hash=hash_password(pw))
                db.add(user)
                await db.flush()
                print(f"NEW ACCOUNT {spec['email']} role={spec['role']} "
                      f"org={spec['org']} password={pw}")
            if not (await db.execute(select(Membership).where(
                    Membership.org_id == org.id,
                    Membership.user_id == user.id))).scalar_one_or_none():
                db.add(Membership(tenant_id=tenant.id, org_id=org.id,
                                  user_id=user.id, role=spec["role"],
                                  status="active"))

        if not (await db.execute(select(OrgConnection).where(
                OrgConnection.practice_org_id == orgs["practice"].id,
                OrgConnection.lab_org_id == orgs["lab"].id))
        ).scalar_one_or_none():
            db.add(OrgConnection(
                tenant_id=tenant.id,
                practice_org_id=orgs["practice"].id,
                lab_org_id=orgs["lab"].id,
                initiated_by_org_id=orgs["practice"].id, status="accepted"))

        if not (await db.execute(select(RosterMember).where(
                RosterMember.org_id == orgs["practice"].id))).scalars().first():
            roster = RosterMember(tenant_id=tenant.id,
                                  org_id=orgs["practice"].id, kind="doctor",
                                  display_name="Dr. Rivera", is_default=True)
            db.add(roster)
            await db.flush()
            orgs["practice"].default_doctor_id = roster.id

        from app.modules.clinical.models import Patient, TreatmentCase
        from app.modules.rx.models import (
            CatalogItem, FulfillmentEvent, Rx, RxItem, RxTransition,
        )

        doctor = (await db.execute(select(UserAccount).join(Membership).where(
            Membership.org_id == orgs["practice"].id,
            Membership.role == "practice_admin"))).scalars().first()
        roster_doc = (await db.execute(select(RosterMember).where(
            RosterMember.org_id == orgs["practice"].id))).scalars().first()

        patient_ids = {}
        for first, last, dob, ref, case_label in DEMO_PATIENTS:
            pat = (await db.execute(select(Patient).where(
                Patient.org_id == orgs["practice"].id,
                Patient.external_ref == ref))).scalar_one_or_none()
            if not pat:
                num = (await db.execute(
                    text("SELECT nextval('patient_number_seq')"))).scalar()
                pat = Patient(
                    tenant_id=tenant.id, org_id=orgs["practice"].id,
                    patient_number=f"P{num:06d}", first_name=first,
                    last_name=last, dob=dob, external_ref=ref,
                    notes="synthetic demo patient")
                db.add(pat)
                await db.flush()
            patient_ids[ref] = pat.id
            if not (await db.execute(select(TreatmentCase).where(
                    TreatmentCase.patient_id == pat.id))
            ).scalar_one_or_none():
                db.add(TreatmentCase(
                    tenant_id=tenant.id, org_id=orgs["practice"].id,
                    patient_id=pat.id, label=f"{case_label} (synthetic)",
                    stage="active",
                    opened_by_user_id=doctor.id if doctor else None,
                    opened_at=datetime.now(UTC)))

        for kind, code, name, cat in CATALOG:
            if not (await db.execute(select(CatalogItem).where(
                    CatalogItem.tenant_id == tenant.id,
                    CatalogItem.code == code,
                    CatalogItem.owner_org_id.is_(None)
            ))).scalar_one_or_none():
                db.add(CatalogItem(
                    tenant_id=tenant.id, owner_org_id=None, kind=kind,
                    code=code, name=name, category=cat,
                    option_schema=({"required": ["band_tooth"]}
                                   if code == "BND" else None)))

        # Sample: a fully delivered Rx so "View a Sample Prescription" shows a
        # complete journey (items, signature, history, fulfillment trail).
        if doctor and not (await db.execute(select(Rx).where(
                Rx.practice_org_id == orgs["practice"].id,
                Rx.status == "delivered"))).scalar_one_or_none():
            hwl = (await db.execute(select(CatalogItem).where(
                CatalogItem.tenant_id == tenant.id,
                CatalogItem.code == "HWL"))).scalar_one()
            num = (await db.execute(
                text("SELECT nextval('rx_number_seq')"))).scalar()
            now = datetime.now(UTC)
            pat_id = patient_ids["DEMO-005"]
            case = (await db.execute(select(TreatmentCase).where(
                TreatmentCase.patient_id == pat_id))).scalar_one()
            rx = Rx(
                tenant_id=tenant.id, practice_org_id=orgs["practice"].id,
                rx_number=f"RX{num:06d}", patient_id=pat_id,
                case_id=case.id, lab_org_id=orgs["lab"].id,
                location_id=orgs["practice"].default_location_id,
                doctor_id=roster_doc.id if roster_doc else None,
                due_date=date.today(), status="delivered",
                fulfillment_status="delivered", checked_in_via="download",
                created_by_user_id=doctor.id, submitted_at=now,
                submitted_by_user_id=doctor.id, checked_in_at=now,
                checked_in_by_user_id=doctor.id, completed_at=now,
                completed_by_user_id=doctor.id, carrier="Canada Post",
                tracking_number="DEMO-TRACK-001", shipped_at=now,
                shipped_by_user_id=doctor.id, received_at=now,
                received_by_user_id=doctor.id, delivered_at=now,
                delivered_by_user_id=doctor.id, qc_status="pass",
                signature_name="Dr. Rivera (demo)", signed_rx_version=1,
                notes="Synthetic demo order — no real patient data.")
            db.add(rx)
            await db.flush()
            db.add(RxItem(tenant_id=tenant.id, rx_id=rx.id,
                          catalog_item_id=hwl.id, arch="upper",
                          tooth_ops=[{"tooth": "14", "op": "band"}]))
            for i, (frm, to) in enumerate([
                    (None, "draft"), ("draft", "submitted"),
                    ("submitted", "checked_in"), ("checked_in", "in_progress"),
                    ("in_progress", "completed")]):
                db.add(RxTransition(
                    tenant_id=tenant.id, rx_id=rx.id, from_status=frm,
                    to_status=to, via="button", actor_user_id=doctor.id,
                    actor_org_id=orgs["practice"].id if i < 3
                    else orgs["lab"].id))
            for ev in ["qc_passed", "shipped", "received", "delivered"]:
                db.add(FulfillmentEvent(
                    tenant_id=tenant.id, rx_id=rx.id, event=ev,
                    actor_user_id=doctor.id, actor_org_id=orgs["lab"].id))

        await db.commit()
        print(f"preview demo seed ok: tenant={tenant.id} "
              f"practice={orgs['practice'].id} lab={orgs['lab'].id}")


def main() -> None:
    _guard()
    p = argparse.ArgumentParser()
    p.add_argument("--token", required=True,
                   help="must equal PREVIEW_DEMO_TOKEN")
    p.add_argument("--slug", default="demo")
    p.add_argument("--practice", default="Harbourview Orthodontics (demo)")
    p.add_argument("--lab", default="Coastal Ortho Lab (demo)")
    p.add_argument("--practice-tz", default="America/Vancouver")
    p.add_argument("--lab-tz", default="America/Toronto")
    a = p.parse_args()
    if a.token != os.environ.get("PREVIEW_DEMO_TOKEN", ""):
        raise SystemExit("invalid demo-seed token")
    asyncio.run(seed_demo(a.slug, a.practice, a.lab,
                          a.practice_tz, a.lab_tz))


if __name__ == "__main__":
    main()
