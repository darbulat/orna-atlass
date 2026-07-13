from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from orna_atlas.app.db.base import Base

_SENSITIVE_LEVELS = frozenset({"protected", "high", "medium"})


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (
        CheckConstraint("exact_latitude BETWEEN -90 AND 90", name="ck_locations_exact_latitude"),
        CheckConstraint("exact_longitude BETWEEN -180 AND 180", name="ck_locations_exact_longitude"),
        CheckConstraint(
            "(public_latitude IS NULL) = (public_longitude IS NULL)",
            name="ck_locations_public_coordinate_pair",
        ),
        CheckConstraint(
            "public_latitude IS NULL OR public_latitude BETWEEN -90 AND 90",
            name="ck_locations_public_latitude",
        ),
        CheckConstraint(
            "public_longitude IS NULL OR public_longitude BETWEEN -180 AND 180",
            name="ck_locations_public_longitude",
        ),
        CheckConstraint(
            "coordinate_visibility IN ('exact_public','approximate_public','hidden_public')",
            name="ck_locations_coordinate_visibility",
        ),
        CheckConstraint(
            "sensitivity_level IN ('none','low','medium','high','protected')",
            name="ck_locations_sensitivity_level",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(180), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    country_code: Mapped[str | None] = mapped_column(String(2), index=True)
    region: Mapped[str | None] = mapped_column(String(120))
    habitat: Mapped[str | None] = mapped_column(String(120), index=True)
    exact_latitude: Mapped[float] = mapped_column(Float)
    exact_longitude: Mapped[float] = mapped_column(Float)
    public_latitude: Mapped[float | None] = mapped_column(Float)
    public_longitude: Mapped[float | None] = mapped_column(Float)
    coordinate_visibility: Mapped[str] = mapped_column(String(40), default="exact_public", index=True)
    sensitivity_level: Mapped[str] = mapped_column(String(40), default="none", index=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    sessions = relationship("RecordingSession", back_populates="location", cascade="all, delete-orphan")

    @property
    def coordinates_protected(self) -> bool:
        return self.coordinate_visibility != "exact_public" or self.sensitivity_level in _SENSITIVE_LEVELS

    @property
    def latitude(self) -> float | None:
        if self.coordinate_visibility == "hidden_public":
            return None
        if self.coordinate_visibility == "exact_public" and self.sensitivity_level not in _SENSITIVE_LEVELS:
            return self.exact_latitude
        return self.public_latitude

    @property
    def longitude(self) -> float | None:
        if self.coordinate_visibility == "hidden_public":
            return None
        if self.coordinate_visibility == "exact_public" and self.sensitivity_level not in _SENSITIVE_LEVELS:
            return self.exact_longitude
        return self.public_longitude
