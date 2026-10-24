"""Dev/test seed — SYNTHETIC data only (SAFE-008). Idempotent.

Usage: python -m app.seed
Creates: tenant T1 with orgs PA(practice)/LA(lab)/LB(lab, unconnected),
users admin@pa.dev / doctor@pa.dev / staff@pa.dev / admin@la.dev / tech@la.dev
(password: Passw0rd!dev), PA<->LA accepted connection, Dr. Demo roster member.
"""
import asyncio

from sqlalchemy import select

from app.db import AdminSessionLocal
from app.modules.iam.models import (
    Membership, OrgConnection, Organization, RosterMember, Tenant, UserAccount,
)
from app.security import hash_password

PASSWORD = "Passw0rd!dev"
USERS = [
    ("admin@pa.dev", "PA Admin", "practice_admin", "PA"),
    ("doctor@pa.dev", "Dr. Demo", "practice_doctor", "PA"),
    ("staff@pa.dev", "PA Staff", "practice_staff", "PA"),
    ("admin@la.dev", "LA Admin", "lab_admin", "LA"),
    ("tech@la.dev", "LA Tech", "lab_technician", "LA"),
]


async def seed() -> None:
    async with AdminSessionLocal() as db:
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

        if not (await db.execute(select(OrgConnection).where(
                OrgConnection.practice_org_id == orgs["PA"].id,
                OrgConnection.lab_org_id == orgs["LA"].id))).scalar_one_or_none():
            db.add(OrgConnection(tenant_id=tenant.id,
                                 practice_org_id=orgs["PA"].id,
                                 lab_org_id=orgs["LA"].id,
                                 status="accepted"))

        if not (await db.execute(select(RosterMember).where(
                RosterMember.org_id == orgs["PA"].id))).scalars().first():
            db.add(RosterMember(tenant_id=tenant.id, org_id=orgs["PA"].id,
                                kind="doctor", display_name="Dr. Demo",
                                is_default=True))

        await db.commit()
        print(f"seed ok: tenant={tenant.id} PA={orgs['PA'].id} "
              f"LA={orgs['LA'].id} LB={orgs['LB'].id}")


if __name__ == "__main__":
    asyncio.run(seed())
