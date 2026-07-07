from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _reject_required_nulls(data: dict, fields: set[str]) -> dict:
    null_fields = sorted(field for field in fields if field in data and data[field] is None)
    if null_fields:
        joined = ", ".join(null_fields)
        raise ValueError(f"Fields may be omitted but cannot be null: {joined}")
    return data


class MediaAssetCreate(BaseModel):
    kind: str = Field(default="source_audio", max_length=40)
    storage_key: str = Field(min_length=1, max_length=512)
    mime_type: str = Field(default="audio/wav", max_length=120)
    duration_seconds: int | None = Field(default=None, ge=0)
    size_bytes: int | None = Field(default=None, ge=0)
    checksum: str | None = Field(default=None, max_length=128)
    metadata: dict = Field(default_factory=dict)
    enqueue_processing: bool = True


class MediaAssetUpdate(BaseModel):
    kind: str | None = Field(default=None, max_length=40)
    storage_key: str | None = Field(default=None, min_length=1, max_length=512)
    mime_type: str | None = Field(default=None, max_length=120)
    processing_status: str | None = Field(default=None, max_length=40)
    duration_seconds: int | None = Field(default=None, ge=0)
    size_bytes: int | None = Field(default=None, ge=0)
    checksum: str | None = Field(default=None, max_length=128)
    metadata: dict | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_required_nulls(cls, data: object) -> object:
        if isinstance(data, dict):
            return _reject_required_nulls(data, {"kind", "storage_key", "mime_type", "metadata"})
        return data


class ProcessingJobRead(BaseModel):
    id: UUID
    asset_id: UUID
    job_type: str
    status: str
    attempt_count: int
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MediaAssetRead(BaseModel):
    id: UUID
    session_id: UUID
    kind: str
    mime_type: str
    processing_status: str = "uploaded"
    duration_seconds: int | None
    size_bytes: int | None
    checksum: str | None
    metadata: dict = Field(validation_alias="metadata_")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AdminMediaAssetRead(MediaAssetRead):
    storage_key: str
    processing_jobs: list[ProcessingJobRead] = Field(default_factory=list)


class ProcessingStatusRead(BaseModel):
    session_id: UUID
    processing_status: str
    media_assets: list[AdminMediaAssetRead]
    latest_job: ProcessingJobRead | None = None
