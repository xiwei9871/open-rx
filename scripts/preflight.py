#!/usr/bin/env python3
"""SAFE-010 environment preflight — run before deploy/upgrade.

Fails (exit 1) on:
  - prod env with any dev-default secret/URL (delegates to Settings
    validators, which already refuse to boot)
  - missing TOTP_ENCRYPTION_KEY in prod
  - HTTP (non-TLS) endpoints for S3/CORS in prod
Warns on weak session secret length, dev bucket names.
Prints a redacted summary — values are never echoed.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))


def main() -> int:
    from app.config import Settings
    env = os.environ.get("ENV", "dev")
    try:
        s = Settings()
    except Exception as e:  # pydantic validation already lists every issue
        print(f"PREFLIGHT FAIL — settings invalid:\n{e}")
        return 1

    problems, warns = [], []
    if len(s.session_secret) < 32:
        warns.append("SESSION_SECRET under 32 chars")
    if "dev" in s.s3_bucket:
        warns.append(f"S3_BUCKET looks like a dev name ({s.s3_bucket!r})")
    if env == "prod":
        for url, name in ((s.s3_endpoint_url, "S3_ENDPOINT_URL"),):
            if url.startswith("http://"):
                problems.append(f"{name} is not TLS")
        for o in s.cors_origin_list:
            if o.startswith("http://") or o == "*":
                problems.append(f"CORS origin {o!r} is not HTTPS")
        if not s.totp_encryption_key:
            problems.append("TOTP_ENCRYPTION_KEY missing")
        if s.database_admin_url and "localhost" in s.database_admin_url:
            warns.append("DATABASE_ADMIN_URL points at localhost")

    for w in warns:
        print(f"  warn: {w}")
    if problems:
        for p_ in problems:
            print(f"  FAIL: {p_}")
        print(f"preflight: {len(problems)} problem(s)")
        return 1
    print(f"preflight ok: env={env} bucket={s.s3_bucket} "
          f"av={s.asset_av_engine}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
