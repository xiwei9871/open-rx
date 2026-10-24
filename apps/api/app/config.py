from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    database_url: str = "postgresql+asyncpg://easyrs_app:dev_app_pw_change_me@localhost:5432/easyrs"
    database_admin_url: str = "postgresql+asyncpg://easyrs_admin:dev_admin_pw_change_me@localhost:5432/easyrs"
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "easyrs_dev"
    s3_secret_key: str = "dev_minio_pw_change_me"
    s3_bucket: str = "easyrs-assets-dev"
    session_secret: str = "dev_session_secret_change_me_32bytes!!"
    cors_origins: str = "http://localhost:5173"

    session_ttl_seconds: int = 60 * 60 * 12
    challenge_ttl_seconds: int = 300
    password_min_length: int = 10

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
