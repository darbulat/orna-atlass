from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.core.config import get_settings
from orna_atlas.app.core.errors import ServiceUnavailableError
from orna_atlas.app.core.security import CurrentUser
from orna_atlas.app.integrations.s3 import get_object_storage_client
from orna_atlas.app.integrations.redis import invalidate_atlas_cache
from orna_atlas.app.modules.admin.repository import add_audit_event
from orna_atlas.app.modules.locations.service import require_location_for_admin
from orna_atlas.app.modules.locations.public import is_publicly_discoverable
from orna_atlas.app.modules.memberships.service import has_playback_entitlement
from orna_atlas.app.modules.sessions import repository
from orna_atlas.app.modules.sessions.models import RecordingSession
from orna_atlas.app.modules.sessions.schemas import (
    BirdPartsResponse,
    BirdVocalPartRead,
    FeaturedSessionRead,
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


async def _visible_access_levels(
    session: AsyncSession, current_user: CurrentUser | None
) -> tuple[str, ...]:
    if current_user is None:
        return ("public",)
    if current_user.role in {"editor", "admin"} or await has_playback_entitlement(
        session, UUID(current_user.id)
    ):
        return ("public", "members_only")
    return ("public",)


async def list_visible_sessions(
    session: AsyncSession,
    current_user: CurrentUser | None,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[RecordingSession]:
    access_levels = await _visible_access_levels(session, current_user)
    return await repository.list_sessions(
        session, limit=limit, offset=offset, access_levels=access_levels
    )


async def require_visible_session(
    session: AsyncSession, locator: str, current_user: CurrentUser | None
) -> RecordingSession:
    access_levels = await _visible_access_levels(session, current_user)
    try:
        session_id = UUID(locator)
    except ValueError:
        recording = await repository.get_visible_session_by_slug(
            session, locator, access_levels=access_levels
        )
    else:
        recording = await repository.get_visible_session(
            session, session_id, access_levels=access_levels
        )
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


def bird_parts_for_session(recording: RecordingSession) -> BirdPartsResponse:
    parts = list(recording.bird_vocal_parts) if recording.bird_vocal_parts else []
    if not parts:
        return BirdPartsResponse(session_id=recording.id, parts=[])
    return BirdPartsResponse(
        session_id=recording.id,
        analysis_provider=parts[0].analysis_provider,
        analysis_model_version=parts[0].analysis_model_version,
        parts=[BirdVocalPartRead.model_validate(part) for part in parts],
    )


async def list_featured_sessions(session: AsyncSession, *, limit: int = 12) -> list[FeaturedSessionRead]:
    recordings = await repository.list_featured_sessions(session, limit=limit)
    return [FeaturedSessionRead.model_validate(recording) for recording in recordings]


def create_playback_grant(recording: RecordingSession) -> PlaybackGrantRead:
    rendition = _ready_streaming_rendition(recording)
    if rendition is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Playable rendition is not ready")
    storage_client = get_object_storage_client()
    if not storage_client.is_configured():
        raise ServiceUnavailableError("Playback storage is not configured")
    try:
        if not storage_client.object_exists(rendition.storage_key):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Playable rendition is unavailable")
        settings = get_settings()
        expires_in = settings.s3_presign_expires_seconds
        stream_url = storage_client.generate_presigned_get_url(
            rendition.storage_key, expires_in=expires_in
        )
        return PlaybackGrantRead(
            session_id=recording.id,
            stream_url=stream_url,
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
            refresh_after_seconds=min(600, max(60, expires_in - 60)),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise ServiceUnavailableError("Playback storage is unavailable") from exc


async def authorize_playback_grant(
    session: AsyncSession,
    recording: RecordingSession,
    current_user: CurrentUser | None,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> PlaybackGrantRead:
    if (
        not is_publicly_discoverable(recording.location)
        and (current_user is None or current_user.role not in {"editor", "admin"})
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if recording.access_level == "members_only":
        if current_user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Membership required")
        entitled = current_user.role in {"editor", "admin"} or await has_playback_entitlement(
            session, UUID(current_user.id)
        )
        if not entitled:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Active membership required")
    elif recording.access_level != "public":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    grant = create_playback_grant(recording)
    actor_id = UUID(current_user.id) if current_user and current_user.id != "local-admin" else None
    await add_audit_event(
        session, event_type="playback.grant_created", subject_type="recording_session",
        subject_id=str(recording.id), actor_user_id=actor_id, ip_address=ip_address,
        user_agent=user_agent, metadata={"access_level": recording.access_level},
    )
    await session.commit()
    return grant


def _ready_streaming_rendition(recording: RecordingSession):
    assets = list(recording.media_assets)
    for asset in assets:
        if asset.kind == STREAMING_RENDITION_KIND and asset.processing_status == "ready":
            return asset
    return None


async def create_session(session: AsyncSession, data: SessionCreate) -> RecordingSession:
    await require_location_for_admin(session, data.location_id)
    if await repository.get_session_by_slug_for_admin(session, data.slug):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session slug exists")
    recording = await repository.create_session(session, data)
    await session.commit()
    await session.refresh(recording, attribute_names=["media_assets"])
    await invalidate_atlas_cache()
    return recording


async def update_session(session: AsyncSession, session_id: UUID, data: SessionUpdate) -> RecordingSession:
    recording = await require_session_for_admin(session, session_id)
    if data.location_id is not None:
        await require_location_for_admin(session, data.location_id)
    if (
        data.slug
        and data.slug != recording.slug
        and await repository.get_session_by_slug_for_admin(session, data.slug)
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session slug exists")
    recording = await repository.update_session(session, recording, data)
    await session.commit()
    await session.refresh(recording, attribute_names=["media_assets"])
    await invalidate_atlas_cache()
    return recording


async def delete_session(session: AsyncSession, session_id: UUID) -> None:
    recording = await require_session_for_admin(session, session_id)
    await repository.delete_session(session, recording)
    await session.commit()
    await invalidate_atlas_cache()
