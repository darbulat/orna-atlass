from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


def _reject_required_nulls(data: dict, fields: set[str]) -> dict:
    null_fields = sorted(field for field in fields if field in data and data[field] is None)
    if null_fields:
        joined = ", ".join(null_fields)
        raise ValueError(f"Fields may be omitted but cannot be null: {joined}")
    return data


class LocationBase(BaseModel):
    slug: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=180)
    description: str | None = None
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    region: str | None = None
    habitat: str | None = None
    exact_latitude: float = Field(ge=-90, le=90)
    exact_longitude: float = Field(ge=-180, le=180)
    public_latitude: float | None = Field(default=None, ge=-90, le=90)
    public_longitude: float | None = Field(default=None, ge=-180, le=180)
    coordinate_visibility: str = Field(default="exact_public", max_length=40)
    sensitivity_level: str = Field(default="none", max_length=40)
    timezone: str = "UTC"
    metadata: dict = Field(default_factory=dict)


class LocationCreate(LocationBase):
    pass


class LocationUpdate(BaseModel):
    slug: str | None = Field(default=None, min_length=1, max_length=120)
    name: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = None
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    region: str | None = None
    habitat: str | None = None
    exact_latitude: float | None = Field(default=None, ge=-90, le=90)
    exact_longitude: float | None = Field(default=None, ge=-180, le=180)
    public_latitude: float | None = Field(default=None, ge=-90, le=90)
    public_longitude: float | None = Field(default=None, ge=-180, le=180)
    coordinate_visibility: str | None = Field(default=None, max_length=40)
    sensitivity_level: str | None = Field(default=None, max_length=40)
    timezone: str | None = None
    metadata: dict | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_required_nulls(cls, data: object) -> object:
        if isinstance(data, dict):
            return _reject_required_nulls(
                data,
                {
                    "slug",
                    "name",
                    "exact_latitude",
                    "exact_longitude",
                    "coordinate_visibility",
                    "sensitivity_level",
                    "timezone",
                    "metadata",
                },
            )
        return data


class LocationRead(BaseModel):
    id: UUID
    slug: str
    name: str
    description: str | None
    country_code: str | None
    region: str | None
    habitat: str | None
    latitude: float | None = Field(ge=-90, le=90)
    longitude: float | None = Field(ge=-180, le=180)
    public_latitude: float | None = Field(default=None, ge=-90, le=90)
    public_longitude: float | None = Field(default=None, ge=-180, le=180)
    coordinate_visibility: str
    sensitivity_level: str
    timezone: str
    metadata: dict = Field(validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @computed_field
    @property
    def coordinates_protected(self) -> bool:
        sensitive_levels = {"protected", "high", "medium"}
        return self.coordinate_visibility != "exact_public" or self.sensitivity_level in sensitive_levels
