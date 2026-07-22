from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.core.domain_errors import NotFoundError

from orna_atlas.app.modules.library import repository
from orna_atlas.app.modules.library.schemas import (
    FavoriteRead,
    LibrarySessionSummary,
    ListeningHistoryRead,
    ListeningProgressUpdate,
)
from orna_atlas.app.modules.sessions.models import RecordingSession
from orna_atlas.app.modules.memberships.service import has_playback_entitlement


def _favorite_read(favorite) -> FavoriteRead:
    return FavoriteRead(
        session=LibrarySessionSummary.model_validate(favorite.recording_session),
        favorited_at=favorite.created_at,
    )


def _history_read(history) -> ListeningHistoryRead:
    return ListeningHistoryRead(
        session=LibrarySessionSummary.model_validate(history.recording_session),
        first_listened_at=history.first_listened_at,
        last_listened_at=history.last_listened_at,
        last_position_seconds=history.last_position_seconds,
        completed_at=history.completed_at,
    )


async def _get_accessible_session(
    db: AsyncSession, user_id: UUID, session_id: UUID, *, role: str
) -> RecordingSession:
    recording = await repository.get_library_eligible_session(db, session_id)
    if recording is None:
        raise NotFoundError("Session not found")
    if (
        recording.access_level == "members_only"
        and role not in {"editor", "admin"}
        and not await has_playback_entitlement(db, user_id)
    ):
        raise NotFoundError("Session not found")
    return recording


async def _visible_access_levels(db: AsyncSession, user_id: UUID, *, role: str) -> tuple[str, ...]:
    if role in {"editor", "admin"} or await has_playback_entitlement(db, user_id):
        return ("public", "members_only")
    return ("public",)


async def list_favorites(db: AsyncSession, user_id: UUID, *, role: str = "user", limit: int, offset: int) -> list[FavoriteRead]:
    access_levels = await _visible_access_levels(db, user_id, role=role)
    return [_favorite_read(item) for item in await repository.list_favorites(
        db, user_id, access_levels=access_levels, limit=limit, offset=offset
    )]


async def add_favorite(db: AsyncSession, user_id: UUID, session_id: UUID, *, role: str = "user") -> FavoriteRead:
    await _get_accessible_session(db, user_id, session_id, role=role)
    item = await repository.upsert_favorite(db, user_id, session_id, created_at=datetime.now(UTC))
    await db.commit()
    return _favorite_read(item)


async def remove_favorite(db: AsyncSession, user_id: UUID, session_id: UUID) -> None:
    await repository.delete_favorite(db, user_id, session_id)
    await db.commit()


async def list_listening_history(db: AsyncSession, user_id: UUID, *, role: str = "user", limit: int, offset: int) -> list[ListeningHistoryRead]:
    access_levels = await _visible_access_levels(db, user_id, role=role)
    return [_history_read(item) for item in await repository.list_history(
        db, user_id, access_levels=access_levels, limit=limit, offset=offset
    )]


async def update_listening_progress(
    db: AsyncSession,
    user_id: UUID,
    session_id: UUID,
    update: ListeningProgressUpdate,
    *,
    role: str = "user",
    occurred_at: datetime | None = None,
) -> ListeningHistoryRead:
    event_time = occurred_at or datetime.now(UTC)
    recording = await _get_accessible_session(db, user_id, session_id, role=role)
    position = update.position_seconds
    if recording.duration_seconds is not None:
        position = min(position, float(recording.duration_seconds))
    item = await repository.upsert_history(
        db,
        user_id,
        session_id,
        position_seconds=position,
        completed=update.completed,
        now=event_time,
    )
    await db.commit()
    return _history_read(item)


async def remove_listening_history_item(db: AsyncSession, user_id: UUID, session_id: UUID) -> None:
    await repository.delete_history_item(db, user_id, session_id)
    await db.commit()


async def clear_listening_history(db: AsyncSession, user_id: UUID) -> None:
    await repository.clear_history(db, user_id)
    await db.commit()
