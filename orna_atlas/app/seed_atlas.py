from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select

from orna_atlas.app.db.session import AsyncSessionLocal, engine
from orna_atlas.app.integrations.redis import get_redis_client
from orna_atlas.app.modules.collections.models import Collection, CollectionLocation, CollectionSession
from orna_atlas.app.modules.locations.models import Location
from orna_atlas.app.modules.media.models import MediaAsset  # noqa: F401
from orna_atlas.app.modules.sessions.models import BirdVocalPart, RecordingSession


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
        "coordinate_visibility": "approximate_public",
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
    {
        "slug": "nepal-himalayas-dawn",
        "name": "Nepal, Himalayas",
        "description": "High Himalayan dawn site with thin alpine air and distant valley birdsong.",
        "country_code": "NP",
        "region": "Himalayas",
        "habitat": "mountain",
        "exact_latitude": 28.3949,
        "exact_longitude": 84.1240,
        "coordinate_visibility": "exact_public",
        "sensitivity_level": "none",
        "timezone": "Asia/Kathmandu",
        "metadata_": {
            "seed": True,
            "field_context": "high Himalayan dawn",
            "source_image": "photo_2026-07-02_16-37-25.jpg",
            "display_context": "Now at dawn",
            "elevation_meters": 2897,
        },
        "sessions": [
            {
                "slug": "nepal-himalayas-first-light",
                "title": "First Light in the Himalayas",
                "description": "Sparse high-altitude calls over a still mountain valley at first light.",
                "recorded_at": datetime(2026, 5, 19, 23, 57, tzinfo=UTC),
                "duration_seconds": 2520,
                "recorder": "ORNA field kit",
                "weather": "Cold high-altitude dawn, calm wind",
            }
        ],
    },
    {
        "slug": "black-forest-germany-dawn",
        "name": "Black Forest, Germany",
        "description": "Layered conifer forest chorus from the Black Forest at live dawn.",
        "country_code": "DE",
        "region": "Black Forest",
        "habitat": "forest",
        "exact_latitude": 48.532,
        "exact_longitude": 8.135,
        "coordinate_visibility": "exact_public",
        "sensitivity_level": "none",
        "timezone": "Europe/Berlin",
        "metadata_": {
            "seed": True,
            "field_context": "Black Forest dawn chorus",
            "source_image": "photo_2026-07-02_16-37-25.jpg",
            "elevation_meters": 778,
            "weather": {
                "temperature_celsius": 9,
                "wind_meters_per_second": 2,
                "humidity_percent": 78,
                "moon_phase": "Waxing crescent",
            },
        },
        "sessions": [
            {
                "slug": "black-forest-dawn-chorus",
                "title": "Black Forest Dawn Chorus",
                "description": "Blackbird, thrush, chaffinch, warbler, tit, pipit, and wren activity.",
                "recorded_at": datetime(2026, 6, 12, 3, 42, 31, tzinfo=UTC),
                "duration_seconds": 3180,
                "recorder": "ORNA field kit",
                "weather": "9 C, light wind, 78% humidity, waxing crescent moon",
            }
        ],
    },
    {
        "slug": "patagonia-chile-dawn",
        "name": "Patagonia, Chile",
        "description": "Cold Patagonian valley and lake ambience under a clear dawn sky.",
        "country_code": "CL",
        "region": "Patagonia",
        "habitat": "mountain",
        "exact_latitude": -51.2538,
        "exact_longitude": -72.3450,
        "coordinate_visibility": "exact_public",
        "sensitivity_level": "none",
        "timezone": "America/Punta_Arenas",
        "metadata_": {
            "seed": True,
            "field_context": "Patagonian lake dawn",
            "source_image": "photo_2026-07-02_16-37-25.jpg",
            "carousel_period": "Dawn",
        },
        "sessions": [
            {
                "slug": "patagonia-chile-lake-dawn",
                "title": "Patagonian Lake at Dawn",
                "description": "Windless lake edge with distant mountain birds and low morning air.",
                "recorded_at": datetime(2026, 3, 24, 9, 42, tzinfo=UTC),
                "duration_seconds": 2740,
                "recorder": "ORNA field kit",
                "weather": "Cold dawn, calm lake surface",
            }
        ],
    },
    {
        "slug": "bavarian-forest-germany-dawn",
        "name": "Bavarian Forest, Germany",
        "description": "Soft spruce and beech forest ambience from a Bavarian morning ridge.",
        "country_code": "DE",
        "region": "Bavaria",
        "habitat": "forest",
        "exact_latitude": 49.1120,
        "exact_longitude": 13.1340,
        "coordinate_visibility": "exact_public",
        "sensitivity_level": "none",
        "timezone": "Europe/Berlin",
        "metadata_": {
            "seed": True,
            "field_context": "Bavarian forest dawn",
            "source_image": "photo_2026-07-02_16-37-25.jpg",
            "carousel_period": "Dawn",
        },
        "sessions": [
            {
                "slug": "bavarian-forest-spruce-dawn",
                "title": "Spruce Forest Before Sunrise",
                "description": "Layered dawn birdsong moving through spruce and beech canopy.",
                "recorded_at": datetime(2026, 6, 8, 3, 34, tzinfo=UTC),
                "duration_seconds": 2860,
                "recorder": "ORNA field kit",
                "weather": "Cool forest dawn with light mist",
            }
        ],
    },
    {
        "slug": "kenya-highlands-dawn",
        "name": "Kenya Highlands",
        "description": "Open highland grass and forest-edge dawn ambience above the valley floor.",
        "country_code": "KE",
        "region": "Central Highlands",
        "habitat": "highland",
        "exact_latitude": -0.4160,
        "exact_longitude": 36.9510,
        "coordinate_visibility": "exact_public",
        "sensitivity_level": "none",
        "timezone": "Africa/Nairobi",
        "metadata_": {
            "seed": True,
            "field_context": "Kenyan highland dawn",
            "source_image": "photo_2026-07-02_16-37-25.jpg",
            "carousel_period": "Dawn",
        },
        "sessions": [
            {
                "slug": "kenya-highlands-morning-plain",
                "title": "Highland Morning Plain",
                "description": "Grassland calls, soft insects, and distant forest-edge birds at sunrise.",
                "recorded_at": datetime(2026, 2, 11, 3, 12, tzinfo=UTC),
                "duration_seconds": 2640,
                "recorder": "ORNA field kit",
                "weather": "Mild highland morning, clear sky",
            }
        ],
    },
    {
        "slug": "hokkaido-japan-dawn",
        "name": "Hokkaido, Japan",
        "description": "Northern Japanese dawn soundscape from forested volcanic uplands.",
        "country_code": "JP",
        "region": "Hokkaido",
        "habitat": "forest",
        "exact_latitude": 43.2203,
        "exact_longitude": 142.8635,
        "coordinate_visibility": "exact_public",
        "sensitivity_level": "none",
        "timezone": "Asia/Tokyo",
        "metadata_": {
            "seed": True,
            "field_context": "Hokkaido upland dawn",
            "source_image": "photo_2026-07-02_16-37-25.jpg",
            "carousel_period": "Dawn",
        },
        "sessions": [
            {
                "slug": "hokkaido-upland-dawn",
                "title": "Hokkaido Upland Dawn",
                "description": "Cool northern forest calls across open volcanic highlands.",
                "recorded_at": datetime(2026, 5, 27, 19, 28, tzinfo=UTC),
                "duration_seconds": 2960,
                "recorder": "ORNA field kit",
                "weather": "Cool dawn, light mountain haze",
            }
        ],
    },
    {
        "slug": "great-bear-rainforest-canada-dawn",
        "name": "Great Bear Rainforest, Canada",
        "description": "Temperate rainforest dawn with dense conifers, wet air, and sheltered calls.",
        "country_code": "CA",
        "region": "British Columbia",
        "habitat": "rainforest",
        "exact_latitude": 52.5000,
        "exact_longitude": -127.5000,
        "coordinate_visibility": "exact_public",
        "sensitivity_level": "none",
        "timezone": "America/Vancouver",
        "metadata_": {
            "seed": True,
            "field_context": "Great Bear Rainforest dawn",
            "source_image": "photo_2026-07-02_16-37-25.jpg",
            "carousel_period": "Dawn",
        },
        "sessions": [
            {
                "slug": "great-bear-rainforest-wet-dawn",
                "title": "Wet Dawn in Great Bear Rainforest",
                "description": "Rain-softened forest bed with close canopy calls and distant water.",
                "recorded_at": datetime(2026, 4, 16, 12, 58, tzinfo=UTC),
                "duration_seconds": 3020,
                "recorder": "ORNA field kit",
                "weather": "Wet, overcast coastal rainforest dawn",
            }
        ],
    },
]


SEED_COLLECTIONS: list[dict[str, Any]] = [
    {
        "slug": "dawn-archive",
        "title": "Dawn Archive",
        "description": "Editorial journeys through first-light recordings across the atlas.",
        "sort_order": 0,
        "location_slugs": [
            "valdaysky-dawn-forest",
            "polistovsky-protected-marsh",
            "nepal-himalayas-dawn",
            "black-forest-germany-dawn",
            "patagonia-chile-dawn",
            "bavarian-forest-germany-dawn",
            "kenya-highlands-dawn",
            "hokkaido-japan-dawn",
            "great-bear-rainforest-canada-dawn",
        ],
        "session_slugs": [
            "valdaysky-dawn-chorus",
            "nepal-himalayas-first-light",
            "black-forest-dawn-chorus",
            "patagonia-chile-lake-dawn",
        ],
    },
    {
        "slug": "wetlands",
        "title": "Wetlands",
        "description": "Reedbeds, bogs, and coastal marshes with layered aquatic soundscapes.",
        "sort_order": 1,
        "location_slugs": ["lahemaa-coastal-reeds", "polistovsky-protected-marsh"],
        "session_slugs": ["lahemaa-reedbed-morning", "polistovsky-bog-before-sunrise"],
    },
    {
        "slug": "no-human-noise",
        "title": "No Human Noise",
        "description": "Sessions selected for minimal anthropogenic disturbance.",
        "sort_order": 2,
        "location_slugs": [
            "valdaysky-dawn-forest",
            "kazakh-steppe-evening",
            "patagonia-chile-dawn",
            "great-bear-rainforest-canada-dawn",
        ],
        "session_slugs": [
            "kazakh-steppe-after-rain",
            "patagonia-chile-lake-dawn",
            "great-bear-rainforest-wet-dawn",
        ],
    },
    {
        "slug": "photo-dawn-places",
        "title": "Photo Dawn Places",
        "description": "Locations visible in the July 2026 dawn interface reference image.",
        "sort_order": 3,
        "location_slugs": [
            "nepal-himalayas-dawn",
            "black-forest-germany-dawn",
            "patagonia-chile-dawn",
            "bavarian-forest-germany-dawn",
            "kenya-highlands-dawn",
            "hokkaido-japan-dawn",
            "great-bear-rainforest-canada-dawn",
        ],
        "session_slugs": [
            "nepal-himalayas-first-light",
            "black-forest-dawn-chorus",
            "patagonia-chile-lake-dawn",
            "bavarian-forest-spruce-dawn",
            "kenya-highlands-morning-plain",
            "hokkaido-upland-dawn",
            "great-bear-rainforest-wet-dawn",
        ],
    },
]

FEATURED_SESSION_SLUGS = [
    "valdaysky-dawn-chorus",
    "lahemaa-reedbed-morning",
    "polistovsky-bog-before-sunrise",
    "black-forest-dawn-chorus",
    "nepal-himalayas-first-light",
]

BIRD_PARTS_BY_SESSION: dict[str, list[dict[str, Any]]] = {
    "valdaysky-dawn-chorus": [
        {
            "species_code": "turdus_merula",
            "species_common_name": "Common blackbird",
            "species_scientific_name": "Turdus merula",
            "starts_at_seconds": 184.2,
            "ends_at_seconds": 191.8,
            "confidence": 0.93,
            "call_type": "song",
            "analysis_provider": "external-bird-audio-service",
            "analysis_model_version": "2026-06",
        },
        {
            "species_code": "parus_major",
            "species_common_name": "Great tit",
            "species_scientific_name": "Parus major",
            "starts_at_seconds": 420.0,
            "ends_at_seconds": 432.5,
            "confidence": 0.88,
            "call_type": "call",
            "analysis_provider": "external-bird-audio-service",
            "analysis_model_version": "2026-06",
        },
    ],
    "lahemaa-reedbed-morning": [
        {
            "species_code": "acrocephalus_scirpaceus",
            "species_common_name": "Eurasian reed warbler",
            "species_scientific_name": "Acrocephalus scirpaceus",
            "starts_at_seconds": 96.0,
            "ends_at_seconds": 108.4,
            "confidence": 0.91,
            "call_type": "song",
            "analysis_provider": "external-bird-audio-service",
            "analysis_model_version": "2026-06",
        },
    ],
    "black-forest-dawn-chorus": [
        {
            "species_code": "turdus_merula",
            "species_common_name": "Eurasian blackbird",
            "species_scientific_name": "Turdus merula",
            "starts_at_seconds": 118.0,
            "ends_at_seconds": 620.0,
            "confidence": 0.92,
            "call_type": "song",
            "analysis_provider": "external-bird-audio-service",
            "analysis_model_version": "2026-06",
        },
        {
            "species_code": "turdus_philomelos",
            "species_common_name": "Song thrush",
            "species_scientific_name": "Turdus philomelos",
            "starts_at_seconds": 402.0,
            "ends_at_seconds": 690.0,
            "confidence": 0.89,
            "call_type": "song",
            "analysis_provider": "external-bird-audio-service",
            "analysis_model_version": "2026-06",
        },
        {
            "species_code": "fringilla_coelebs",
            "species_common_name": "Common chaffinch",
            "species_scientific_name": "Fringilla coelebs",
            "starts_at_seconds": 510.0,
            "ends_at_seconds": 995.0,
            "confidence": 0.87,
            "call_type": "song",
            "analysis_provider": "external-bird-audio-service",
            "analysis_model_version": "2026-06",
        },
        {
            "species_code": "phylloscopus_trochilus",
            "species_common_name": "Willow warbler",
            "species_scientific_name": "Phylloscopus trochilus",
            "starts_at_seconds": 1240.0,
            "ends_at_seconds": 1515.0,
            "confidence": 0.86,
            "call_type": "song",
            "analysis_provider": "external-bird-audio-service",
            "analysis_model_version": "2026-06",
        },
        {
            "species_code": "parus_major",
            "species_common_name": "Great tit",
            "species_scientific_name": "Parus major",
            "starts_at_seconds": 925.0,
            "ends_at_seconds": 1498.0,
            "confidence": 0.88,
            "call_type": "call",
            "analysis_provider": "external-bird-audio-service",
            "analysis_model_version": "2026-06",
        },
        {
            "species_code": "anthus_trivialis",
            "species_common_name": "Tree pipit",
            "species_scientific_name": "Anthus trivialis",
            "starts_at_seconds": 515.0,
            "ends_at_seconds": 1180.0,
            "confidence": 0.84,
            "call_type": "song",
            "analysis_provider": "external-bird-audio-service",
            "analysis_model_version": "2026-06",
        },
        {
            "species_code": "troglodytes_troglodytes",
            "species_common_name": "Wren",
            "species_scientific_name": "Troglodytes troglodytes",
            "starts_at_seconds": 210.0,
            "ends_at_seconds": 810.0,
            "confidence": 0.85,
            "call_type": "song",
            "analysis_provider": "external-bird-audio-service",
            "analysis_model_version": "2026-06",
        },
    ],
}


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


async def _upsert_session(session, location: Location, payload: dict[str, Any]) -> RecordingSession:
    recording = await session.scalar(
        select(RecordingSession).where(RecordingSession.slug == payload["slug"])
    )
    session_data = {
        **payload,
        "location": location,
        "access_level": "public",
        "publication_status": "published",
        "metadata_": _session_metadata(location),
    }
    if recording is None:
        recording = RecordingSession(**session_data)
        session.add(recording)
    else:
        for key, value in session_data.items():
            setattr(recording, key, value)
    await session.flush()
    return recording


async def _mark_featured_sessions(session) -> None:
    for index, slug in enumerate(FEATURED_SESSION_SLUGS):
        recording = await session.scalar(select(RecordingSession).where(RecordingSession.slug == slug))
        if recording is not None:
            recording.is_featured = True
            recording.featured_sort_order = index


async def _seed_bird_parts(session) -> None:
    for session_slug, parts in BIRD_PARTS_BY_SESSION.items():
        recording = await session.scalar(select(RecordingSession).where(RecordingSession.slug == session_slug))
        if recording is None:
            continue
        existing = await session.scalars(
            select(BirdVocalPart).where(BirdVocalPart.session_id == recording.id)
        )
        for part in existing:
            await session.delete(part)
        for part in parts:
            session.add(BirdVocalPart(session_id=recording.id, metadata_={"seed": True}, **part))


async def _seed_collections(session) -> None:
    slug_to_location = {
        row.slug: row
        for row in (await session.scalars(select(Location))).all()
    }
    slug_to_session = {
        row.slug: row
        for row in (await session.scalars(select(RecordingSession))).all()
    }
    for payload in SEED_COLLECTIONS:
        collection = await session.scalar(select(Collection).where(Collection.slug == payload["slug"]))
        if collection is None:
            collection = Collection(
                slug=payload["slug"],
                title=payload["title"],
                description=payload["description"],
                sort_order=payload["sort_order"],
                metadata_={"seed": True},
            )
            session.add(collection)
            await session.flush()
        else:
            collection.title = payload["title"]
            collection.description = payload["description"]
            collection.sort_order = payload["sort_order"]
        await session.execute(
            delete(CollectionLocation).where(CollectionLocation.collection_id == collection.id)
        )
        await session.execute(
            delete(CollectionSession).where(CollectionSession.collection_id == collection.id)
        )
        await session.flush()
        for index, location_slug in enumerate(payload["location_slugs"]):
            location = slug_to_location.get(location_slug)
            if location is not None:
                session.add(
                    CollectionLocation(collection_id=collection.id, location_id=location.id, sort_order=index)
                )
        for index, session_slug in enumerate(payload["session_slugs"]):
            recording = slug_to_session.get(session_slug)
            if recording is not None:
                session.add(
                    CollectionSession(collection_id=collection.id, session_id=recording.id, sort_order=index)
                )


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
        await _mark_featured_sessions(session)
        await _seed_bird_parts(session)
        await _seed_collections(session)
        await session.commit()
    await _clear_atlas_cache()
    await engine.dispose()


def main() -> None:
    asyncio.run(seed())
    print(f"Seeded {len(SEED_LOCATIONS)} atlas locations and {len(SEED_COLLECTIONS)} collections.")


if __name__ == "__main__":
    main()
