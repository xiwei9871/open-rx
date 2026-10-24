"""Password hashing + opaque session tokens + permission map.

Permission map is PROVISIONAL (permission-matrix.md): only platform-level
capabilities needed by B0 tasks are granted. Clinical-role capabilities stay
out until V1.1 verifies them — do NOT silently promote.
"""
import hashlib
import secrets

from pwdlib import PasswordHash

_pwd = PasswordHash.recommended()  # argon2id


def hash_password(pw: str) -> str:
    return _pwd.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    return _pwd.verify(pw, hashed)


def new_session_token() -> tuple[str, str]:
    """Return (raw_token, sha256_hex). Only the hash is persisted."""
    raw = secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# PROVISIONAL — platform-level only. Clinical capabilities (rx/patient/asset
# writes) intentionally absent until V1.1 role verification (V-03).
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "practice_admin": frozenset({
        "org:manage", "location:write", "member:write", "roster:write",
        "connection:write", "audit:read",
    }),
    "practice_doctor": frozenset({"roster:read"}),
    "practice_staff": frozenset({"roster:read"}),
    "lab_admin": frozenset({
        "org:manage", "location:write", "member:write",
        "connection:write", "audit:read",
    }),
    "lab_technician": frozenset(),
}
