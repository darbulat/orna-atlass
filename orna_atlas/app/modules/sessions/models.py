from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from orna_atlas.app.db.base import Base


class RecordingSession(Base):
    __tablename__ = "recording_sessions"

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
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    location = relationship("Location", back_populates="sessions")
    media_assets = relationship("MediaAsset", back_populates="session", cascade="all, delete-orphan")
