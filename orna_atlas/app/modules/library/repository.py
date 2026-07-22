"""Account-backed favorites and listening history."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import case, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from orna_atlas.app.modules.library.models import ListeningHistory, UserFavorite
from orna_atlas.app.modules.locations.models import Location
from orna_atlas.app.modules.locations.public import publicly_discoverable_clause
from orna_atlas.app.modules.sessions.models import RecordingSession


_ELIGIBLE = (
    RecordingSession.access_level.in_(("public", "members_only")),
    RecordingSession.publication_status == "published",
    RecordingSession.archived_at.is_(None),
    publicly_discoverable_clause(),
)


async def get_library_eligible_session(db: AsyncSession, session_id: UUID) -> RecordingSession | None:
    result = await db.execute(
        select(RecordingSession)
        .join(Location, RecordingSession.location_id == Location.id)
        .options(joinedload(RecordingSession.location))
        .where(RecordingSession.id == session_id, *_ELIGIBLE)
    )
    return result.scalar_one_or_none()


async def _favorite_by_id(db: AsyncSession, user_id: UUID, session_id: UUID) -> UserFavorite:
    result = await db.execute(
        select(UserFavorite)
        .options(joinedload(UserFavorite.recording_session).joinedload(RecordingSession.location))
        .where(UserFavorite.user_id == user_id, UserFavorite.session_id == session_id)
    )
    return result.scalar_one()


async def list_favorites(
    db: AsyncSession,
    user_id: UUID,
    *,
    access_levels: tuple[str, ...],
    limit: int,
    offset: int,
) -> list[UserFavorite]:
    result = await db.execute(
        select(UserFavorite)
        .join(UserFavorite.recording_session)
        .join(Location, RecordingSession.location_id == Location.id)
        .options(joinedload(UserFavorite.recording_session).joinedload(RecordingSession.location))
        .where(*_ELIGIBLE, RecordingSession.access_level.in_(access_levels), UserFavorite.user_id == user_id)
        .order_by(UserFavorite.created_at.desc(), UserFavorite.session_id)
        .limit(limit).offset(offset)
    )
    return list(result.scalars().all())


async def upsert_favorite(db: AsyncSession, user_id: UUID, session_id: UUID, *, created_at: datetime) -> UserFavorite:
    await db.execute(
        insert(UserFavorite)
        .values(user_id=user_id, session_id=session_id, created_at=created_at)
        .on_conflict_do_nothing(index_elements=[UserFavorite.user_id, UserFavorite.session_id])
    )
    await db.flush()
    return await _favorite_by_id(db, user_id, session_id)


async def delete_favorite(db: AsyncSession, user_id: UUID, session_id: UUID) -> None:
    await db.execute(delete(UserFavorite).where(UserFavorite.user_id == user_id, UserFavorite.session_id == session_id))
    await db.flush()


async def _history_by_id(db: AsyncSession, user_id: UUID, session_id: UUID) -> ListeningHistory:
    result = await db.execute(
        select(ListeningHistory)
        .options(joinedload(ListeningHistory.recording_session).joinedload(RecordingSession.location))
        .where(ListeningHistory.user_id == user_id, ListeningHistory.session_id == session_id)
    )
    return result.scalar_one()


async def list_history(
    db: AsyncSession,
    user_id: UUID,
    *,
    access_levels: tuple[str, ...],
    limit: int,
    offset: int,
) -> list[ListeningHistory]:
    result = await db.execute(
        select(ListeningHistory)
        .join(ListeningHistory.recording_session)
        .join(Location, RecordingSession.location_id == Location.id)
        .options(joinedload(ListeningHistory.recording_session).joinedload(RecordingSession.location))
        .where(*_ELIGIBLE, RecordingSession.access_level.in_(access_levels), ListeningHistory.user_id == user_id)
        .order_by(ListeningHistory.last_listened_at.desc(), ListeningHistory.session_id)
        .limit(limit).offset(offset)
    )
    return list(result.scalars().all())


def _history_upsert_statement(user_id: UUID, session_id: UUID, *, position_seconds: float, completed: bool, now: datetime):
    completed_at = now if completed else None
    statement = insert(ListeningHistory).values(
        user_id=user_id,
        session_id=session_id,
        first_listened_at=now,
        last_listened_at=now,
        last_position_seconds=position_seconds,
        completed_at=completed_at,
    )
    return statement.on_conflict_do_update(
        index_elements=[ListeningHistory.user_id, ListeningHistory.session_id],
        set_={
            "first_listened_at": func.least(
                ListeningHistory.first_listened_at, statement.excluded.first_listened_at
            ),
            "last_listened_at": func.greatest(
                ListeningHistory.last_listened_at, statement.excluded.last_listened_at
            ),
            "last_position_seconds": case(
                (
                    statement.excluded.last_listened_at >= ListeningHistory.last_listened_at,
                    statement.excluded.last_position_seconds,
                ),
                else_=ListeningHistory.last_position_seconds,
            ),
            "completed_at": func.coalesce(ListeningHistory.completed_at, statement.excluded.completed_at),
        },
    )


async def upsert_history(db: AsyncSession, user_id: UUID, session_id: UUID, *, position_seconds: float, completed: bool, now: datetime) -> ListeningHistory:
    await db.execute(_history_upsert_statement(
        user_id, session_id, position_seconds=position_seconds, completed=completed, now=now
    ))
    await db.flush()
    return await _history_by_id(db, user_id, session_id)


async def delete_history_item(db: AsyncSession, user_id: UUID, session_id: UUID) -> None:
    await db.execute(delete(ListeningHistory).where(ListeningHistory.user_id == user_id, ListeningHistory.session_id == session_id))
    await db.flush()


async def clear_history(db: AsyncSession, user_id: UUID) -> None:
    await db.execute(delete(ListeningHistory).where(ListeningHistory.user_id == user_id))
    await db.flush()
