"""TASK-0002 base: login, TOTP 2FA, session auth, logout, me.

Login events are audited (success/failure/2fa). Passwords argon2id.
Tenant binding at the auth boundary goes through resolve_login() — a
SECURITY DEFINER function owned by the admin role — so the runtime role never
needs RLS-exempt credentials (B0.1; replaces the B0 admin-engine read).
"""
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, text, update

from app.audit import record
from app.config import get_settings
from app.deps import Db, Me, SESSION_COOKIE

SESSION_HINT_COOKIE = "easyrs_session_hint"
from app.modules.auth.models import AuthChallenge, AuthSession
from app.modules.auth.schemas import (
    LoginRequest, LoginResult, MeOut,
    TwoFAEnableRequest, TwoFASetupResult, TwoFAVerifyRequest,
)
from app.modules.iam.models import UserAccount
from app.ratelimit import allow
from app.security import (
    dec_totp, enc_totp, hash_password, new_session_token, token_hash,
    verify_password,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["auth"])
_s = get_settings()


def _unauth(msg: str = "Invalid credentials") -> HTTPException:
    return HTTPException(status_code=401,
                         detail={"code": "unauthorized", "message": msg})


def _limited(msg: str = "Too many attempts") -> HTTPException:
    return HTTPException(status_code=429,
                         detail={"code": "rate_limited", "message": msg})


async def _resolve_login(db: AsyncSession, email: str):
    """Pre-auth membership/org/tenant projection via SECURITY DEFINER fn."""
    row = (await db.execute(
        text("SELECT user_id, org_id, tenant_id, org_status, member_role "
             "FROM resolve_login(:email)"), {"email": email}
    )).mappings().first()
    return row


async def _issue_session(
    db: AsyncSession, request: Request, response: Response,
    user: UserAccount, action: str,
) -> None:
    r = await _resolve_login(db, user.email)
    raw, hashed = new_session_token()
    sess = AuthSession(
        token_hash=hashed,
        user_id=user.id,
        active_org_id=r["org_id"] if r else None,
        tenant_id=r["tenant_id"] if r else None,
        expires_at=datetime.now(UTC) + timedelta(seconds=_s.session_ttl_seconds),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(sess)
    record(db, action=action, object_type="user_account", object_id=user.id,
           tenant_id=r["tenant_id"] if r else None,
           org_id=r["org_id"] if r else None,
           actor_user_id=user.id, request=request)
    await db.commit()
    response.set_cookie(
        SESSION_COOKIE, raw, max_age=_s.session_ttl_seconds,
        httponly=True, samesite="lax", secure=_s.env == "prod",
    )
    # JS-readable marker so the SPA can skip the /auth/me probe (and its
    # noisy 401 console entry) for visitors who were never signed in.
    # Carries no credentials — the HttpOnly session cookie is authoritative.
    response.set_cookie(
        SESSION_HINT_COOKIE, "1", max_age=_s.session_ttl_seconds,
        httponly=False, samesite="lax", secure=_s.env == "prod",
    )


@router.post("/auth/login", response_model=LoginResult, operation_id="login")
async def login(body: LoginRequest, request: Request, response: Response, db: Db):
    ip = request.client.host if request.client else "unknown"
    email = body.email.lower()
    if not await allow("login_email", email,
                       _s.rl_login_email_limit, _s.rl_login_email_window) \
            or not await allow("login_ip", ip,
                               _s.rl_login_ip_limit, _s.rl_login_ip_window):
        record(db, action="login_rate_limited", object_type="user_account",
               object_id=email, request=request)
        await db.commit()
        raise _limited()

    user = (await db.execute(
        select(UserAccount).where(UserAccount.email == email)
    )).scalar_one_or_none()
    if not user or user.status != "active" \
            or not verify_password(body.password, user.password_hash):
        record(db, action="login_failed", object_type="user_account",
               object_id=user.id if user else email, request=request)
        await db.commit()
        raise _unauth()

    if user.totp_enabled:
        if not user.totp_secret_enc:
            # Fail closed (S1a-00A): an enabled flag without a usable secret is
            # an inconsistent account state. Never downgrade to single-factor;
            # deny and require controlled recovery (re-enrollment by admin).
            record(db, action="login_denied_2fa_inconsistent",
                   object_type="user_account", object_id=user.id,
                   actor_user_id=user.id, request=request)
            await db.commit()
            raise HTTPException(status_code=401, detail={
                "code": "totp_recovery_required",
                "message": "Two-factor is enabled but its secret is unusable; "
                           "contact an administrator to re-enroll"})
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
    ip = request.client.host if request.client else "unknown"
    if not await allow("totp_ip", ip,
                       _s.rl_totp_ip_limit, _s.rl_totp_ip_window):
        raise _limited()
    ch = await db.get(AuthChallenge, body.challenge_id)
    now = datetime.now(UTC)
    if not ch or ch.consumed_at or ch.expires_at <= now \
            or ch.attempts >= _s.challenge_max_attempts:
        raise _unauth("Challenge expired or exhausted")
    user = await db.get(UserAccount, ch.user_id)
    try:
        ok = bool(user and user.totp_secret_enc
                  and pyotp.TOTP(dec_totp(user.totp_secret_enc)).verify(
                      body.code, valid_window=1))
    except Exception:
        # Corrupt/undecryptable secret must deny, not 500 (fail closed).
        ok = False
        record(db, action="login_2fa_secret_unusable", object_type="user_account",
               object_id=ch.user_id, request=request)
    if not ok:
        ch.attempts += 1
        exhausted = ch.attempts >= _s.challenge_max_attempts
        if exhausted:
            ch.consumed_at = now
        record(db, action="login_2fa_failed", object_type="user_account",
               object_id=ch.user_id, request=request,
               after={"attempts": ch.attempts, "exhausted": exhausted})
        await db.commit()
        raise _unauth("Invalid 2FA code")
    ch.consumed_at = now
    await _issue_session(db, request, response, user, "login_success")
    return LoginResult()


@router.post("/auth/logout", status_code=204, operation_id="logout")
async def logout(request: Request, db: Db, me: Me):
    me.session.revoked_at = datetime.now(UTC)
    record(db, action="logout", object_type="user_account", object_id=me.user.id,
           tenant_id=me.tenant_id, org_id=me.org.id,
           actor_user_id=me.user.id, request=request)
    await db.commit()
    # A directly-returned Response bypasses the injected `response` param —
    # delete_cookie must land on this object or no Set-Cookie is emitted.
    out = Response(status_code=204)
    out.delete_cookie(SESSION_COOKIE)
    out.delete_cookie(SESSION_HINT_COOKIE)
    return out


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
    me.user.totp_secret_enc = enc_totp(body.secret)
    me.user.totp_enabled = True
    record(db, action="2fa_enabled", object_type="user_account",
           object_id=me.user.id, tenant_id=me.tenant_id, org_id=me.org.id,
           actor_user_id=me.user.id, request=request)
    await db.commit()
    return Response(status_code=204)


@router.post("/auth/password", status_code=204, operation_id="changePassword")
async def change_password(body: dict, request: Request, db: Db, me: Me):
    if not await allow("password", str(me.user.id),
                       _s.rl_password_limit, _s.rl_password_window):
        raise _limited()
    old, new = body.get("old_password", ""), body.get("new_password", "")
    if len(new) < _s.password_min_length:
        raise HTTPException(status_code=422, detail={
            "code": "validation_failed",
            "message": f"password must be >= {_s.password_min_length} chars"})
    if not verify_password(old, me.user.password_hash):
        raise _unauth("Old password mismatch")
    me.user.password_hash = hash_password(new)
    # Revoke every OTHER session — a password change invalidates prior auth.
    await db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == me.user.id,
               AuthSession.id != me.session.id,
               AuthSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    record(db, action="password_changed", object_type="user_account",
           object_id=me.user.id, tenant_id=me.tenant_id, org_id=me.org.id,
           actor_user_id=me.user.id, request=request,
           after={"other_sessions_revoked": True})
    await db.commit()
    return Response(status_code=204)
