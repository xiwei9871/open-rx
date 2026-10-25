#!/usr/bin/env python3
"""SAFE-006 backup: PostgreSQL dump + S3 object copy + manifest.

Produces a backup directory:
  backups/<ts>/db.dump            (pg_dump custom format, ADMIN url)
  backups/<ts>/objects/<key>      (every object in the asset bucket)
  backups/<ts>/manifest.json      (row counts, object sha256/size)

Usage:
  python scripts/backup.py [--out backups/<ts>]
Env: DATABASE_ADMIN_URL or DATABASE_URL, S3_ENDPOINT_URL, S3_ACCESS_KEY,
     S3_SECRET_KEY, S3_BUCKET — same names the API uses (.env is loaded).

PG_DOCKER=<container> runs pg_dump inside the postgres container so the
client version always matches the server (drill on the dev compose stack).
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))

import boto3  # noqa: E402
from botocore.config import Config  # noqa: E402


def _settings():
    from app.config import get_settings
    return get_settings()


def _url_parts(url: str) -> tuple[str, str, str]:
    """postgresql+asyncpg://user:pass@host:port/db -> (user, hostport, db)"""
    u = url.replace("postgresql+asyncpg://", "postgresql://")
    m = re.match(r"postgresql://([^:]+):[^@]*@([^/]+)/(.+)", u)
    return m.group(1), m.group(2), m.group(3)


def _pg_dump(url: str, dest: str) -> None:
    container = os.environ.get("PG_DOCKER")
    if container:
        user, _hp, db = _url_parts(url)
        with open(dest, "wb") as fh:
            subprocess.run(
                ["docker", "exec", container, "pg_dump", "-U", user,
                 "--format=custom", "--no-owner", db],
                check=True, stdout=fh)
        return
    subprocess.run(
        ["pg_dump", "--format=custom", "--no-owner", "--file", dest,
         url.replace("postgresql+asyncpg://", "postgresql://")],
        check=True)


def _s3(s):
    # proxies={} — local S3 endpoints must never route through a system
    # HTTP proxy (botocore honours macOS system proxy by default).
    return boto3.client(
        "s3", endpoint_url=s.s3_endpoint_url,
        aws_access_key_id=s.s3_access_key,
        aws_secret_access_key=s.s3_secret_key,
        config=Config(proxies={}))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    s = _settings()
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = args.out or os.path.join("backups", ts)
    os.makedirs(os.path.join(out, "objects"), exist_ok=True)

    dump = os.path.join(out, "db.dump")
    _pg_dump(s.database_admin_url or s.database_url, dump)

    s3 = _s3(s)
    manifest = {"created_at": datetime.now(UTC).isoformat(),
                "bucket": s.s3_bucket, "objects": []}
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=s.s3_bucket):
        for o in page.get("Contents", []):
            key = o["Key"]
            dest = os.path.join(out, "objects", key)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            s3.download_file(s.s3_bucket, key, dest)
            with open(dest, "rb") as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()
            manifest["objects"].append({
                "key": key, "bytes": o["Size"], "sha256": digest})
    manifest["object_count"] = len(manifest["objects"])
    with open(os.path.join(out, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"backup ok: {out} "
          f"(db.dump {os.path.getsize(dump)} bytes, "
          f"{manifest['object_count']} objects)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
