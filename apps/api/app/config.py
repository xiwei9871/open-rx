from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_DEFAULTS = {
    "session_secret": "dev_session_secret_change_me_32bytes!!",
    "database_admin_url": "postgresql+asyncpg://easyrs_admin:dev_admin_pw_change_me@localhost:5432/easyrs",
    "database_url": "postgresql+asyncpg://easyrs_app:dev_app_pw_change_me@localhost:5432/easyrs",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    database_url: str = _DEV_DEFAULTS["database_url"]
    # Optional at runtime: only migrate/seed jobs need the RLS-exempt role.
    database_admin_url: str | None = _DEV_DEFAULTS["database_admin_url"]
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "easyrs_dev"
    s3_secret_key: str = "dev_minio_pw_change_me"
    s3_bucket: str = "easyrs-assets-dev"
    session_secret: str = _DEV_DEFAULTS["session_secret"]
    # base64 Fernet key; REQUIRED in prod (else derived from session_secret)
    totp_encryption_key: str | None = None
    cors_origins: str = "http://localhost:5173"

    session_ttl_seconds: int = 60 * 60 * 12
    challenge_ttl_seconds: int = 300
    challenge_max_attempts: int = 5
    password_min_length: int = 10
    # rate limits (count, window seconds): login per email / ip, pw changes
    rl_login_email_limit: int = 8
    rl_login_email_window: int = 300
    rl_login_ip_limit: int = 40
    rl_login_ip_window: int = 300
    rl_password_limit: int = 5
    rl_password_window: int = 900

    @model_validator(mode="after")
    def _prod_guards(self) -> "Settings":
        """Fail closed: prod must not boot with dev defaults or missing keys."""
        if self.env != "prod":
            return self
        problems = []
        for field, default in _DEV_DEFAULTS.items():
            if getattr(self, field) == default:
                problems.append(f"{field.upper()} still set to dev default")
        for field in ("totp_encryption_key",):
            if not getattr(self, field):
                problems.append(f"{field.upper()} is required in prod")
        if "dev_" in self.s3_secret_key or "dev_" in self.s3_access_key:
            problems.append("S3 credentials still set to dev defaults")
        if problems:
            raise ValueError("prod configuration refused: " + "; ".join(problems))
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
