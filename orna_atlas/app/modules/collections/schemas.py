from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from orna_atlas.app.modules.locations.schemas import LocationRead
from orna_atlas.app.modules.sessions.schemas import SessionRead
from orna_atlas.app.core.schema_validation import reject_required_nulls


class CollectionSummaryRead(BaseModel):
    id: UUID
    slug: str
    title: str
    description: str | None
    sort_order: int
    location_count: int = 0
    session_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class CollectionDetailRead(BaseModel):
    id: UUID
    slug: str
    title: str
    description: str | None
    sort_order: int
    location_count: int = 0
    session_count: int = 0
    metadata: dict = Field(validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime
    locations: list[LocationRead] = Field(default_factory=list)
    sessions: list[SessionRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class CollectionBase(BaseModel):
    slug: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=220)
    description: str | None = None
    is_public: bool = True
    sort_order: int = 0
    metadata: dict = Field(default_factory=dict)
    location_ids: list[UUID] = Field(default_factory=list)
    session_ids: list[UUID] = Field(default_factory=list)


class CollectionCreate(CollectionBase):
    pass


class CollectionUpdate(BaseModel):
    slug: str | None = Field(default=None, min_length=1, max_length=120)
    title: str | None = Field(default=None, min_length=1, max_length=220)
    description: str | None = None
    is_public: bool | None = None
    sort_order: int | None = None
    metadata: dict | None = None
    location_ids: list[UUID] | None = None
    session_ids: list[UUID] | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_required_nulls(cls, data: object) -> object:
        if isinstance(data, dict):
            return reject_required_nulls(
                data,
                {"slug", "title", "is_public", "sort_order", "metadata", "location_ids", "session_ids"},
            )
        return data


class CollectionAdminRead(BaseModel):
    id: UUID
    slug: str
    title: str
    description: str | None
    is_public: bool
    sort_order: int
    metadata: dict = Field(validation_alias="metadata_")
    location_ids: list[UUID] = Field(default_factory=list)
    session_ids: list[UUID] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
