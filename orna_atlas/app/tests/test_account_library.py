from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from orna_atlas.app.main import app
from orna_atlas.app.modules.library import repository, service
from orna_atlas.app.modules.library.schemas import ListeningProgressUpdate


EXPECTED_PATHS = {
    "/api/v1/users/me/favorites",
    "/api/v1/users/me/favorites/{session_id}",
    "/api/v1/users/me/listening-history",
    "/api/v1/users/me/listening-history/{session_id}",
}


def test_account_library_contracts_are_published() -> None:
    schema = app.openapi()
    paths = schema["paths"]
    assert EXPECTED_PATHS <= paths.keys()
    assert set(paths["/api/v1/users/me/favorites/{session_id}"]) == {"put", "delete"}
    assert set(paths["/api/v1/users/me/listening-history"]) == {"get", "delete"}
    assert set(paths["/api/v1/users/me/listening-history/{session_id}"]) == {"put", "delete"}
    assert {"HTTPBearer", "APIKeyCookie"} <= schema["components"]["securitySchemes"].keys()
    for path in EXPECTED_PATHS:
        for operation in paths[path].values():
            assert operation["security"] == [{"HTTPBearer": []}, {"APIKeyCookie": []}]
            assert "401" in operation["responses"]


@pytest.mark.parametrize("position", [-1, float("nan"), float("inf"), -float("inf")])
def test_listening_progress_rejects_unsafe_positions(position: float) -> None:
    with pytest.raises(ValidationError):
        ListeningProgressUpdate(position_seconds=position)


@pytest.mark.asyncio
async def test_add_public_favorite_commits_once(monkeypatch) -> None:
    user_id = uuid4()
    session_id = uuid4()
    location = SimpleNamespace(id=uuid4(), slug="pine-marsh", name="Pine Marsh", region="Harju", habitat="Wetland")
    recording = SimpleNamespace(
        id=session_id,
        slug="first-session",
        title="First Session",
        recorded_at=datetime.now(UTC),
        duration_seconds=3600,
        access_level="public",
        location=location,
    )
    favorite = SimpleNamespace(recording_session=recording, created_at=datetime.now(UTC))
    db = SimpleNamespace(commit=AsyncMock())
    monkeypatch.setattr(service.repository, "get_library_eligible_session", AsyncMock(return_value=recording))
    monkeypatch.setattr(service.repository, "upsert_favorite", AsyncMock(return_value=favorite))

    result = await service.add_favorite(db, user_id, session_id)

    assert result.session.id == session_id
    assert "latitude" not in result.model_dump_json()
    service.repository.upsert_favorite.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_members_only_favorite_is_not_resolved_without_entitlement(monkeypatch) -> None:
    recording = SimpleNamespace(id=uuid4(), access_level="members_only")
    db = SimpleNamespace(commit=AsyncMock())
    upsert = AsyncMock()
    monkeypatch.setattr(repository, "get_library_eligible_session", AsyncMock(return_value=recording))
    monkeypatch.setattr(service, "has_playback_entitlement", AsyncMock(return_value=False))
    monkeypatch.setattr(repository, "upsert_favorite", upsert)

    with pytest.raises(Exception) as exc_info:
        await service.add_favorite(db, uuid4(), recording.id)

    assert getattr(exc_info.value, "detail", None) == "Session not found"
    upsert.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_history_upsert_preserves_first_completion_timestamp() -> None:
    statement = repository._history_upsert_statement(
        uuid4(), uuid4(), position_seconds=10, completed=True, now=datetime.now(UTC)
    )
    compiled = str(statement.compile(dialect=postgresql.dialect())).lower()
    assert "coalesce(listening_history.completed_at, excluded.completed_at)" in compiled
    assert "greatest(listening_history.last_listened_at, excluded.last_listened_at)" in compiled
    assert "excluded.last_listened_at >= listening_history.last_listened_at" in compiled


@pytest.mark.asyncio
async def test_library_lists_use_current_canonical_access_levels(monkeypatch) -> None:
    db = SimpleNamespace()
    user_id = uuid4()
    list_favorites = AsyncMock(return_value=[])
    list_history = AsyncMock(return_value=[])
    monkeypatch.setattr(service, "has_playback_entitlement", AsyncMock(return_value=False))
    monkeypatch.setattr(repository, "list_favorites", list_favorites)
    monkeypatch.setattr(repository, "list_history", list_history)

    await service.list_favorites(db, user_id, role="user", limit=10, offset=0)
    await service.list_listening_history(db, user_id, role="admin", limit=10, offset=0)

    assert list_favorites.await_args.kwargs["access_levels"] == ("public",)
    assert list_history.await_args.kwargs["access_levels"] == ("public", "members_only")


@pytest.mark.asyncio
async def test_history_position_is_clamped_and_completed_state_is_forward_only(monkeypatch) -> None:
    user_id = uuid4()
    session_id = uuid4()
    location = SimpleNamespace(id=uuid4(), slug="pine-marsh", name="Pine Marsh", region=None, habitat=None)
    recording = SimpleNamespace(
        id=session_id,
        slug="first-session",
        title="First Session",
        recorded_at=datetime.now(UTC),
        duration_seconds=120,
        access_level="public",
        location=location,
    )
    history = SimpleNamespace(
        recording_session=recording,
        first_listened_at=datetime.now(UTC),
        last_listened_at=datetime.now(UTC),
        last_position_seconds=120.0,
        completed_at=datetime.now(UTC),
    )
    db = SimpleNamespace(commit=AsyncMock())
    upsert = AsyncMock(return_value=history)
    monkeypatch.setattr(service.repository, "get_library_eligible_session", AsyncMock(return_value=recording))
    monkeypatch.setattr(service.repository, "upsert_history", upsert)

    occurred_at = datetime(2026, 7, 22, 10, 0, tzinfo=UTC)
    result = await service.update_listening_progress(
        db,
        user_id,
        session_id,
        ListeningProgressUpdate(position_seconds=999, completed=True),
        occurred_at=occurred_at,
    )

    assert result.last_position_seconds == 120
    assert upsert.await_args.kwargs["position_seconds"] == 120
    assert upsert.await_args.kwargs["completed"] is True
    assert upsert.await_args.kwargs["now"] == occurred_at
    db.commit.assert_awaited_once()
