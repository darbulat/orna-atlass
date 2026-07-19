import re
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
    audio_job_timeout_seconds: int = Field(default=600, ge=60, validation_alias="AUDIO_JOB_TIMEOUT_SECONDS")
    audio_job_timeout_per_hour_seconds: int = Field(
        default=3600,
        ge=60,
        validation_alias="AUDIO_JOB_TIMEOUT_PER_HOUR_SECONDS",
    )
    audio_job_max_timeout_seconds: int = Field(
        default=21600,
        ge=60,
        validation_alias="AUDIO_JOB_MAX_TIMEOUT_SECONDS",
    )
    audio_job_max_retries: int = Field(
        default=2,
        ge=0,
        le=10,
        validation_alias="AUDIO_JOB_MAX_RETRIES",
    )
    audio_job_retry_interval_seconds: int = Field(
        default=60,
        ge=1,
        validation_alias="AUDIO_JOB_RETRY_INTERVAL_SECONDS",
    )
    pipeline_stale_after_seconds: int = Field(
        default=25200,
        ge=300,
        validation_alias="PIPELINE_STALE_AFTER_SECONDS",
    )
    worker_metrics_port: int = Field(
        default=9101,
        ge=1024,
        le=65535,
        validation_alias="WORKER_METRICS_PORT",
    )
    audio_job_result_ttl_seconds: int = Field(
        default=3600, ge=60, validation_alias="AUDIO_JOB_RESULT_TTL_SECONDS"
    )
    media_retention_days: int = Field(
        default=30, ge=0, validation_alias="MEDIA_RETENTION_DAYS"
    )
    environment: str = Field(default="development", validation_alias="APP_ENVIRONMENT")
    auth_secret_key: str = Field(
        default="development-only-change-me-32-bytes",
        validation_alias="AUTH_SECRET_KEY",
    )
    auth_signing_algorithm: str = Field(default="HS256", validation_alias="AUTH_SIGNING_ALGORITHM")
    auth_key_id: str = Field(default="orna-primary", validation_alias="AUTH_KEY_ID")
    auth_private_key: str | None = Field(default=None, validation_alias="AUTH_PRIVATE_KEY")
    auth_jwks_json: str | None = Field(default=None, validation_alias="AUTH_JWKS_JSON")
    hls_token_secret: str = Field(
        default="development-only-hls-token-secret-32-bytes",
        validation_alias="HLS_TOKEN_SECRET",
    )
    hls_token_key_id: str = Field(default="primary", validation_alias="HLS_TOKEN_KEY_ID")
    hls_token_previous_secrets: dict[str, str] = Field(
        default_factory=dict,
        validation_alias="HLS_TOKEN_PREVIOUS_SECRETS",
    )
    access_token_ttl_seconds: int = Field(
        default=900, ge=60, validation_alias="ACCESS_TOKEN_TTL_SECONDS"
    )
    refresh_token_ttl_days: int = Field(default=30, ge=1, validation_alias="REFRESH_TOKEN_TTL_DAYS")
    auth_cookie_secure: bool = Field(default=False, validation_alias="AUTH_COOKIE_SECURE")
    local_admin_enabled: bool = Field(default=False, validation_alias="LOCAL_ADMIN_ENABLED")
    auth_rate_limit: int = Field(default=10, ge=1, validation_alias="AUTH_RATE_LIMIT")
    search_rate_limit: int = Field(default=60, ge=1, validation_alias="SEARCH_RATE_LIMIT")
    playback_rate_limit: int = Field(default=30, ge=1, validation_alias="PLAYBACK_RATE_LIMIT")
    rate_limit_window_seconds: int = Field(
        default=60, ge=1, validation_alias="RATE_LIMIT_WINDOW_SECONDS"
    )

    @model_validator(mode="after")
    def reject_insecure_production_auth(self) -> "Settings":
        normalized_environment = self.environment.lower()
        if self.auth_signing_algorithm not in {"HS256", "RS256"}:
            raise ValueError("AUTH_SIGNING_ALGORITHM must be HS256 or RS256")
        if self.auth_signing_algorithm == "RS256" and not self.auth_private_key:
            raise ValueError("AUTH_PRIVATE_KEY is required for RS256 signing")
        if re.fullmatch(r"[A-Za-z0-9_-]+", self.hls_token_key_id) is None:
            raise ValueError(
                "HLS_TOKEN_KEY_ID must use only URL-safe letters, digits, underscores, or hyphens"
            )
        if self.hls_token_key_id in self.hls_token_previous_secrets:
            raise ValueError("HLS_TOKEN_KEY_ID must not also be configured as a previous key")
        if any(
            re.fullmatch(r"[A-Za-z0-9_-]+", key_id) is None
            for key_id in self.hls_token_previous_secrets
        ):
            raise ValueError(
                "HLS_TOKEN_PREVIOUS_SECRETS key ids must use only URL-safe letters, digits, underscores, or hyphens"
            )
        if self.audio_job_max_timeout_seconds < self.audio_job_timeout_seconds:
            raise ValueError(
                "AUDIO_JOB_MAX_TIMEOUT_SECONDS must be at least AUDIO_JOB_TIMEOUT_SECONDS"
            )
        if self.pipeline_stale_after_seconds <= self.audio_job_max_timeout_seconds:
            raise ValueError(
                "PIPELINE_STALE_AFTER_SECONDS must exceed AUDIO_JOB_MAX_TIMEOUT_SECONDS"
            )
        if self.local_admin_enabled and normalized_environment not in {"development", "local"}:
            raise ValueError(
                "LOCAL_ADMIN_ENABLED may only be true in development or local environments"
            )
        if normalized_environment == "production":
            if self.hls_token_secret == self.auth_secret_key:
                raise ValueError("HLS_TOKEN_SECRET must be independent from AUTH_SECRET_KEY")
            if (
                self.hls_token_secret == "development-only-hls-token-secret-32-bytes"
                or len(self.hls_token_secret) < 32
            ):
                raise ValueError("HLS_TOKEN_SECRET must contain at least 32 characters in production")
            if any(
                secret == self.auth_secret_key
                for secret in self.hls_token_previous_secrets.values()
            ):
                raise ValueError(
                    "HLS_TOKEN_PREVIOUS_SECRETS must be independent from AUTH_SECRET_KEY"
                )
            if (
                "development-only-hls-token-secret-32-bytes"
                in self.hls_token_previous_secrets.values()
            ):
                raise ValueError(
                    "HLS_TOKEN_PREVIOUS_SECRETS must not contain the development default"
                )
            if any(len(secret) < 32 for secret in self.hls_token_previous_secrets.values()):
                raise ValueError(
                    "HLS_TOKEN_PREVIOUS_SECRETS values must contain at least 32 characters in production"
                )
            if (
                self.auth_signing_algorithm == "HS256"
                and (
                    self.auth_secret_key == "development-only-change-me-32-bytes"
                    or len(self.auth_secret_key) < 32
                )
            ):
                raise ValueError("AUTH_SECRET_KEY must contain at least 32 characters in production")
            if not self.auth_cookie_secure:
                raise ValueError("AUTH_COOKIE_SECURE must be true in production")
        return self

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
