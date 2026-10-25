"""S1a-03: uploads + assets + file references + download grants.

Flow: declareUpload -> presigned PUT (staging key) -> completeUpload
(server re-hashes + validates, promotes to content-addressed asset key).
Assets are immutable: no update/delete endpoints exist. Access requires
owning the asset's org OR holding a live file_reference to a subject owned by
the caller's org. Lab roles have no path to patient assets until Rx subjects
exist (subject_type rx/notification/order returns 422 today).
"""
import asyncio
import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record
from app.config import get_settings
from app.deps import (Db, Me, Principal, limit_writes, require_perm,
                      tenant_commit, _deny)
from app.modules.assets.models import (AccessGrant, Asset, FileReference,
                                       UploadSession)
from app.modules.assets.schemas import (AssetOut, DownloadRequest,
                                        FileReferenceOut, ReferenceCreate,
                                        SignedUrlOut, UploadComplete,
                                        UploadDeclare, UploadSessionOut)
from app.modules.clinical.models import Patient, TreatmentCase
from app.storage import s3, s3_presign

router = APIRouter(tags=["assets"])
_s = get_settings()


def _asset_join_out(ref: FileReference, asset: Asset) -> dict:
    a = AssetOut.model_validate(asset)
    return {**FileReferenceOut.model_validate(ref).model_dump(mode="json"),
            "asset": a.model_dump(mode="json")}


def _validate_stl(content: bytes) -> bool:
    """Minimal mesh sanity (ASSET-008): binary layout or ASCII markers."""
    if len(content) >= 84:
        n = int.from_bytes(content[80:84], "little")
        if 84 + 50 * n == len(content):
            return True
    head = content.lstrip()[:5].lower()
    return head == b"solid" and b"facet" in content[:8192]


async def _subject_owned(db: AsyncSession, p: Principal,
                         subject_type: str, subject_id: uuid.UUID) -> bool:
    if subject_type == "patient":
        row = await db.get(Patient, subject_id)
        return bool(row and row.org_id == p.org.id
                    and row.tenant_id == p.tenant_id and not row.deleted_at)
    if subject_type == "case":
        row = await db.get(TreatmentCase, subject_id)
        return bool(row and row.org_id == p.org.id
                    and row.tenant_id == p.tenant_id)
    if subject_type == "rx":
        from app.modules.rx.models import Rx
        from app.modules.rx.router import LAB_VISIBLE_STATUSES
        row = await db.get(Rx, subject_id)
        if not row or row.tenant_id != p.tenant_id:
            return False
        if row.practice_org_id == p.org.id:
            return True
        return (row.lab_org_id == p.org.id
                and row.status in LAB_VISIBLE_STATUSES)
    return False  # notification/order — no such entities yet


async def _asset_visible(db: AsyncSession, p: Principal, asset: Asset) -> bool:
    if asset.tenant_id == p.tenant_id and asset.org_id == p.org.id:
        return True
    refs = (await db.execute(select(FileReference).where(
        FileReference.asset_id == asset.id,
        FileReference.revoked_at.is_(None)))).scalars().all()
    for ref in refs:
        if await _subject_owned(db, p, ref.subject_type, ref.subject_id):
            return True
    return False


async def _get_visible_asset(db: AsyncSession, p: Principal,
                             asset_id: uuid.UUID, request: Request) -> Asset:
    a = await db.get(Asset, asset_id)
    if not a or a.tenant_id != p.tenant_id \
            or not await _asset_visible(db, p, a):
        await _deny(db, request, p, "asset_not_visible")
    return a


def _staging_key(org_id: uuid.UUID, session_id: uuid.UUID) -> str:
    return f"staging/{org_id}/{session_id}"


def _asset_key(tenant_id: uuid.UUID, org_id: uuid.UUID, sha256: str) -> str:
    """Org-namespaced content key (S1a1-01). Same bytes in two orgs -> two
    independent objects; no org ever shares a mutable physical object.
    Legacy flat keys assets/{sha256} remain valid — rows store the exact
    key, readers never recompute it."""
    return f"assets/{tenant_id}/{org_id}/{sha256}"


async def _ensure_bucket() -> None:
    """Bucket + CORS for browser presigned PUT (cross-origin by design —
    assets live on the storage host, not the API host)."""
    def work():
        try:
            s3().head_bucket(Bucket=_s.s3_bucket)
        except ClientError:
            s3().create_bucket(Bucket=_s.s3_bucket)
        s3().put_bucket_cors(
            Bucket=_s.s3_bucket,
            CORSConfiguration={"CORSRules": [{
                "AllowedOrigins": _s.cors_origin_list or ["*"],
                "AllowedMethods": ["PUT", "GET", "HEAD"],
                "AllowedHeaders": ["*"],
                "MaxAgeSeconds": 3000,
            }]})
    await asyncio.to_thread(work)


async def _expire_stale_sessions(db: AsyncSession) -> None:
    """Opportunistic cleanup (ASSET-010/S1a1-02): mark expired sessions and
    drop their staging objects — best-effort, inside the CALLER's
    transaction. No commit here: committing mid-request would drop the
    request-scoped SET LOCAL app.tenant_id and every later tenant-scoped
    statement would hit deny-all RLS. Cleanup visibility is RLS-filtered
    to the caller's tenant, which is exactly the authorized scope.
    Storage failures are swallowed — a missing/dead object must never
    block a new upload."""
    stale = (await db.execute(select(UploadSession).where(
        UploadSession.status == "open",
        UploadSession.expires_at < datetime.now(UTC)).limit(50))).scalars().all()
    for sess in stale:
        sess.status = "expired"
        try:
            await asyncio.to_thread(
                s3().delete_object, Bucket=_s.s3_bucket, Key=sess.storage_key)
        except Exception:
            pass


# ---------------- uploads -----------------------------------------------------
@router.post("/uploads", response_model=UploadSessionOut, status_code=201,
             operation_id="declareUpload")
async def declare_upload(body: UploadDeclare, request: Request, db: Db,
                         p: Me, _g=Depends(require_perm("asset:write"))):
    await limit_writes(p)
    if body.bytes > _s.upload_max_bytes:
        raise HTTPException(status_code=422, detail={
            "code": "validation_failed",
            "message": f"file exceeds { _s.upload_max_bytes } byte limit"})
    await _ensure_bucket()
    await _expire_stale_sessions(db)

    # Natural-key dedup: an open session for the same content resumes.
    existing = (await db.execute(select(UploadSession).where(
        UploadSession.org_id == p.org.id,
        UploadSession.sha256 == body.sha256,
        UploadSession.status == "open",
        UploadSession.expires_at > datetime.now(UTC))
        .order_by(UploadSession.created_at))).scalars().first()
    if existing and existing.bytes == body.bytes:
        url = await asyncio.to_thread(
            s3_presign().generate_presigned_url, "put_object",
            Params={"Bucket": _s.s3_bucket, "Key": existing.storage_key},
            ExpiresIn=_s.upload_session_ttl_seconds)
        return UploadSessionOut(id=existing.id, status=existing.status,
                                upload_urls=[url],
                                expires_at=existing.expires_at, resumed=True)

    sess = UploadSession(
        tenant_id=p.tenant_id, org_id=p.org.id, user_id=p.user.id,
        sha256=body.sha256, bytes=body.bytes, kind=body.kind, jaw=body.jaw,
        storage_key=f"staging/{p.org.id}/{uuid.uuid4()}",
        expires_at=datetime.now(UTC)
        + timedelta(seconds=_s.upload_session_ttl_seconds))
    db.add(sess)
    await db.flush()
    record(db, action="upload.declared", object_type="upload_session",
           object_id=sess.id, tenant_id=p.tenant_id, org_id=p.org.id,
           actor_user_id=p.user.id, request=request,
           after={"sha256": body.sha256, "bytes": body.bytes})
    await tenant_commit(db, p)
    url = await asyncio.to_thread(
        s3_presign().generate_presigned_url, "put_object",
        Params={"Bucket": _s.s3_bucket, "Key": sess.storage_key},
        ExpiresIn=_s.upload_session_ttl_seconds)
    return UploadSessionOut(id=sess.id, status=sess.status,
                            upload_urls=[url], expires_at=sess.expires_at)


@router.post("/uploads/{session_id}/complete", response_model=AssetOut,
             status_code=202, operation_id="completeUpload")
async def complete_upload(session_id: uuid.UUID, body: UploadComplete,
                          request: Request, db: Db, p: Me,
                          _g=Depends(require_perm("asset:write"))):
    await limit_writes(p)
    sess = await db.get(UploadSession, session_id, with_for_update=True)
    if not sess or sess.tenant_id != p.tenant_id or sess.org_id != p.org.id:
        await _deny(db, request, p, "upload_session_not_found")
    if sess.status != "open" or sess.expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=409, detail={
            "code": "conflict", "message": "upload session not open"})
    if sess.sha256 != body.sha256:
        raise HTTPException(status_code=422, detail={
            "code": "validation_failed",
            "message": "sha256 does not match the declared upload"})

    # Verify actual content: size + sha256 + structural check. Anything less
    # than a byte-exact match aborts and keeps the session open for retry.
    try:
        obj = await asyncio.to_thread(
            s3().get_object, Bucket=_s.s3_bucket, Key=sess.storage_key)
    except ClientError:
        raise HTTPException(status_code=409, detail={
            "code": "conflict",
            "message": "no object found at the staging location"})
    content = await asyncio.to_thread(obj["Body"].read)
    digest = hashlib.sha256(content).hexdigest()
    if len(content) != sess.bytes or digest != sess.sha256:
        await asyncio.to_thread(
            s3().delete_object, Bucket=_s.s3_bucket, Key=sess.storage_key)
        raise HTTPException(status_code=422, detail={
            "code": "content_mismatch",
            "message": "uploaded bytes do not match declared size/sha256"})
    if sess.kind == "stl" and not _validate_stl(content):
        await asyncio.to_thread(
            s3().delete_object, Bucket=_s.s3_bucket, Key=sess.storage_key)
        raise HTTPException(status_code=422, detail={
            "code": "invalid_mesh",
            "message": "file is not a recognizable STL mesh"})

    key = _asset_key(sess.tenant_id, sess.org_id, digest)
    await asyncio.to_thread(
        s3().copy_object, Bucket=_s.s3_bucket, Key=key,
        CopySource={"Bucket": _s.s3_bucket, "Key": sess.storage_key})
    await asyncio.to_thread(
        s3().delete_object, Bucket=_s.s3_bucket, Key=sess.storage_key)

    # Same content re-uploaded by the same org -> the dedup'd asset returns.
    asset = (await db.execute(select(Asset).where(
        Asset.org_id == p.org.id, Asset.sha256 == digest))).scalar_one_or_none()
    if not asset:
        asset = Asset(tenant_id=p.tenant_id, org_id=p.org.id,
                      uploaded_by_user_id=p.user.id, sha256=digest,
                      kind=sess.kind, jaw=sess.jaw, bytes=len(content),
                      storage_key=key, format_status="format_ok")
        db.add(asset)
    sess.status = "completed"
    await db.flush()
    record(db, action="asset.created", object_type="asset",
           object_id=asset.id, tenant_id=p.tenant_id, org_id=p.org.id,
           actor_user_id=p.user.id, request=request,
           after={"sha256": digest, "kind": sess.kind, "jaw": sess.jaw})
    await tenant_commit(db, p)
    return asset


# ---------------- assets ------------------------------------------------------
@router.get("/assets/{asset_id}", response_model=AssetOut,
            operation_id="getAsset")
async def get_asset(asset_id: uuid.UUID, request: Request, db: Db, p: Me,
                    _g=Depends(require_perm("asset:read"))):
    return await _get_visible_asset(db, p, asset_id, request)


@router.post("/assets/{asset_id}/download", response_model=SignedUrlOut,
             operation_id="downloadAsset")
async def download_asset(asset_id: uuid.UUID, body: DownloadRequest | None,
                         request: Request, db: Db, p: Me,
                         _g=Depends(require_perm("asset:read"))):
    asset = await _get_visible_asset(db, p, asset_id, request)
    ttl = (body.ttl_seconds if body else 900)
    grant = AccessGrant(
        tenant_id=p.tenant_id, asset_id=asset.id, org_id=p.org.id,
        user_id=p.user.id,
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl))
    db.add(grant)
    record(db, action="asset.download_granted", object_type="asset",
           object_id=asset.id, tenant_id=p.tenant_id, org_id=p.org.id,
           actor_user_id=p.user.id, request=request,
           after={"ttl": ttl})
    await tenant_commit(db, p)
    url = await asyncio.to_thread(
        s3_presign().generate_presigned_url, "get_object",
        Params={"Bucket": _s.s3_bucket, "Key": asset.storage_key},
        ExpiresIn=ttl)
    # presigned URLs cannot be revoked once issued (S3 limitation) — revoked
    # references block NEW grants; TTL bounds the exposure window.
    return SignedUrlOut(url=url, expires_at=grant.expires_at,
                        grant_id=grant.id)


# ---------------- file references ----------------------------------------------
@router.post("/assets/{asset_id}/references", response_model=FileReferenceOut,
             status_code=201, operation_id="grantAssetReference")
async def grant_reference(asset_id: uuid.UUID, body: ReferenceCreate,
                          request: Request, db: Db, p: Me,
                          _g=Depends(require_perm("asset:share"))):
    await limit_writes(p)
    asset = await _get_visible_asset(db, p, asset_id, request)
    if asset.format_status != "format_ok":
        raise HTTPException(status_code=422, detail={
            "code": "validation_failed",
            "message": "only structurally-valid assets may be referenced"})
    if body.subject_type in ("rx", "notification", "order"):
        raise HTTPException(status_code=422, detail={
            "code": "validation_failed",
            "message": f"subject_type {body.subject_type} not supported yet"})
    if not await _subject_owned(db, p, body.subject_type, body.subject_id):
        await _deny(db, request, p, "subject_not_owned")
    live = (await db.execute(select(FileReference).where(
        FileReference.asset_id == asset.id,
        FileReference.subject_type == body.subject_type,
        FileReference.subject_id == body.subject_id,
        FileReference.role == body.role,
        FileReference.revoked_at.is_(None)))).scalar_one_or_none()
    if live:
        return live
    ref = FileReference(
        tenant_id=p.tenant_id, asset_id=asset.id,
        subject_type=body.subject_type, subject_id=body.subject_id,
        role=body.role, granted_by_org_id=p.org.id,
        granted_by_user_id=p.user.id)
    db.add(ref)
    record(db, action="asset.reference_granted", object_type="file_reference",
           object_id=ref.id, tenant_id=p.tenant_id, org_id=p.org.id,
           actor_user_id=p.user.id, request=request,
           after={"asset_id": str(asset.id),
                  "subject": f"{body.subject_type}:{body.subject_id}"})
    await tenant_commit(db, p)
    return ref


@router.delete("/assets/{asset_id}/references", status_code=204,
               operation_id="revokeAssetReference")
async def revoke_reference(asset_id: uuid.UUID, request: Request, db: Db,
                           p: Me, _g=Depends(require_perm("asset:share")),
                           subject_type: str | None = None,
                           subject_id: uuid.UUID | None = None):
    await limit_writes(p)
    refs = (await db.execute(select(FileReference).where(
        FileReference.asset_id == asset_id,
        FileReference.revoked_at.is_(None)))).scalars().all()
    n = 0
    for ref in refs:
        if subject_type and ref.subject_type != subject_type:
            continue
        if subject_id and ref.subject_id != subject_id:
            continue
        # the granting org or the org owning the referenced subject may revoke
        if ref.granted_by_org_id == p.org.id or await _subject_owned(
                db, p, ref.subject_type, ref.subject_id):
            ref.revoked_at = datetime.now(UTC)
            n += 1
    if n:
        record(db, action="asset.reference_revoked", object_type="asset",
               object_id=asset_id, tenant_id=p.tenant_id, org_id=p.org.id,
               actor_user_id=p.user.id, request=request,
               after={"revoked": n})
        await tenant_commit(db, p)
