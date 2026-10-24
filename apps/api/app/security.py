"""Password hashing + opaque session tokens + permission map.

Permission map is PROVISIONAL (permission-matrix.md): only platform-level
capabilities needed by B0 tasks are granted. Clinical-role capabilities stay
out until V1.1 verifies them — do NOT silently promote.
"""
import base64
import hashlib
import secrets

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
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


def _totp_fernet() -> Fernet:
    """Encryption for TOTP seeds at rest.

    Key source: explicit TOTP_ENCRYPTION_KEY (required in prod), else HKDF
    derived from SESSION_SECRET (dev/test convenience — still a controlled
    key boundary; rotating the key invalidates enrolled seeds).
    """
    from app.config import get_settings
    s = get_settings()
    if s.totp_encryption_key:
        return Fernet(s.totp_encryption_key.encode())
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
               info=b"easyrs-totp").derive(s.session_secret.encode())
    return Fernet(base64.urlsafe_b64encode(key))


def enc_totp(secret: str) -> bytes:
    return _totp_fernet().encrypt(secret.encode())


def dec_totp(enc: bytes) -> str:
    return _totp_fernet().decrypt(enc).decode()


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
