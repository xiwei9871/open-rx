"""TASK-0002 base: login, TOTP 2FA, session auth, logout, me.

Login events are audited (success/failure/2fa). Passwords argon2id.
"""
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select

from app.audit import record
from app.config import get_settings
from app.db import AdminSessionLocal
from app.deps import Db, Me, SESSION_COOKIE
from app.modules.auth.models import AuthChallenge, AuthSession
from app.modules.auth.schemas import (
    LoginRequest, LoginResult, MeOut,
    TwoFAEnableRequest, TwoFASetupResult, TwoFAVerifyRequest,
)
from app.modules.iam.models import Membership, Organization, UserAccount
from app.security import (
    hash_password, new_session_token, token_hash, verify_password,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["auth"])
_s = get_settings()


def _unauth(msg: str = "Invalid credentials") -> HTTPException:
    return HTTPException(status_code=401,
                         detail={"code": "unauthorized", "message": msg})


async def _issue_session(
    db: AsyncSession, request: Request, response: Response,
    user: UserAccount, action: str,
) -> None:
    # Membership/org are RLS-scoped; at the auth boundary there is no tenant
    # context yet, so this ONE lookup runs on the admin engine (documented
    # exception — every post-login request uses the least-privilege engine).
    async with AdminSessionLocal() as adm:
        m = (await adm.execute(
            select(Membership).where(
                Membership.user_id == user.id, Membership.status == "active",
            ).order_by(Membership.created_at)
        )).scalars().first()
        org = await adm.get(Organization, m.org_id) if m else None
    raw, hashed = new_session_token()
    sess = AuthSession(
        token_hash=hashed,
        user_id=user.id,
        active_org_id=m.org_id if m else None,
        tenant_id=org.tenant_id if org else None,
        expires_at=datetime.now(UTC) + timedelta(seconds=_s.session_ttl_seconds),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(sess)
    record(db, action=action, object_type="user_account", object_id=user.id,
           tenant_id=org.tenant_id if org else None,
           org_id=org.id if org else None,
           actor_user_id=user.id, request=request)
    await db.commit()
    response.set_cookie(
        SESSION_COOKIE, raw, max_age=_s.session_ttl_seconds,
        httponly=True, samesite="lax", secure=_s.env == "prod",
    )


@router.post("/auth/login", response_model=LoginResult, operation_id="login")
async def login(body: LoginRequest, request: Request, response: Response, db: Db):
    user = (await db.execute(
        select(UserAccount).where(UserAccount.email == body.email.lower())
    )).scalar_one_or_none()
    if not user or user.status != "active" \
            or not verify_password(body.password, user.password_hash):
        record(db, action="login_failed", object_type="user_account",
               object_id=user.id if user else body.email, request=request)
        await db.commit()
        raise _unauth()

    if user.totp_enabled and user.totp_secret:
        ch = AuthChallenge(
            user_id=user.id, purpose="totp_login",
            expires_at=datetime.now(UTC) + timedelta(seconds=_s.challenge_ttl_seconds),
        )
        db.add(ch)
        record(db, action="login_2fa_required", object_type="user_account",
               object_id=user.id, actor_user_id=user.id, request=request)
        await db.commit()
        return LoginResult(requires_2fa=True, challenge_id=ch.id)

    await _issue_session(db, request, response, user, "login_success")
    return LoginResult()


@router.post("/auth/2fa/verify", response_model=LoginResult, operation_id="verifyTwoFA")
async def verify_2fa(body: TwoFAVerifyRequest, request: Request,
                     response: Response, db: Db):
    ch = await db.get(AuthChallenge, body.challenge_id)
    now = datetime.now(UTC)
    if not ch or ch.consumed_at or ch.expires_at <= now:
        raise _unauth("Challenge expired or unknown")
    user = await db.get(UserAccount, ch.user_id)
    if not user or not user.totp_secret \
            or not pyotp.TOTP(user.totp_secret).verify(body.code, valid_window=1):
        record(db, action="login_2fa_failed", object_type="user_account",
               object_id=ch.user_id, request=request)
        await db.commit()
        raise _unauth("Invalid 2FA code")
    ch.consumed_at = now
    await _issue_session(db, request, response, user, "login_success")
    return LoginResult()


@router.post("/auth/logout", status_code=204, operation_id="logout")
async def logout(request: Request, response: Response, db: Db, me: Me):
    me.session.revoked_at = datetime.now(UTC)
    record(db, action="logout", object_type="user_account", object_id=me.user.id,
           tenant_id=me.tenant_id, org_id=me.org.id,
           actor_user_id=me.user.id, request=request)
    await db.commit()
    response.delete_cookie(SESSION_COOKIE)
    return Response(status_code=204)


@router.get("/auth/me", response_model=MeOut, operation_id="me")
async def me(p: Me):
    return MeOut(
        user_id=p.user.id, email=p.user.email, display_name=p.user.display_name,
        org_id=p.org.id, org_name=p.org.name, org_kind=p.org.kind,
        tenant_id=p.tenant_id, role=p.membership.role,
        permissions=sorted(p.permissions),
        session_expires_at=p.session.expires_at,
    )


@router.post("/auth/2fa/setup", response_model=TwoFASetupResult,
             operation_id="setupTwoFA")
async def setup_2fa(p: Me):
    # Secret is returned once, client-side only; it is persisted only after the
    # user proves possession via /2fa/enable.
    secret = pyotp.random_base32()
    return TwoFASetupResult(
        secret=secret,
        otpauth_url=pyotp.TOTP(secret).provisioning_uri(
            name=p.user.email, issuer_name="EasyRS"),
    )


@router.post("/auth/2fa/enable", status_code=204, operation_id="enableTwoFA")
async def enable_2fa(body: TwoFAEnableRequest, request: Request, db: Db, me: Me):
    if not pyotp.TOTP(body.secret).verify(body.code, valid_window=1):
        raise HTTPException(status_code=422, detail={
            "code": "validation_failed", "message": "TOTP code does not match secret"})
    me.user.totp_secret = body.secret
    me.user.totp_enabled = True
    record(db, action="2fa_enabled", object_type="user_account",
           object_id=me.user.id, tenant_id=me.tenant_id, org_id=me.org.id,
           actor_user_id=me.user.id, request=request)
    await db.commit()
    return Response(status_code=204)


@router.post("/auth/password", status_code=204, operation_id="changePassword")
async def change_password(body: dict, request: Request, db: Db, me: Me):
    old, new = body.get("old_password", ""), body.get("new_password", "")
    if len(new) < _s.password_min_length:
        raise HTTPException(status_code=422, detail={
            "code": "validation_failed",
            "message": f"password must be >= {_s.password_min_length} chars"})
    if not verify_password(old, me.user.password_hash):
        raise _unauth("Old password mismatch")
    me.user.password_hash = hash_password(new)
    record(db, action="password_changed", object_type="user_account",
           object_id=me.user.id, tenant_id=me.tenant_id, org_id=me.org.id,
           actor_user_id=me.user.id, request=request)
    await db.commit()
    return Response(status_code=204)
