from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from orna_atlas.app.db.base import Base


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('audio','source_audio','master_audio','streaming_rendition','audio_stream')",
            name="ck_media_assets_kind",
        ),
        CheckConstraint(
            "processing_status IN ('pending','uploaded','queued','processing','ready','failed')",
            name="ck_media_assets_processing_status",
        ),
        CheckConstraint("duration_seconds IS NULL OR duration_seconds >= 0", name="ck_media_assets_duration"),
        CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="ck_media_assets_size"),
        CheckConstraint("revision > 0", name="ck_media_assets_revision"),
        Index(
            "uq_media_assets_active_source",
            "session_id",
            unique=True,
            postgresql_where=text(
                "kind IN ('audio', 'source_audio', 'master_audio') "
                "AND is_active AND archived_at IS NULL "
                "AND NOT (metadata ? 'recording_segment')"
            ),
        ),
        Index(
            "uq_media_assets_active_rendition",
            "session_id",
            unique=True,
            postgresql_where=text(
                "is_active AND archived_at IS NULL AND kind = 'streaming_rendition'"
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("recording_sessions.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(40), default="audio")
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    mime_type: Mapped[str] = mapped_column(String(120), default="audio/wav")
    processing_status: Mapped[str] = mapped_column(String(40), default="uploaded", index=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    checksum: Mapped[str | None] = mapped_column(String(128))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    storage_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_asset_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="SET NULL"), index=True
    )
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    session = relationship("RecordingSession", back_populates="media_assets")
    processing_jobs = relationship("ProcessingJob", back_populates="asset", cascade="all, delete-orphan")


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        CheckConstraint("job_type IN ('audio_pipeline')", name="ck_processing_jobs_type"),
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed')",
            name="ck_processing_jobs_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_processing_jobs_attempt_count"),
        Index(
            "uq_processing_jobs_active_asset_type",
            "asset_id",
            "job_type",
            unique=True,
            postgresql_where=text("status IN ('queued','running')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    asset_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="CASCADE"), index=True
    )
    job_type: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    stage_states: Mapped[dict] = mapped_column(JSONB, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(128), index=True)
    queue_job_id: Mapped[str | None] = mapped_column(String(255), index=True)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    asset = relationship("MediaAsset", back_populates="processing_jobs")


class StorageCleanupJob(Base):
    """Durable, retry-safe deletion request for an archived object-storage key."""

    __tablename__ = "storage_cleanup_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','succeeded','failed')",
            name="ck_storage_cleanup_jobs_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_storage_cleanup_jobs_attempt_count"),
        UniqueConstraint("asset_id", name="uq_storage_cleanup_jobs_asset_id"),
        UniqueConstraint("storage_key", name="uq_storage_cleanup_jobs_storage_key"),
        Index("ix_storage_cleanup_jobs_due", "status", "next_attempt_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    asset_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("media_assets.id", ondelete="SET NULL"),
        index=True,
    )
    storage_key: Mapped[str] = mapped_column(String(512))
    object_keys: Mapped[list[str] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    retain_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    asset = relationship("MediaAsset")


class RecordingSegment(Base):
    __tablename__ = "recording_segments"
    __table_args__ = (
        CheckConstraint("sequence_number > 0", name="ck_recording_segments_sequence"),
        CheckConstraint(
            "processing_status IN ('pending','processing','ready','failed')",
            name="ck_recording_segments_processing_status",
        ),
        CheckConstraint("start_offset_ms IS NULL OR start_offset_ms >= 0", name="ck_recording_segments_offset"),
        CheckConstraint("duration_ms IS NULL OR duration_ms > 0", name="ck_recording_segments_duration"),
        UniqueConstraint("session_id", "sequence_number", name="uq_recording_segments_sequence"),
        UniqueConstraint("source_asset_id", name="uq_recording_segments_source_asset"),
    )
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("recording_sessions.id", ondelete="CASCADE"), index=True)
    source_asset_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="RESTRICT"), index=True)
    sequence_number: Mapped[int] = mapped_column(Integer)
    processing_status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    processing_attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    processing_error_code: Mapped[str | None] = mapped_column(String(80))
    processing_error_message: Mapped[str | None] = mapped_column(Text)
    start_offset_ms: Mapped[int | None] = mapped_column(BigInteger)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    session = relationship("RecordingSession", back_populates="recording_segments")
    source_asset = relationship("MediaAsset")


class HlsProcessingJob(Base):
    __tablename__ = "hls_processing_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('queued','running','succeeded','failed')", name="ck_hls_jobs_status"),
        CheckConstraint("attempt_count >= 0", name="ck_hls_jobs_attempt_count"),
        Index("uq_hls_jobs_active_source_set", "session_id", "source_fingerprint", unique=True, postgresql_where=text("status IN ('queued','running')")),
    )
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("recording_sessions.id", ondelete="CASCADE"), index=True)
    source_fingerprint: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    stage_states: Mapped[dict] = mapped_column(JSONB, default=dict)
    queue_job_id: Mapped[str | None] = mapped_column(String(255), index=True)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    session = relationship("RecordingSession", back_populates="hls_processing_jobs")
