from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ORNA Atlas API"
    api_prefix: str = "/api/v1"
    database_url: str = Field(
        default="postgresql+asyncpg://orna:orna@localhost:5432/orna_atlas",
        validation_alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    s3_endpoint_url: str | None = Field(default=None, validation_alias="S3_ENDPOINT_URL")
    s3_public_endpoint_url: str | None = Field(default=None, validation_alias="S3_PUBLIC_ENDPOINT_URL")
    s3_region: str = Field(default="us-east-1", validation_alias="S3_REGION")
    s3_private_bucket: str = Field(default="orna-audio-private", validation_alias="S3_PRIVATE_BUCKET")
    s3_public_bucket: str = Field(default="orna-media-public", validation_alias="S3_PUBLIC_BUCKET")
    s3_access_key_id: str | None = Field(default=None, validation_alias="S3_ACCESS_KEY_ID")
    s3_secret_access_key: str | None = Field(default=None, validation_alias="S3_SECRET_ACCESS_KEY")
    s3_presign_expires_seconds: int = Field(default=900, validation_alias="S3_PRESIGN_EXPIRES_SECONDS")
    environment: str = Field(default="development", validation_alias="APP_ENVIRONMENT")
    auth_secret_key: str = Field(default="development-only-change-me", validation_alias="AUTH_SECRET_KEY")
    access_token_ttl_seconds: int = Field(
        default=900, ge=60, validation_alias="ACCESS_TOKEN_TTL_SECONDS"
    )
    refresh_token_ttl_days: int = Field(default=30, ge=1, validation_alias="REFRESH_TOKEN_TTL_DAYS")
    auth_cookie_secure: bool = Field(default=False, validation_alias="AUTH_COOKIE_SECURE")
    local_admin_enabled: bool = Field(default=True, validation_alias="LOCAL_ADMIN_ENABLED")
    auth_rate_limit: int = Field(default=10, ge=1, validation_alias="AUTH_RATE_LIMIT")
    search_rate_limit: int = Field(default=60, ge=1, validation_alias="SEARCH_RATE_LIMIT")
    playback_rate_limit: int = Field(default=30, ge=1, validation_alias="PLAYBACK_RATE_LIMIT")
    rate_limit_window_seconds: int = Field(
        default=60, ge=1, validation_alias="RATE_LIMIT_WINDOW_SECONDS"
    )

    @model_validator(mode="after")
    def reject_insecure_production_auth(self) -> "Settings":
        if self.environment.lower() == "production":
            if self.auth_secret_key == "development-only-change-me" or len(self.auth_secret_key) < 32:
                raise ValueError("AUTH_SECRET_KEY must contain at least 32 characters in production")
            if self.local_admin_enabled:
                raise ValueError("LOCAL_ADMIN_ENABLED must be false in production")
            if not self.auth_cookie_secure:
                raise ValueError("AUTH_COOKIE_SECURE must be true in production")
        return self

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
