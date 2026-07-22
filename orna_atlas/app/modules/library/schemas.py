from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LibraryLocationSummary(BaseModel):
    id: UUID
    slug: str
    name: str
    region: str | None = None
    habitat: str | None = None

    model_config = ConfigDict(from_attributes=True)


class LibrarySessionSummary(BaseModel):
    id: UUID
    slug: str
    title: str
    recorded_at: datetime
    duration_seconds: int | None = Field(default=None, ge=0)
    access_level: str
    location: LibraryLocationSummary

    model_config = ConfigDict(from_attributes=True)


class FavoriteRead(BaseModel):
    session: LibrarySessionSummary
    favorited_at: datetime


class ListeningProgressUpdate(BaseModel):
    position_seconds: float = Field(ge=0)
    completed: bool = False

    model_config = ConfigDict(allow_inf_nan=False)


class ListeningHistoryRead(BaseModel):
    session: LibrarySessionSummary
    first_listened_at: datetime
    last_listened_at: datetime
    last_position_seconds: float = Field(ge=0)
    completed_at: datetime | None = None
