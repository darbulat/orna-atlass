from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from orna_atlas.app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    role: Mapped[str] = mapped_column(
        String(32), default="member", nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    oauth_identities = relationship(
        "OAuthIdentity", back_populates="user", cascade="all, delete-orphan"
    )
    membership = relationship(
        "Membership", back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    audit_events = relationship("AuditEvent", back_populates="actor")
