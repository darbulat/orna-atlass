from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AtlasSessionSummary(BaseModel):
    id: UUID
    slug: str
    title: str
    recorded_at: datetime
    duration_seconds: int | None = None


class AtlasPoint(BaseModel):
    type: Literal["point"] = "point"
    id: UUID
    slug: str
    name: str
    description: str | None = None
    country_code: str | None = None
    region: str | None = None
    habitat: str | None = None
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timezone: str
    sensitivity_level: str
    session_count: int = Field(ge=0)
    latest_session: AtlasSessionSummary | None = None


class AtlasCluster(BaseModel):
    type: Literal["cluster"] = "cluster"
    id: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    count: int = Field(ge=1)
    habitats: list[str] = Field(default_factory=list)


class AtlasPointsResponse(BaseModel):
    bbox: tuple[float, float, float, float] | None
    zoom: int = Field(ge=0, le=22)
    mode: Literal["points", "clusters"]
    points: list[AtlasPoint | AtlasCluster]
    cache_key: str


class SearchResult(BaseModel):
    type: Literal["location", "session"]
    id: UUID
    slug: str
    title: str
    subtitle: str | None = None
    habitat: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    session_slug: str | None = None
    atlas_point: AtlasPoint | None = None
