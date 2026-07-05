from datetime import UTC, datetime, timedelta
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from orna_atlas.app.modules.locations.schemas import LocationRead


def _reject_required_nulls(data: dict, fields: set[str]) -> dict:
    null_fields = sorted(field for field in fields if field in data and data[field] is None)
    if null_fields:
        joined = ", ".join(null_fields)
        raise ValueError(f"Fields may be omitted but cannot be null: {joined}")
    return data


def _metadata_from_obj(obj: object) -> dict:
    metadata = getattr(obj, "metadata_", {})
    return metadata if isinstance(metadata, dict) else {}


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


class PlaybackGrantRead(BaseModel):
    session_id: UUID
    status: str = "ready"
    stream_url: str
    expires_at: datetime
    refresh_after_seconds: int = 600

    @classmethod
    def mock_for_session(cls, session_id: UUID) -> "PlaybackGrantRead":
        return cls(
            session_id=session_id,
            stream_url=f"/mock-audio/sessions/{session_id}/stream_320.mp3",
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )


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


class SessionDetailRead(SessionRead):
    location: LocationRead
    recording_integrity: RecordingIntegrityRead = Field(default_factory=RecordingIntegrityRead)
    waveform: WaveformRead = Field(default_factory=WaveformRead)
    annotations: list[SessionAnnotationRead] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def hydrate_detail_fields(cls, data: object) -> object:
        if isinstance(data, dict):
            metadata = data.get("metadata") or data.get("metadata_") or {}
            data = dict(data)
        else:
            metadata = _metadata_from_obj(data)
            data = {
                "id": getattr(data, "id"),
                "location_id": getattr(data, "location_id"),
                "slug": getattr(data, "slug"),
                "title": getattr(data, "title"),
                "description": getattr(data, "description"),
                "recorded_at": getattr(data, "recorded_at"),
                "duration_seconds": getattr(data, "duration_seconds"),
                "recorder": getattr(data, "recorder"),
                "weather": getattr(data, "weather"),
                "access_level": getattr(data, "access_level"),
                "metadata_": metadata,
                "created_at": getattr(data, "created_at"),
                "updated_at": getattr(data, "updated_at"),
                "media_assets": getattr(data, "media_assets", []),
                "location": getattr(data, "location"),
            }
        data.setdefault("recording_integrity", metadata.get("recording_integrity", {}))
        waveform = metadata.get("waveform", {})
        if isinstance(waveform, dict):
            waveform = {"session_id": data.get("id"), "duration_seconds": data.get("duration_seconds"), **waveform}
        data.setdefault("waveform", waveform)
        data.setdefault("annotations", metadata.get("annotations", []))
        return data
