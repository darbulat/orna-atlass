from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import UUID
import wave

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.core.config import get_settings
from orna_atlas.app.integrations.s3 import get_object_storage_client
from orna_atlas.app.modules.locations.service import require_location
from orna_atlas.app.modules.sessions import repository
from orna_atlas.app.modules.sessions.models import RecordingSession
from orna_atlas.app.modules.sessions.schemas import (
    PlaybackGrantRead,
    SessionAnnotationRead,
    SessionCreate,
    SessionUpdate,
    WaveformRead,
)

STREAMING_RENDITION_KIND = "streaming_rendition"


async def require_session(session: AsyncSession, session_id: UUID) -> RecordingSession:
    recording = await repository.get_session(session, session_id)
    if recording is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return recording


async def require_session_for_admin(session: AsyncSession, session_id: UUID) -> RecordingSession:
    recording = await repository.get_session_for_admin(session, session_id)
    if recording is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return recording


async def require_public_session_by_slug(session: AsyncSession, slug: str) -> RecordingSession:
    recording = await repository.get_session_by_slug(session, slug)
    if recording is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return recording


def waveform_for_session(recording: RecordingSession) -> WaveformRead:
    metadata = recording.metadata_ if isinstance(recording.metadata_, dict) else {}
    waveform = metadata.get("waveform") if isinstance(metadata.get("waveform"), dict) else {}
    payload = {
        "session_id": recording.id,
        "duration_seconds": recording.duration_seconds,
        **waveform,
    }
    return WaveformRead(**payload)


def annotations_for_session(recording: RecordingSession) -> list[SessionAnnotationRead]:
    metadata = recording.metadata_ if isinstance(recording.metadata_, dict) else {}
    annotations = metadata.get("annotations") if isinstance(metadata.get("annotations"), list) else []
    return [SessionAnnotationRead.model_validate(annotation) for annotation in annotations]


def mock_wav_bytes() -> bytes:
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(8000)
        wav_file.writeframes(b"\x00\x00" * 8000)
    return buffer.getvalue()


def create_playback_grant(recording: RecordingSession) -> PlaybackGrantRead:
    rendition = _ready_streaming_rendition(recording)
    storage_client = get_object_storage_client()
    if rendition is not None and storage_client.is_configured():
        settings = get_settings()
        expires_in = settings.s3_presign_expires_seconds
        stream_url = storage_client.generate_presigned_get_url(rendition.storage_key, expires_in=expires_in)
        return PlaybackGrantRead(
            session_id=recording.id,
            stream_url=stream_url,
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
            refresh_after_seconds=min(600, max(60, expires_in - 60)),
        )
    return PlaybackGrantRead.mock_for_session(recording.id)


def _ready_streaming_rendition(recording: RecordingSession):
    assets = list(recording.media_assets)
    for asset in assets:
        if asset.kind == STREAMING_RENDITION_KIND and asset.processing_status == "ready":
            return asset
    return None


async def create_session(session: AsyncSession, data: SessionCreate) -> RecordingSession:
    await require_location(session, data.location_id)
    if await repository.get_session_by_slug_for_admin(session, data.slug):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session slug exists")
    return await repository.create_session(session, data)


async def update_session(session: AsyncSession, session_id: UUID, data: SessionUpdate) -> RecordingSession:
    recording = await require_session_for_admin(session, session_id)
    if data.location_id is not None:
        await require_location(session, data.location_id)
    if (
        data.slug
        and data.slug != recording.slug
        and await repository.get_session_by_slug_for_admin(session, data.slug)
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session slug exists")
    return await repository.update_session(session, recording, data)
