from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from orna_atlas.app.core.domain_types import ProcessingStatus, SessionAccess
from orna_atlas.app.modules.locations.schemas import LocationRead
from orna_atlas.app.modules.media.schemas import MediaAssetRead


def _reject_required_nulls(data: dict, fields: set[str]) -> dict:
    null_fields = sorted(field for field in fields if field in data and data[field] is None)
    if null_fields:
        joined = ", ".join(null_fields)
        raise ValueError(f"Fields may be omitted but cannot be null: {joined}")
    return data


def _metadata_from_obj(obj: object) -> dict:
    metadata = getattr(obj, "metadata_", {})
    return metadata if isinstance(metadata, dict) else {}


class RecordingIntegrityRead(BaseModel):
    human_noise_level: str = "unknown"
    post_processing: str = "Not yet reviewed"
    microphone_setup: str | None = None
    recordist_notes: str | None = None


class WaveformRead(BaseModel):
    session_id: UUID | None = None
    duration_seconds: int | None = None
    peaks: list[float] = Field(default_factory=list)
    sample_rate: int = 1
    status: str = "placeholder"


class SessionAnnotationRead(BaseModel):
    offset_seconds: float = Field(ge=0)
    duration_seconds: float | None = Field(default=None, ge=0)
    label: str
    annotation_type: str = "editorial_note"
    confidence: float | None = Field(default=None, ge=0, le=1)
    metadata: dict = Field(default_factory=dict)


class BirdVocalPartRead(BaseModel):
    id: UUID
    species_code: str
    species_common_name: str
    species_scientific_name: str | None = None
    starts_at_seconds: float = Field(ge=0)
    ends_at_seconds: float = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    channel: str | None = None
    call_type: str = "unknown"
    metadata: dict = Field(default_factory=dict, validation_alias="metadata_")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class BirdPartsResponse(BaseModel):
    session_id: UUID
    analysis_provider: str | None = None
    analysis_model_version: str | None = None
    parts: list[BirdVocalPartRead] = Field(default_factory=list)


class FeaturedSessionRead(BaseModel):
    id: UUID
    slug: str
    title: str
    description: str | None
    recorded_at: datetime
    duration_seconds: int | None
    featured_sort_order: int | None = None
    location: LocationRead

    model_config = ConfigDict(from_attributes=True)


class PlaybackGrantRead(BaseModel):
    session_id: UUID
    status: str = "ready"
    stream_url: str
    expires_at: datetime
    refresh_after_seconds: int = 600


class SessionBase(BaseModel):
    location_id: UUID
    slug: str = Field(min_length=1, max_length=140)
    title: str = Field(min_length=1, max_length=220)
    description: str | None = None
    recorded_at: datetime
    duration_seconds: int | None = Field(default=None, ge=0)
    recorder: str | None = None
    weather: str | None = None
    access_level: SessionAccess = SessionAccess.PUBLIC
    processing_status: ProcessingStatus = ProcessingStatus.PENDING
    is_featured: bool = False
    featured_sort_order: int | None = None
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
    access_level: SessionAccess | None = None
    processing_status: ProcessingStatus | None = None
    is_featured: bool | None = None
    featured_sort_order: int | None = None
    metadata: dict | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_required_nulls(cls, data: object) -> object:
        if isinstance(data, dict):
            return _reject_required_nulls(
                data,
                {
                    "location_id",
                    "slug",
                    "title",
                    "recorded_at",
                    "access_level",
                    "processing_status",
                    "is_featured",
                    "featured_sort_order",
                    "metadata",
                },
            )
        return data


class SessionRead(SessionBase):
    metadata: dict = Field(validation_alias="metadata_")
    id: UUID
    created_at: datetime
    updated_at: datetime
    media_assets: list[MediaAssetRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class SessionDetailRead(SessionRead):
    location: LocationRead
    recording_integrity: RecordingIntegrityRead = Field(default_factory=RecordingIntegrityRead)
    waveform: WaveformRead = Field(default_factory=WaveformRead)
    annotations: list[SessionAnnotationRead] = Field(default_factory=list)
    bird_parts: BirdPartsResponse | None = None

    @model_validator(mode="before")
    @classmethod
    def hydrate_detail_fields(cls, data: object) -> object:
        source = data
        if isinstance(data, dict):
            metadata = data.get("metadata") or data.get("metadata_") or {}
            data = dict(data)
        else:
            metadata = _metadata_from_obj(data)
            source = data
            data = {
                "id": data.id,
                "location_id": data.location_id,
                "slug": data.slug,
                "title": data.title,
                "description": data.description,
                "recorded_at": data.recorded_at,
                "duration_seconds": data.duration_seconds,
                "recorder": data.recorder,
                "weather": data.weather,
                "access_level": data.access_level,
                "processing_status": getattr(data, "processing_status", "pending"),
                "is_featured": getattr(data, "is_featured", False),
                "featured_sort_order": getattr(data, "featured_sort_order", None),
                "metadata_": metadata,
                "created_at": data.created_at,
                "updated_at": data.updated_at,
                "media_assets": getattr(data, "media_assets", []),
                "location": getattr(data, "location"),
            }
        data.setdefault("recording_integrity", metadata.get("recording_integrity", {}))
        waveform = metadata.get("waveform", {})
        if isinstance(waveform, dict):
            waveform = {"session_id": data.get("id"), "duration_seconds": data.get("duration_seconds"), **waveform}
        data.setdefault("waveform", waveform)
        annotations = metadata.get("annotations", [])
        data.setdefault("annotations", annotations if isinstance(annotations, list) else [])
        if isinstance(source, dict):
            parts = list(source.get("bird_vocal_parts") or [])
        else:
            parts = list(getattr(source, "bird_vocal_parts", []) or [])
        if parts:
            data["bird_parts"] = {
                "session_id": data.get("id"),
                "analysis_provider": parts[0].analysis_provider,
                "analysis_model_version": parts[0].analysis_model_version,
                "parts": parts,
            }
        return data
