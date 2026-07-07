from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ORNA Atlas API"
    api_prefix: str = "/api/v1"
    database_url: str = Field(
        default="postgresql+asyncpg://orna:orna@localhost:5432/orna_atlas",
        validation_alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    cors_origins: list[str] = ["http://localhost:3000"]
    s3_endpoint_url: str | None = Field(default=None, validation_alias="S3_ENDPOINT_URL")
    s3_region: str = Field(default="us-east-1", validation_alias="S3_REGION")
    s3_private_bucket: str = Field(default="orna-audio-private", validation_alias="S3_PRIVATE_BUCKET")
    s3_public_bucket: str = Field(default="orna-media-public", validation_alias="S3_PUBLIC_BUCKET")
    s3_access_key_id: str | None = Field(default=None, validation_alias="S3_ACCESS_KEY_ID")
    s3_secret_access_key: str | None = Field(default=None, validation_alias="S3_SECRET_ACCESS_KEY")
    s3_presign_expires_seconds: int = Field(default=900, validation_alias="S3_PRESIGN_EXPIRES_SECONDS")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
