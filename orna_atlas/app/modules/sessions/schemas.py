from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _reject_required_nulls(data: dict, fields: set[str]) -> dict:
    null_fields = sorted(field for field in fields if field in data and data[field] is None)
    if null_fields:
        joined = ", ".join(null_fields)
        raise ValueError(f"Fields may be omitted but cannot be null: {joined}")
    return data


class MediaAssetRead(BaseModel):
    id: UUID
    session_id: UUID
    kind: str
    mime_type: str
    duration_seconds: int | None
    size_bytes: int | None
    checksum: str | None
    metadata: dict = Field(validation_alias="metadata_")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class SessionBase(BaseModel):
    location_id: UUID
    slug: str = Field(min_length=1, max_length=140)
    title: str = Field(min_length=1, max_length=220)
    description: str | None = None
    recorded_at: datetime
    duration_seconds: int | None = Field(default=None, ge=0)
    recorder: str | None = None
    weather: str | None = None
    access_level: str = "public"
    metadata: dict = Field(default_factory=dict)


class SessionCreate(SessionBase):
    pass


class SessionUpdate(BaseModel):
    location_id: UUID | None = None
    slug: str | None = Field(default=None, min_length=1, max_length=140)
    title: str | None = Field(default=None, min_length=1, max_length=220)
    description: str | None = None
    recorded_at: datetime | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    recorder: str | None = None
    weather: str | None = None
    access_level: str | None = None
    metadata: dict | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_required_nulls(cls, data: object) -> object:
        if isinstance(data, dict):
            return _reject_required_nulls(
                data,
                {"location_id", "slug", "title", "recorded_at", "access_level", "metadata"},
            )
        return data


class SessionRead(SessionBase):
    metadata: dict = Field(validation_alias="metadata_")
    id: UUID
    created_at: datetime
    updated_at: datetime
    media_assets: list[MediaAssetRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
