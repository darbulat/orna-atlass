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


class DawnWindowConfig(BaseModel):
    before_minutes: int = Field(ge=1)
    after_minutes: int = Field(ge=1)
    refresh_seconds: int = Field(ge=1)


class DawnLocation(BaseModel):
    location: AtlasPoint
    local_date: str
    local_time: str
    civil_dawn_at: datetime | None = None
    sunrise_at: datetime | None = None
    window_starts_at: datetime | None = None
    window_ends_at: datetime | None = None
    minutes_until_sunrise: int | None = None
    state: Literal["active", "upcoming", "past", "polar"]


class DawnCurrentResponse(BaseModel):
    generated_at: datetime
    window: DawnWindowConfig
    active_locations: list[DawnLocation]
    next_locations: list[DawnLocation]
    cache_key: str


class DawnFollowResponse(BaseModel):
    generated_at: datetime
    window: DawnWindowConfig
    locations: list[DawnLocation]
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
