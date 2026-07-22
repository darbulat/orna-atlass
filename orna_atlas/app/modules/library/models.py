from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from orna_atlas.app.db.base import Base


class UserFavorite(Base):
    __tablename__ = "user_favorites"
    __table_args__ = (
        Index("ix_user_favorites_user_created_at", "user_id", "created_at", "session_id"),
        Index("ix_user_favorites_session_id", "session_id"),
    )

    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("recording_sessions.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)

    recording_session = relationship("RecordingSession")


class ListeningHistory(Base):
    __tablename__ = "listening_history"
    __table_args__ = (
        CheckConstraint("last_position_seconds >= 0", name="ck_listening_history_position"),
        Index("ix_listening_history_user_last_listened_at", "user_id", "last_listened_at", "session_id"),
        Index("ix_listening_history_session_id", "session_id"),
    )

    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("recording_sessions.id", ondelete="CASCADE"), primary_key=True)
    first_listened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_listened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_position_seconds: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    recording_session = relationship("RecordingSession")
