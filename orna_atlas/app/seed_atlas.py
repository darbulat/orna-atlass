from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from orna_atlas.app.db.session import AsyncSessionLocal, engine
from orna_atlas.app.integrations.redis import get_redis_client
from orna_atlas.app.modules.locations.models import Location
from orna_atlas.app.modules.media.models import MediaAsset  # noqa: F401
from orna_atlas.app.modules.sessions.models import RecordingSession


SEED_LOCATIONS: list[dict[str, Any]] = [
    {
        "slug": "valdaysky-dawn-forest",
        "name": "Valdaysky Dawn Forest",
        "description": "Mixed northern forest at first light with open understory and wet moss beds.",
        "country_code": "RU",
        "region": "Novgorod Oblast",
        "habitat": "forest",
        "exact_latitude": 57.9848,
        "exact_longitude": 33.2525,
        "coordinate_visibility": "exact_public",
        "sensitivity_level": "none",
        "timezone": "Europe/Moscow",
        "metadata_": {"seed": True, "field_context": "early morning forest edge"},
        "sessions": [
            {
                "slug": "valdaysky-dawn-chorus",
                "title": "Dawn Chorus Above the Moss Beds",
                "description": "Layered thrushes, tits, and distant cuckoo calls before sunrise.",
                "recorded_at": datetime(2026, 5, 18, 2, 42, tzinfo=UTC),
                "duration_seconds": 2480,
                "recorder": "ORNA field kit",
                "weather": "Cool, still air, light mist",
            }
        ],
    },
    {
        "slug": "lahemaa-coastal-reeds",
        "name": "Lahemaa Coastal Reeds",
        "description": "Sheltered Baltic reedbed with coastal wind, gulls, and reed warblers.",
        "country_code": "EE",
        "region": "Lahemaa National Park",
        "habitat": "coast",
        "exact_latitude": 59.5794,
        "exact_longitude": 25.7773,
        "coordinate_visibility": "exact_public",
        "sensitivity_level": "none",
        "timezone": "Europe/Tallinn",
        "metadata_": {"seed": True, "field_context": "coastal reedbed"},
        "sessions": [
            {
                "slug": "lahemaa-reedbed-morning",
                "title": "Morning Wind in the Reedbed",
                "description": "Reed movement, gull calls, and close warbler phrases along the shore.",
                "recorded_at": datetime(2026, 6, 3, 3, 15, tzinfo=UTC),
                "duration_seconds": 3120,
                "recorder": "ORNA field kit",
                "weather": "Light coastal wind, overcast",
            }
        ],
    },
    {
        "slug": "polistovsky-protected-marsh",
        "name": "Polistovsky Protected Marsh",
        "description": "Sensitive raised bog location published with generalized public coordinates.",
        "country_code": "RU",
        "region": "Pskov Oblast",
        "habitat": "wetland",
        "exact_latitude": 57.1567,
        "exact_longitude": 30.3186,
        "public_latitude": 57.21,
        "public_longitude": 30.42,
        "coordinate_visibility": "public_only",
        "sensitivity_level": "protected",
        "timezone": "Europe/Moscow",
        "metadata_": {"seed": True, "field_context": "protected raised bog"},
        "sessions": [
            {
                "slug": "polistovsky-bog-before-sunrise",
                "title": "Bog Edge Before Sunrise",
                "description": "Cranes at distance, snipe display, and low wind across open bog.",
                "recorded_at": datetime(2026, 4, 29, 1, 55, tzinfo=UTC),
                "duration_seconds": 2740,
                "recorder": "ORNA field kit",
                "weather": "Cold, low cloud, wet ground",
            }
        ],
    },
    {
        "slug": "kazakh-steppe-evening",
        "name": "Kazakh Steppe Evening",
        "description": "Open steppe recording site with wide ambience and sparse evening calls.",
        "country_code": "KZ",
        "region": "Akmola Region",
        "habitat": "steppe",
        "exact_latitude": 51.9184,
        "exact_longitude": 69.1518,
        "coordinate_visibility": "exact_public",
        "sensitivity_level": "none",
        "timezone": "Asia/Almaty",
        "metadata_": {"seed": True, "field_context": "open steppe grassland"},
        "sessions": [
            {
                "slug": "kazakh-steppe-after-rain",
                "title": "Steppe After Rain",
                "description": "Soft wind, skylarks, and distant thunder after a passing storm.",
                "recorded_at": datetime(2026, 5, 30, 13, 20, tzinfo=UTC),
                "duration_seconds": 1980,
                "recorder": "ORNA field kit",
                "weather": "After rain, clearing sky",
            }
        ],
    },
]


def _session_metadata(location: Location) -> dict[str, Any]:
    return {
        "seed": True,
        "recording_integrity": {
            "human_noise_level": "none",
            "post_processing": "No loops, no studio layers, light normalization only",
            "microphone_setup": "Stereo field recorder, spaced pair",
            "recordist_notes": f"Test fixture recorded for {location.name}.",
        },
        "waveform": {
            "peaks": [0.08, 0.16, 0.11, 0.34, 0.28, 0.47, 0.31, 0.22, 0.38, 0.18],
            "sample_rate": 1,
            "status": "fixture",
        },
        "annotations": [
            {
                "offset_seconds": 45,
                "duration_seconds": 90,
                "label": "Opening ambient bed",
                "annotation_type": "editorial_note",
                "confidence": None,
                "metadata": {"seed": True},
            },
            {
                "offset_seconds": 420,
                "duration_seconds": 120,
                "label": "Prominent bird vocal activity",
                "annotation_type": "bird_activity",
                "confidence": 0.78,
                "metadata": {"seed": True, "habitat": location.habitat},
            },
        ],
    }


async def _upsert_location(session, payload: dict[str, Any]) -> Location:
    location_data = {key: value for key, value in payload.items() if key != "sessions"}
    location = await session.scalar(select(Location).where(Location.slug == payload["slug"]))
    if location is None:
        location = Location(**location_data)
        session.add(location)
    else:
        for key, value in location_data.items():
            setattr(location, key, value)
    return location


async def _upsert_session(session, location: Location, payload: dict[str, Any]) -> None:
    recording = await session.scalar(
        select(RecordingSession).where(RecordingSession.slug == payload["slug"])
    )
    session_data = {
        **payload,
        "location": location,
        "access_level": "public",
        "metadata_": _session_metadata(location),
    }
    if recording is None:
        session.add(RecordingSession(**session_data))
    else:
        for key, value in session_data.items():
            setattr(recording, key, value)


async def _clear_atlas_cache() -> None:
    redis = get_redis_client()
    try:
        keys = [key async for key in redis.scan_iter("atlas:points:*")]
        if keys:
            await redis.delete(*keys)
    except Exception:
        pass
    finally:
        await redis.aclose()


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        for location_payload in SEED_LOCATIONS:
            location = await _upsert_location(session, location_payload)
            await session.flush()
            for session_payload in location_payload["sessions"]:
                await _upsert_session(session, location, session_payload)
        await session.commit()
    await _clear_atlas_cache()
    await engine.dispose()


def main() -> None:
    asyncio.run(seed())
    print(f"Seeded {len(SEED_LOCATIONS)} atlas locations.")


if __name__ == "__main__":
    main()
