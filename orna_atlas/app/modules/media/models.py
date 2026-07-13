from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
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
                "is_active AND archived_at IS NULL "
                "AND kind IN ('audio','source_audio','master_audio')"
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
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    asset = relationship("MediaAsset", back_populates="processing_jobs")
