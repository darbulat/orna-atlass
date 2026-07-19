from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from orna_atlas.app.core.domain_types import JobStatus, JobType, MediaKind, ProcessingStatus
from orna_atlas.app.core.schema_validation import reject_required_nulls


class MediaAssetCreate(BaseModel):
    kind: MediaKind = MediaKind.SOURCE_AUDIO
    storage_key: str = Field(min_length=1, max_length=512)
    mime_type: str = Field(default="audio/wav", max_length=120)
    duration_seconds: int | None = Field(default=None, ge=0)
    size_bytes: int | None = Field(default=None, ge=0)
    checksum: str | None = Field(default=None, max_length=128)
    metadata: dict = Field(default_factory=dict)
    enqueue_processing: bool = True


class MediaAssetUpdate(BaseModel):
    kind: MediaKind | None = None
    storage_key: str | None = Field(default=None, min_length=1, max_length=512)
    mime_type: str | None = Field(default=None, max_length=120)
    processing_status: ProcessingStatus | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    size_bytes: int | None = Field(default=None, ge=0)
    checksum: str | None = Field(default=None, max_length=128)
    metadata: dict | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_required_nulls(cls, data: object) -> object:
        if isinstance(data, dict):
            return reject_required_nulls(data, {"kind", "storage_key", "mime_type", "metadata"})
        return data


class ProcessingJobRead(BaseModel):
    id: UUID
    asset_id: UUID
    job_type: JobType
    status: JobStatus
    attempt_count: int
    stage_states: dict = Field(default_factory=dict)
    request_id: str | None = None
    queue_job_id: str | None = None
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    heartbeat_at: datetime | None = None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MediaAssetRead(BaseModel):
    id: UUID
    session_id: UUID
    kind: MediaKind
    mime_type: str
    processing_status: ProcessingStatus = ProcessingStatus.UPLOADED
    duration_seconds: int | None
    size_bytes: int | None
    checksum: str | None
    revision: int = Field(default=1, ge=1)
    is_active: bool = True
    archived_at: datetime | None = None
    source_asset_id: UUID | None = None
    metadata: dict = Field(validation_alias="metadata_")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PublicMediaAssetRead(BaseModel):
    """Public playback projection without storage or pipeline internals."""

    id: UUID
    session_id: UUID
    kind: MediaKind
    mime_type: str
    processing_status: ProcessingStatus = ProcessingStatus.UPLOADED
    duration_seconds: int | None
    revision: int = Field(default=1, ge=1)
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)


class AdminMediaAssetRead(MediaAssetRead):
    storage_key: str
    processing_jobs: list[ProcessingJobRead] = Field(default_factory=list)


class ProcessingStatusRead(BaseModel):
    session_id: UUID
    processing_status: ProcessingStatus
    media_assets: list[AdminMediaAssetRead]
    latest_job: ProcessingJobRead | None = None


class RecordingSegmentCreate(BaseModel):
    sequence_number: int = Field(ge=1)
    storage_key: str = Field(min_length=1, max_length=512)
    checksum: str | None = Field(default=None, max_length=128)


class RecordingSegmentBatchCreate(BaseModel):
    segments: list[RecordingSegmentCreate] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_contiguous_sequence(self) -> "RecordingSegmentBatchCreate":
        sequence = [item.sequence_number for item in self.segments]
        if sequence != list(range(1, len(sequence) + 1)):
            raise ValueError("Segment sequence numbers must be contiguous and ordered from 1")
        if len({item.storage_key for item in self.segments}) != len(self.segments):
            raise ValueError("Segment storage keys must be unique")
        return self


class RecordingSegmentRead(BaseModel):
    id: UUID
    sequence_number: int
    start_offset_ms: int | None
    duration_ms: int | None
    source_asset_id: UUID

    model_config = ConfigDict(from_attributes=True)
