from datetime import datetime
from uuid import UUID
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    ValidationError,
    field_validator,
    model_validator,
)

from orna_atlas.app.core.domain_types import ProcessingStatus, PublicationStatus, SessionAccess
from orna_atlas.app.core.schema_validation import reject_required_nulls
from orna_atlas.app.modules.locations.schemas import LocationRead
from orna_atlas.app.modules.media.schemas import MediaAssetRead, PublicMediaAssetRead


def _metadata_from_obj(obj: object) -> dict:
    metadata = getattr(obj, "metadata_", {})
    return metadata if isinstance(metadata, dict) else {}


def _bounded_metadata_number(
    value: object, *, minimum: float, maximum: float
) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if minimum <= number <= maximum else None


def _safe_photo_url(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 2048:
        return None
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    return value


def _bounded_metadata_text(value: object, *, maximum_length: int) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized if 0 < len(normalized) <= maximum_length else None


class RecordingIntegrityRead(BaseModel):
    human_noise_level: str = "unknown"
    post_processing: str = "Not yet reviewed"
    microphone_setup: str | None = None
    recordist_notes: str | None = None


class WaveformRead(BaseModel):
    session_id: UUID | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    peaks: list[float] = Field(default_factory=list)
    sample_rate: int = Field(default=1, ge=1)
    status: str = Field(default="placeholder", min_length=1, max_length=40)

    model_config = ConfigDict(allow_inf_nan=False)

    @field_validator("peaks")
    @classmethod
    def validate_peaks(cls, values: list[float]) -> list[float]:
        if len(values) > 10_000:
            raise ValueError("waveform may contain at most 10000 peaks")
        if any(value < -1 or value > 1 for value in values):
            raise ValueError("waveform peaks must be between -1 and 1")
        return values


class SessionAnnotationRead(BaseModel):
    offset_seconds: float = Field(ge=0)
    duration_seconds: float | None = Field(default=None, ge=0)
    label: str = Field(min_length=1, max_length=220)
    annotation_type: str = Field(default="editorial_note", min_length=1, max_length=80)
    confidence: float | None = Field(default=None, ge=0, le=1)
    metadata: dict = Field(default_factory=dict)

    model_config = ConfigDict(allow_inf_nan=False)


class PublicSessionAnnotationRead(BaseModel):
    """Public annotation projection without arbitrary metadata."""

    offset_seconds: float = Field(ge=0)
    duration_seconds: float | None = Field(default=None, ge=0)
    label: str = Field(min_length=1, max_length=220)
    annotation_type: str = Field(default="editorial_note", min_length=1, max_length=80)
    confidence: float | None = Field(default=None, ge=0, le=1)

    model_config = ConfigDict(allow_inf_nan=False)


def validate_session_metadata(metadata: dict) -> dict:
    """Validate structured metadata written by admin/API flows."""
    waveform = metadata.get("waveform")
    if waveform is not None:
        if not isinstance(waveform, dict):
            raise ValueError("metadata.waveform must be an object")
        WaveformRead.model_validate(waveform)
    annotations = metadata.get("annotations")
    if annotations is not None:
        if not isinstance(annotations, list):
            raise ValueError("metadata.annotations must be a list")
        for annotation in annotations:
            SessionAnnotationRead.model_validate(annotation)
    return metadata


def safe_waveform_projection(
    *,
    session_id: UUID | None,
    duration_seconds: int | None,
    value: object,
) -> WaveformRead:
    payload = {
        "session_id": session_id,
        "duration_seconds": duration_seconds,
    }
    if isinstance(value, dict):
        payload.update(value)
    try:
        return WaveformRead.model_validate(payload)
    except (TypeError, ValidationError, ValueError):
        return WaveformRead(session_id=session_id, duration_seconds=duration_seconds)


def safe_annotations_projection(value: object) -> list[PublicSessionAnnotationRead]:
    if not isinstance(value, list):
        return []
    projected: list[PublicSessionAnnotationRead] = []
    for annotation in value:
        try:
            projected.append(PublicSessionAnnotationRead.model_validate(annotation))
        except (TypeError, ValidationError, ValueError):
            continue
    return projected


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


class PublicBirdVocalPartRead(BaseModel):
    """Public BirdNET projection without provider payloads or worker errors."""

    id: UUID
    species_code: str
    species_common_name: str
    species_scientific_name: str | None = None
    starts_at_seconds: float = Field(ge=0)
    ends_at_seconds: float = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    channel: str | None = None
    call_type: str = "unknown"

    model_config = ConfigDict(from_attributes=True)


class BirdPartsResponse(BaseModel):
    session_id: UUID
    analysis_provider: str | None = None
    analysis_model_version: str | None = None
    parts: list[PublicBirdVocalPartRead] = Field(default_factory=list)


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
    publication_status: PublicationStatus = PublicationStatus.DRAFT
    processing_status: ProcessingStatus = ProcessingStatus.PENDING
    is_featured: bool = False
    featured_sort_order: int | None = None
    metadata: dict = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def validate_structured_metadata(cls, value: dict) -> dict:
        return validate_session_metadata(value)


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
    publication_status: PublicationStatus | None = None
    processing_status: ProcessingStatus | None = None
    is_featured: bool | None = None
    featured_sort_order: int | None = None
    metadata: dict | None = None

    @field_validator("metadata")
    @classmethod
    def validate_structured_metadata(cls, value: dict | None) -> dict | None:
        return validate_session_metadata(value) if value is not None else value

    @model_validator(mode="before")
    @classmethod
    def reject_required_nulls(cls, data: object) -> object:
        if isinstance(data, dict):
            return reject_required_nulls(
                data,
                {
                    "location_id",
                    "slug",
                    "title",
                    "recorded_at",
                    "access_level",
                    "publication_status",
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


class PublicSessionRead(BaseModel):
    """Explicit public session projection; raw metadata and timestamps stay private."""

    id: UUID
    location_id: UUID
    slug: str
    title: str
    description: str | None
    recorded_at: datetime
    duration_seconds: int | None = Field(default=None, ge=0)
    recorder: str | None = None
    weather: str | None = None
    access_level: SessionAccess
    publication_status: PublicationStatus = PublicationStatus.PUBLISHED
    processing_status: ProcessingStatus = ProcessingStatus.PENDING
    is_featured: bool = False
    featured_sort_order: int | None = None
    media_assets: list[PublicMediaAssetRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class SessionDetailRead(PublicSessionRead):
    location: LocationRead
    photo_url: HttpUrl | None = None
    altitude_meters: float | None = Field(default=None, ge=-500, le=9000)
    temperature_celsius: float | None = Field(default=None, ge=-100, le=70)
    wind_speed_kph: float | None = Field(default=None, ge=0, le=500)
    humidity_percent: float | None = Field(default=None, ge=0, le=100)
    moon_phase: str | None = Field(default=None, max_length=64)
    recording_integrity: RecordingIntegrityRead = Field(default_factory=RecordingIntegrityRead)
    waveform: WaveformRead = Field(default_factory=WaveformRead)
    annotations: list[PublicSessionAnnotationRead] = Field(default_factory=list)
    bird_parts: BirdPartsResponse | None = None

    @model_validator(mode="before")
    @classmethod
    def hydrate_detail_fields(cls, data: object) -> object:
        source = data
        if isinstance(data, dict):
            metadata = data.get("metadata") or data.get("metadata_") or {}
            metadata = metadata if isinstance(metadata, dict) else {}
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
                "publication_status": getattr(data, "publication_status", "published"),
                "processing_status": getattr(data, "processing_status", "pending"),
                "is_featured": getattr(data, "is_featured", False),
                "featured_sort_order": getattr(data, "featured_sort_order", None),
                "metadata_": metadata,
                "created_at": data.created_at,
                "updated_at": data.updated_at,
                "media_assets": getattr(data, "media_assets", []),
                "location": getattr(data, "location"),
            }
        context = metadata.get("context", metadata)
        context = context if isinstance(context, dict) else {}
        data["photo_url"] = _safe_photo_url(context.get("photo_url"))
        data["altitude_meters"] = _bounded_metadata_number(
            context.get("altitude_meters"), minimum=-500, maximum=9000
        )
        data["temperature_celsius"] = _bounded_metadata_number(
            context.get("temperature_celsius"), minimum=-100, maximum=70
        )
        data["wind_speed_kph"] = _bounded_metadata_number(
            context.get("wind_speed_kph"), minimum=0, maximum=500
        )
        data["humidity_percent"] = _bounded_metadata_number(
            context.get("humidity_percent"), minimum=0, maximum=100
        )
        data["moon_phase"] = _bounded_metadata_text(
            context.get("moon_phase"), maximum_length=64
        )
        integrity = metadata.get("recording_integrity", {})
        data["recording_integrity"] = integrity if isinstance(integrity, dict) else {}
        data["waveform"] = safe_waveform_projection(
            session_id=data.get("id"),
            duration_seconds=data.get("duration_seconds"),
            value=metadata.get("waveform"),
        )
        data["annotations"] = safe_annotations_projection(metadata.get("annotations"))
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
