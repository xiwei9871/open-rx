#!/usr/bin/env python3
"""SAFE-006 restore drill: restore a backup into SCRATCH targets and verify.

Never restores over the live DB/bucket — restore target is a separate
database (`RESTORE_DATABASE_URL`, default <db>_restore) and a separate
bucket (`RESTORE_S3_BUCKET`, default <bucket>-restore). Verification:
  - table row counts after pg_restore
  - every manifest object re-uploaded, SHA-256 re-verified after a fresh GET

Usage:
  python scripts/restore.py backups/<ts>
Env: same as backup.py, plus RESTORE_DATABASE_URL / RESTORE_S3_BUCKET and
PG_DOCKER=<postgres container> to run pg/psql inside the container.
"""
import hashlib
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))

import boto3  # noqa: E402
from botocore.config import Config  # noqa: E402


def _settings():
    from app.config import get_settings
    return get_settings()


def _plain(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _url_parts(url: str) -> tuple[str, str]:
    u = _plain(url)
    m = re.match(r"postgresql://([^:]+):[^@]*@[^/]+/(.+)", u)
    return m.group(1), m.group(2)


def _s3(s):
    return boto3.client(
        "s3", endpoint_url=s.s3_endpoint_url,
        aws_access_key_id=s.s3_access_key,
        aws_secret_access_key=s.s3_secret_key,
        config=Config(proxies={}))


def _psql(url: str, sql: str, docker_c: str | None,
          db_override: str | None = None) -> str:
    if docker_c:
        user, db = _url_parts(url)
        r = subprocess.run(
            ["docker", "exec", docker_c, "psql", "-U", user, "-d",
             db_override or db, "-At", "-c", sql],
            check=True, capture_output=True, text=True)
        return r.stdout.strip()
    u = _plain(url)
    if db_override:
        u = u.rsplit("/", 1)[0] + "/" + db_override
    r = subprocess.run(["psql", u, "-At", "-c", sql],
                       check=True, capture_output=True, text=True)
    return r.stdout.strip()


def _restore_db(url: str, dump: str, docker_c: str | None) -> None:
    if docker_c:
        user, db = _url_parts(url)
        subprocess.run(["docker", "cp", dump,
                        f"{docker_c}:/tmp/drill_db.dump"], check=True)
        subprocess.run(
            ["docker", "exec", docker_c, "pg_restore", "-U", user,
             "--no-owner", "-d", db, "/tmp/drill_db.dump"], check=True)
        subprocess.run(["docker", "exec", docker_c, "rm",
                        "/tmp/drill_db.dump"], check=True)
        return
    subprocess.run(["pg_restore", "--no-owner", "--dbname", _plain(url),
                    dump], check=True)


def main() -> int:
    src = sys.argv[1]
    s = _settings()
    manifest = json.load(open(os.path.join(src, "manifest.json")))
    docker_c = os.environ.get("PG_DOCKER")

    # --- PostgreSQL restore into scratch DB ---
    base_url = s.database_admin_url or s.database_url
    restore_url = _plain(
        os.environ.get("RESTORE_DATABASE_URL") or base_url + "_restore")
    restore_db = restore_url.rsplit("/", 1)[-1]
    admin_base = _plain(base_url)
    if docker_c:
        user, _ = _url_parts(admin_base)
        subprocess.run(["docker", "exec", docker_c, "psql", "-U", user,
                        "-d", "postgres", "-c",
                        f"DROP DATABASE IF EXISTS {restore_db}"],
                       check=True, capture_output=True)
        subprocess.run(["docker", "exec", docker_c, "psql", "-U", user,
                        "-d", "postgres", "-c",
                        f"CREATE DATABASE {restore_db}"],
                       check=True, capture_output=True)
    else:
        maint = admin_base.rsplit("/", 1)[0] + "/postgres"
        subprocess.run(["psql", maint, "-c",
                        f"DROP DATABASE IF EXISTS {restore_db}"],
                       check=True, capture_output=True)
        subprocess.run(["psql", maint, "-c",
                        f"CREATE DATABASE {restore_db}"],
                       check=True, capture_output=True)
    _restore_db(restore_url, os.path.join(src, "db.dump"), docker_c)
    for table in ("patient", "rx", "asset", "alembic_version"):
        n = _psql(restore_url, f"SELECT count(*) FROM {table}", docker_c)
        print(f"restore db: {table} = {n}")

    # --- S3 restore into scratch bucket + hash verify ---
    s3 = _s3(s)
    rbucket = os.environ.get("RESTORE_S3_BUCKET", s.s3_bucket + "-restore")
    try:
        s3.head_bucket(Bucket=rbucket)
    except Exception:
        s3.create_bucket(Bucket=rbucket)
    verified = failed = 0
    for o in manifest["objects"]:
        srcpath = os.path.join(src, "objects", o["key"])
        with open(srcpath, "rb") as fh:
            body = fh.read()
        if hashlib.sha256(body).hexdigest() != o["sha256"]:
            failed += 1
            continue
        s3.put_object(Bucket=rbucket, Key=o["key"], Body=body)
        dl = s3.get_object(Bucket=rbucket, Key=o["key"])["Body"].read()
        if hashlib.sha256(dl).hexdigest() == o["sha256"]:
            verified += 1
        else:
            failed += 1
    print(f"restore s3: {verified} verified, {failed} failed "
          f"-> bucket {rbucket}")
    if failed:
        print("DRILL FAILED — object integrity mismatch")
        return 1
    print("restore drill ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
