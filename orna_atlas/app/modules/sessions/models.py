from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from orna_atlas.app.db.base import Base


class RecordingSession(Base):
    __tablename__ = "recording_sessions"
    __table_args__ = (
        CheckConstraint("duration_seconds IS NULL OR duration_seconds >= 0", name="ck_sessions_duration"),
        CheckConstraint(
            "access_level IN ('public','members_only','draft','private')",
            name="ck_sessions_access_level",
        ),
        CheckConstraint(
            "processing_status IN ('pending','uploaded','queued','processing','ready','failed')",
            name="ck_sessions_processing_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    location_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("locations.id", ondelete="CASCADE"), index=True
    )
    slug: Mapped[str] = mapped_column(String(140), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(220), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    recorder: Mapped[str | None] = mapped_column(String(160))
    weather: Mapped[str | None] = mapped_column(String(240))
    access_level: Mapped[str] = mapped_column(String(40), default="public", index=True)
    processing_status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    featured_sort_order: Mapped[int | None] = mapped_column(Integer)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    location = relationship("Location", back_populates="sessions")
    media_assets = relationship("MediaAsset", back_populates="session", cascade="all, delete-orphan")
    bird_vocal_parts = relationship(
        "BirdVocalPart", back_populates="session", cascade="all, delete-orphan", order_by="BirdVocalPart.starts_at_seconds"
    )


class BirdVocalPart(Base):
    __tablename__ = "bird_vocal_parts"
    __table_args__ = (
        CheckConstraint("starts_at_seconds >= 0", name="ck_bird_parts_start"),
        CheckConstraint("ends_at_seconds >= starts_at_seconds", name="ck_bird_parts_interval"),
        CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 1", name="ck_bird_parts_confidence"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("recording_sessions.id", ondelete="CASCADE"), index=True
    )
    species_code: Mapped[str] = mapped_column(String(120), index=True)
    species_common_name: Mapped[str] = mapped_column(String(180))
    species_scientific_name: Mapped[str | None] = mapped_column(String(180))
    starts_at_seconds: Mapped[float] = mapped_column(Float)
    ends_at_seconds: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    channel: Mapped[str | None] = mapped_column(String(40))
    call_type: Mapped[str] = mapped_column(String(40), default="unknown")
    analysis_provider: Mapped[str | None] = mapped_column(String(120))
    analysis_model_version: Mapped[str | None] = mapped_column(String(80))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    session = relationship("RecordingSession", back_populates="bird_vocal_parts")
