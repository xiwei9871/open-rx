"""Rx delivery bundle builder (S1b1-01).

Produces a real ZIP on DISK (tempfile, never an unbounded in-memory blob):
  {rx_number}.zip
  ├── prescription.pdf        — EasyRS-generated summary sheet
  ├── manifest.json           — per-file name/kind/jaw/role/sha256/bytes
  └── attachments/            — the actual referenced file bytes

Every referenced object is HEAD-verified (exists, size matches the asset
row) and SHA-256-verified while streaming into the archive. Any failure
aborts the build — callers must not touch Rx state on BundleError.
Filenames are sanitized against ZIP path traversal.
"""
import asyncio
import hashlib
import json
import os
import re
import tempfile
import uuid
import zipfile
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.modules.assets.models import Asset, FileReference
from app.modules.clinical.models import Patient
from app.modules.iam.models import Organization, RosterMember
from app.modules.rx.models import CatalogItem, Rx, RxItem
from app.pdfgen import prescription_pdf
from app.storage import s3


class BundleError(Exception):
    """Package could not be built or verified — no state transition."""


_CHUNK = 1 << 20  # 1 MiB streaming chunks


def _safe_name(name: str) -> str:
    """Strip path separators/traversal; keep a conservative charset."""
    base = os.path.basename(name).replace("\\", "_")
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base).lstrip(".")
    return base or "file"


def _entry_name(idx: int, asset: Asset) -> str:
    ext = {"stl": "stl", "pdf": "pdf", "image": "img", "other": "bin"}.get(
        asset.kind, "bin")
    jaw = asset.jaw if asset.jaw in ("upper", "lower") else "attachment"
    return "attachments/" + _safe_name(f"{jaw}-{idx:02d}.{ext}")


async def _write_verified(zf: zipfile.ZipFile, entry: str, key: str,
                          expected_sha: str, expected_bytes: int) -> None:
    """Stream object -> zip entry while hashing. Raises BundleError on any
    existence/size/hash failure."""
    def work() -> None:
        try:
            head = s3().head_object(Bucket=get_settings().s3_bucket, Key=key)
        except Exception as e:
            raise BundleError(f"object missing: {key} ({e})")
        if head["ContentLength"] != expected_bytes:
            raise BundleError(
                f"size mismatch for {key}: "
                f"{head['ContentLength']} != {expected_bytes}")
        try:
            body = s3().get_object(Bucket=get_settings().s3_bucket,
                                   Key=key)["Body"]
        except Exception as e:
            raise BundleError(f"object unreadable: {key} ({e})")
        digest = hashlib.sha256()
        total = 0
        with zf.open(entry, "w", force_zip64=True) as w:
            for chunk in body.iter_chunks(_CHUNK):
                digest.update(chunk)
                total += len(chunk)
                w.write(chunk)
        if total != expected_bytes or digest.hexdigest() != expected_sha:
            raise BundleError(
                f"hash mismatch for {key}: stored bytes failed verification")
    await asyncio.to_thread(work)


async def _refs(db: AsyncSession, rx: Rx):
    return (await db.execute(
        select(FileReference, Asset)
        .join(Asset, Asset.id == FileReference.asset_id)
        .where(FileReference.subject_type == "rx",
               FileReference.subject_id == rx.id,
               FileReference.revoked_at.is_(None))
        .order_by(FileReference.created_at))).all()


async def _items(db: AsyncSession, rx: Rx):
    return (await db.execute(
        select(RxItem, CatalogItem)
        .join(CatalogItem, CatalogItem.id == RxItem.catalog_item_id)
        .where(RxItem.rx_id == rx.id)
        .order_by(RxItem.created_at))).all()


async def content_fingerprint(db: AsyncSession, rx: Rx) -> str:
    """sha256 over everything the delivered package depends on: Rx content
    fields, the item configuration, and the live file-reference set.
    Status/version are deliberately excluded — a check-in never changes
    what the package contains, an attachment/item edit always does."""
    items = await _items(db, rx)
    refs = await _refs(db, rx)
    payload = {
        "patient_id": str(rx.patient_id),
        "case_id": str(rx.case_id or ""),
        "lab_org_id": str(rx.lab_org_id or ""),
        "location_id": str(rx.location_id or ""),
        "doctor_id": str(rx.doctor_id or ""),
        "form_type": rx.form_type,
        "form_payload": rx.form_payload,
        "due_date": rx.due_date.isoformat() if rx.due_date else "",
        "notes": rx.notes or "",
        "items": [{"catalog_item_id": str(i.catalog_item_id),
                   "arch": i.arch, "tooth_ops": i.tooth_ops,
                   "options": i.options, "qty": i.qty}
                  for i, _ in items],
        "refs": sorted(f"{r.asset_id}:{r.role}" for r, _ in refs),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()


def _item_line(item: RxItem, cat: CatalogItem) -> str:
    parts = [f"{cat.code} {cat.name}", f"arch={item.arch}"]
    if item.qty != 1:
        parts.append(f"qty={item.qty}")
    if item.tooth_ops:
        ops = ", ".join(f"{o.get('tooth')}:{o.get('op')}"
                        for o in item.tooth_ops)
        parts.append(f"teeth[{ops}]")
    if item.options:
        parts.append("options=" + json.dumps(item.options,
                                             ensure_ascii=False,
                                             sort_keys=True))
    return " — ".join(parts)


async def _prescription_pdf(db: AsyncSession, rx: Rx,
                            manifest_files: list[dict]) -> bytes:
    patient = await db.get(Patient, rx.patient_id)
    practice = await db.get(Organization, rx.practice_org_id)
    lab = await db.get(Organization, rx.lab_org_id) if rx.lab_org_id else None
    doctor = await db.get(RosterMember, rx.doctor_id) if rx.doctor_id else None
    items = await _items(db, rx)
    pat = (f"{patient.last_name}, {patient.first_name}"
           if patient else str(rx.patient_id))
    pat += (f" (ref {patient.external_ref})"
            if patient and patient.external_ref else "")
    item_lines = [_item_line(i, c) for i, c in items] or ["(none)"]
    attach_lines = [
        f"{f['entry']}  {f['kind']}/{f.get('jaw') or '-'}  "
        f"{f['bytes']} B  sha256:{f['sha256'][:16]}…"
        for f in manifest_files] or ["(none)"]
    sections = [
        ("Parties", [
            f"Patient: {pat}",
            f"Practice: {practice.name if practice else rx.practice_org_id}",
            f"Prescriber: {doctor.display_name if doctor else '-'}",
            f"Laboratory: {lab.name if lab else '-'}",
        ]),
        ("Order", [
            f"Rx number: {rx.rx_number}",
            f"Status: {rx.status}",
            f"Due date: {rx.due_date or '-'}",
            f"Submitted (UTC): "
            f"{rx.submitted_at.isoformat() if rx.submitted_at else '-'}",
            f"Signed by: {rx.signature_name or '-'}",
        ]),
        ("Items", item_lines),
        ("Instructions", [rx.notes or "(none)"]),
        ("Attachments", attach_lines),
    ]
    return prescription_pdf(f"Prescription {rx.rx_number}", sections,
                            "Generated by EasyRS — synthetic development "
                            "document, not a real clinical prescription")


async def build_bundle(db: AsyncSession, rx: Rx) -> tuple[str, str, int, dict]:
    """Build the ZIP on disk.

    Returns (temp_path, zip_sha256, zip_bytes, manifest_dict).
    The caller owns the temp file and must unlink it.
    """
    refs = await _refs(db, rx)

    manifest_files = []
    for idx, (ref, asset) in enumerate(refs, start=1):
        manifest_files.append({
            "entry": _entry_name(idx, asset),
            "asset_id": str(asset.id),
            "kind": asset.kind, "jaw": asset.jaw, "role": ref.role,
            "sha256": asset.sha256, "bytes": asset.bytes,
        })
    manifest = {
        "rx_number": rx.rx_number, "rx_id": str(rx.id),
        "rx_version": rx.version, "status": rx.status,
        "generated_at": datetime.now(UTC).isoformat(),
        "files": manifest_files,
    }
    pdf = await _prescription_pdf(db, rx, manifest_files)

    fd, path = tempfile.mkstemp(prefix="rxb-", suffix=".zip")
    try:
        with os.fdopen(fd, "wb") as fh:
            with zipfile.ZipFile(fh, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("prescription.pdf", pdf)
                zf.writestr("manifest.json", json.dumps(manifest, indent=2))
                for idx, (_, asset) in enumerate(refs, start=1):
                    await _write_verified(
                        zf, manifest_files[idx - 1]["entry"],
                        asset.storage_key, asset.sha256, asset.bytes)
        digest = hashlib.sha256()
        size = 0
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(_CHUNK), b""):
                digest.update(chunk)
                size += len(chunk)
        return path, digest.hexdigest(), size, manifest
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise


def bundle_key(tenant_id: uuid.UUID, rx_id: uuid.UUID,
               bundle_id: uuid.UUID) -> str:
    return f"bundles/{tenant_id}/{rx_id}/{bundle_id}.zip"
