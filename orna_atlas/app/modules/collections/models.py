from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from orna_atlas.app.db.base import Base


class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(220))
    description: Mapped[str | None] = mapped_column(Text)
    cover_asset_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    location_links = relationship(
        "CollectionLocation",
        back_populates="collection",
        cascade="all, delete-orphan",
        order_by="CollectionLocation.sort_order",
    )
    session_links = relationship(
        "CollectionSession",
        back_populates="collection",
        cascade="all, delete-orphan",
        order_by="CollectionSession.sort_order",
    )


class CollectionLocation(Base):
    __tablename__ = "collection_locations"
    __table_args__ = (UniqueConstraint("collection_id", "location_id", name="uq_collection_locations_pair"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    collection_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("collections.id", ondelete="CASCADE"), index=True
    )
    location_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("locations.id", ondelete="CASCADE"), index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    collection = relationship("Collection", back_populates="location_links")
    location = relationship("Location")


class CollectionSession(Base):
    __tablename__ = "collection_sessions"
    __table_args__ = (UniqueConstraint("collection_id", "session_id", name="uq_collection_sessions_pair"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    collection_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("collections.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("recording_sessions.id", ondelete="CASCADE"), index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    collection = relationship("Collection", back_populates="session_links")
    session = relationship("RecordingSession")
