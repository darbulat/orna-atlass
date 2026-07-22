import re
from functools import lru_cache
from ipaddress import ip_address, ip_network
from urllib.parse import unquote, urlsplit

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _private_key_identity(value: str) -> bytes | None:
    try:
        private_key = serialization.load_pem_private_key(value.encode(), password=None)
    except (TypeError, UnsupportedAlgorithm, ValueError):
        return None
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _is_p256_private_key(value: str) -> bool:
    try:
        key = serialization.load_pem_private_key(
            value.replace("\\n", "\n").encode(), password=None
        )
    except (TypeError, UnsupportedAlgorithm, ValueError):
        return False
    return isinstance(key, ec.EllipticCurvePrivateKey) and isinstance(
        key.curve, ec.SECP256R1
    )


_HOST_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def _is_valid_hostname(value: str) -> bool:
    try:
        ip_address(value)
        return True
    except ValueError:
        pass
    if len(value) > 253:
        return False
    labels = value.split(".")
    return bool(labels) and all(_HOST_LABEL.fullmatch(label) for label in labels)


def _is_valid_production_oauth_url(value: str) -> bool:
    decoded = unquote(value)
    if any(character.isspace() or ord(character) < 32 or ord(character) == 127 or character == "\\" for character in decoded):
        return False
    try:
        parsed = urlsplit(value)
        parsed.port
    except ValueError:
        return False
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and _is_valid_hostname(parsed.hostname)
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
    )


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
    trusted_proxy_cidrs: list[str] = Field(
        default_factory=list, validation_alias="TRUSTED_PROXY_CIDRS"
    )
    oauth_callback_base_url: str = Field(
        default="http://localhost:8000/api/v1/auth/oauth",
        validation_alias="OAUTH_CALLBACK_BASE_URL",
    )
    oauth_frontend_url: str = Field(
        default="http://localhost:3000/membership",
        validation_alias="OAUTH_FRONTEND_URL",
    )
    magic_link_callback_url: str = Field(
        default="http://localhost:8000/api/v1/auth/magic-link/consume",
        validation_alias="MAGIC_LINK_CALLBACK_URL",
    )
    smtp_host: str | None = Field(default=None, validation_alias="SMTP_HOST")
    smtp_port: int = Field(default=587, ge=1, le=65535, validation_alias="SMTP_PORT")
    smtp_username: str | None = Field(default=None, validation_alias="SMTP_USERNAME")
    smtp_password: str | None = Field(default=None, validation_alias="SMTP_PASSWORD")
    smtp_from_email: str | None = Field(default=None, validation_alias="SMTP_FROM_EMAIL")
    smtp_starttls: bool = Field(default=True, validation_alias="SMTP_STARTTLS")
    google_client_id: str | None = Field(default=None, validation_alias="GOOGLE_CLIENT_ID")
    google_client_secret: str | None = Field(default=None, validation_alias="GOOGLE_CLIENT_SECRET")
    apple_client_id: str | None = Field(default=None, validation_alias="APPLE_CLIENT_ID")
    apple_team_id: str | None = Field(default=None, validation_alias="APPLE_TEAM_ID")
    apple_key_id: str | None = Field(default=None, validation_alias="APPLE_KEY_ID")
    apple_private_key: str | None = Field(default=None, validation_alias="APPLE_PRIVATE_KEY")
    facebook_client_id: str | None = Field(default=None, validation_alias="FACEBOOK_CLIENT_ID")
    facebook_client_secret: str | None = Field(
        default=None, validation_alias="FACEBOOK_CLIENT_SECRET"
    )
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
        try:
            for cidr in self.trusted_proxy_cidrs:
                ip_network(cidr, strict=False)
        except ValueError as exc:
            raise ValueError("TRUSTED_PROXY_CIDRS must contain valid IP networks") from exc
        provider_fields = {
            "google": (self.google_client_id, self.google_client_secret),
            "apple": (
                self.apple_client_id,
                self.apple_team_id,
                self.apple_key_id,
                self.apple_private_key,
            ),
            "facebook": (self.facebook_client_id, self.facebook_client_secret),
        }
        provider_names = {
            "google": ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"),
            "apple": (
                "APPLE_CLIENT_ID",
                "APPLE_TEAM_ID",
                "APPLE_KEY_ID",
                "APPLE_PRIVATE_KEY",
            ),
            "facebook": ("FACEBOOK_CLIENT_ID", "FACEBOOK_CLIENT_SECRET"),
        }
        for provider, values in provider_fields.items():
            if any(values) and not all(values):
                missing = [
                    name for name, value in zip(provider_names[provider], values, strict=True) if not value
                ]
                raise ValueError(f"{', '.join(missing)} required when {provider} OAuth is configured")
        oauth_enabled = any(all(values) for values in provider_fields.values())
        if all(provider_fields["apple"]) and not _is_p256_private_key(
            self.apple_private_key or ""
        ):
            raise ValueError("APPLE_PRIVATE_KEY must be a valid P-256 EC private key")
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
        smtp_values = {
            "SMTP_HOST": self.smtp_host,
            "SMTP_FROM_EMAIL": self.smtp_from_email,
            "SMTP_USERNAME": self.smtp_username,
            "SMTP_PASSWORD": self.smtp_password,
        }
        for name, value in smtp_values.items():
            if value is not None and not value.strip():
                raise ValueError(f"{name} must not be blank")
        smtp_fields_present = any(value is not None for value in smtp_values.values())
        if smtp_fields_present and (not self.smtp_host or not self.smtp_from_email):
            raise ValueError("SMTP_HOST and SMTP_FROM_EMAIL must be configured together")
        if bool(self.smtp_username) != bool(self.smtp_password):
            raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must be configured together")
        if normalized_environment == "production":
            if smtp_fields_present:
                callback = urlsplit(self.magic_link_callback_url)
                expected_path = f"{self.api_prefix}/auth/magic-link/consume"
                if callback.scheme != "https" or not callback.netloc:
                    raise ValueError(
                        "MAGIC_LINK_CALLBACK_URL must be an absolute HTTPS URL in production"
                    )
                if callback.username is not None or callback.password is not None:
                    raise ValueError("MAGIC_LINK_CALLBACK_URL must not contain credentials")
                if not _is_valid_production_oauth_url(self.magic_link_callback_url):
                    raise ValueError(
                        "MAGIC_LINK_CALLBACK_URL must be a valid production HTTPS URL"
                    )
                if callback.query or callback.fragment:
                    raise ValueError("MAGIC_LINK_CALLBACK_URL must not contain query or fragment")
                if callback.path.rstrip("/") != expected_path:
                    raise ValueError(
                        f"MAGIC_LINK_CALLBACK_URL must use the callback path {expected_path}"
                    )
                if not self.smtp_starttls:
                    raise ValueError(
                        "SMTP_STARTTLS must be true for production magic-link delivery"
                    )
                if not _is_valid_production_oauth_url(self.oauth_frontend_url):
                    raise ValueError(
                        "OAUTH_FRONTEND_URL must be an absolute HTTPS URL without "
                        "credentials, query, or fragment in production"
                    )
            if oauth_enabled:
                if not _is_valid_production_oauth_url(self.oauth_callback_base_url):
                    raise ValueError(
                        "OAUTH_CALLBACK_BASE_URL must be an absolute HTTPS URL without credentials, query, or fragment"
                    )
                if not _is_valid_production_oauth_url(self.oauth_frontend_url):
                    raise ValueError(
                        "OAUTH_FRONTEND_URL must be an absolute HTTPS URL without credentials, query, or fragment"
                    )
            if self.auth_signing_algorithm == "RS256" and self.auth_private_key:
                hls_secrets = [
                    self.hls_token_secret,
                    *self.hls_token_previous_secrets.values(),
                ]
                private_key_identity = _private_key_identity(self.auth_private_key)
                if self.auth_private_key in hls_secrets or (
                    private_key_identity is not None
                    and any(
                        _private_key_identity(secret) == private_key_identity
                        for secret in hls_secrets
                    )
                ):
                    raise ValueError(
                        "HLS token secrets must be independent from the RS256 private key"
                    )
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
