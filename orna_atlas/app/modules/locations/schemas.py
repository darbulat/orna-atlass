from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from orna_atlas.app.core.domain_types import CoordinateVisibility, SensitivityLevel


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
    coordinate_visibility: CoordinateVisibility = CoordinateVisibility.EXACT_PUBLIC
    sensitivity_level: SensitivityLevel = SensitivityLevel.NONE
    timezone: str = "UTC"
    metadata: dict = Field(default_factory=dict)

    @field_validator("coordinate_visibility", mode="before")
    @classmethod
    def map_legacy_visibility(cls, value: object) -> object:
        return CoordinateVisibility.APPROXIMATE_PUBLIC if value == "public_only" else value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA name") from exc
        return value

    @model_validator(mode="after")
    def validate_public_coordinate_pair(self) -> "LocationBase":
        if (self.public_latitude is None) != (self.public_longitude is None):
            raise ValueError("public latitude and longitude must be supplied together")
        if (
            self.coordinate_visibility is CoordinateVisibility.APPROXIMATE_PUBLIC
            and self.public_latitude is None
        ):
            raise ValueError("approximate public visibility requires public coordinates")
        return self


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
    coordinate_visibility: CoordinateVisibility | None = None
    sensitivity_level: SensitivityLevel | None = None
    timezone: str | None = None
    metadata: dict | None = None

    @field_validator("coordinate_visibility", mode="before")
    @classmethod
    def map_legacy_visibility(cls, value: object) -> object:
        return CoordinateVisibility.APPROXIMATE_PUBLIC if value == "public_only" else value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ZoneInfo(value)
            except ZoneInfoNotFoundError as exc:
                raise ValueError("timezone must be a valid IANA name") from exc
        return value

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
    coordinate_visibility: CoordinateVisibility
    sensitivity_level: SensitivityLevel
    timezone: str
    metadata: dict = Field(validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime

    @field_validator("coordinate_visibility", mode="before")
    @classmethod
    def map_legacy_visibility(cls, value: object) -> object:
        return CoordinateVisibility.APPROXIMATE_PUBLIC if value == "public_only" else value

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @computed_field
    @property
    def coordinates_protected(self) -> bool:
        sensitive_levels = {"protected", "high", "medium"}
        return self.coordinate_visibility != "exact_public" or self.sensitivity_level in sensitive_levels
