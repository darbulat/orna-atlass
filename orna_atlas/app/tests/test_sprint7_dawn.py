from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from orna_atlas.app.integrations.sunrise import sunrise_utc
from orna_atlas.app.main import app
from orna_atlas.app.modules.atlas import service


def public_location(*, latitude: float, longitude: float, timezone: str = "UTC") -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        slug=f"location-{uuid4()}",
        name="Dawn Marsh",
        description=None,
        country_code="EE",
        region="Laanemaa",
        habitat="wetland",
        latitude=latitude,
        longitude=longitude,
        timezone=timezone,
        sensitivity_level="none",
        sessions=[
            SimpleNamespace(
                id=uuid4(),
                slug="dawn-marsh-session",
                title="Dawn Marsh Session",
                recorded_at=now,
                duration_seconds=1200,
                access_level="public",
            )
        ],
    )


def test_sprint7_dawn_routes_are_registered() -> None:
    schema = TestClient(app).get("/openapi.json").json()

    assert "/api/v1/atlas/dawn/current" in schema["paths"]
    assert "/api/v1/atlas/dawn/follow" in schema["paths"]


async def test_current_dawn_returns_active_locations(monkeypatch) -> None:
    location = public_location(latitude=0, longitude=0)
    point = service.point_from_location(location)
    assert point is not None
    now = datetime(2026, 3, 20, 6, 4, tzinfo=UTC)
    sunrise_at = now + timedelta(minutes=5)

    requested: dict[str, float | int] = {}

    async def fake_locations(session, *, target_longitude, limit):
        requested.update(target_longitude=target_longitude, limit=limit)
        return [location]

    def fake_window(**kwargs):
        return SimpleNamespace(
            local_date=now.date(),
            timezone="UTC",
            civil_dawn_at=sunrise_at - timedelta(minutes=30),
            sunrise_at=sunrise_at,
            window_starts_at=sunrise_at - timedelta(minutes=45),
            window_ends_at=sunrise_at + timedelta(minutes=30),
        )

    monkeypatch.setattr(
        service.repository,
        "list_dawn_candidate_locations",
        fake_locations,
    )
    monkeypatch.setattr(service, "dawn_window", fake_window)

    payload = await service.get_current_dawn(SimpleNamespace(), now=now, limit=5)

    assert payload.window.before_minutes == 45
    assert payload.window.after_minutes == 30
    assert payload.active_locations[0].location.slug == location.slug
    assert payload.active_locations[0].state == "active"
    assert payload.active_locations[0].minutes_until_sunrise == 5
    assert payload.cache_key == service.stable_dawn_cache_key(kind="current", now=now, limit=5)
    assert requested == {"target_longitude": -1.0, "limit": 128}


def test_dawn_cache_key_uses_minute_bucket() -> None:
    first = datetime(2026, 7, 6, 10, 0, 1, tzinfo=UTC)
    second = datetime(2026, 7, 6, 10, 0, 59, tzinfo=UTC)

    assert service.stable_dawn_cache_key(kind="follow", now=first, limit=24) == (
        service.stable_dawn_cache_key(kind="follow", now=second, limit=24)
    )


def test_sunrise_preserves_utc_day_offset_for_eastern_longitudes() -> None:
    sunrise = sunrise_utc(latitude=35.6762, longitude=139.6503, local_date=datetime(2026, 7, 6).date())

    assert sunrise is not None
    assert sunrise.date() == datetime(2026, 7, 5).date()


async def test_current_dawn_rolls_past_windows_into_next_locations(monkeypatch) -> None:
    location = public_location(latitude=57.0, longitude=24.0)
    now = datetime(2026, 7, 6, 14, 0, tzinfo=UTC)

    async def fake_locations(session, *, target_longitude, limit):
        return [location]

    def fake_window(**kwargs):
        query_now = kwargs["now"]
        if query_now.date() == now.date():
            sunrise_at = now - timedelta(hours=2)
        else:
            sunrise_at = now + timedelta(hours=22)
        return SimpleNamespace(
            local_date=query_now.date(),
            timezone="UTC",
            civil_dawn_at=sunrise_at - timedelta(minutes=30),
            sunrise_at=sunrise_at,
            window_starts_at=sunrise_at - timedelta(minutes=45),
            window_ends_at=sunrise_at + timedelta(minutes=30),
        )

    monkeypatch.setattr(
        service.repository,
        "list_dawn_candidate_locations",
        fake_locations,
    )
    monkeypatch.setattr(service, "dawn_window", fake_window)

    payload = await service.get_current_dawn(SimpleNamespace(), now=now, limit=5)

    assert payload.active_locations == []
    assert payload.next_locations[0].location.slug == location.slug
    assert payload.next_locations[0].state == "upcoming"
    assert payload.next_locations[0].minutes_until_sunrise == 22 * 60
