"""Ingest the Berezinsky field sample, run BirdNET analysis, and persist bird parts."""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from orna_atlas.app.db.session import AsyncSessionLocal, engine
from orna_atlas.app.integrations.s3 import get_object_storage_client
from orna_atlas.app.modules.locations.models import Location
from orna_atlas.app.modules.media.models import MediaAsset
from orna_atlas.app.modules.media.schemas import MediaAssetCreate
from orna_atlas.app.modules.media.service import process_media_asset, sha256_file
from orna_atlas.app.modules.sessions.models import RecordingSession
from orna_atlas.app.modules.sessions.schemas import SessionCreate
from orna_atlas.app.modules.sessions import repository as sessions_repository

LOCATION_SLUG = "berezinsky-biosphere-reserve"
SESSION_SLUG = "berezinsky-sample"
DEFAULT_AUDIO_PATH = Path("Березинский семпл.WAV")


def _resolve_audio_path(path: str | None) -> Path:
    if path:
        return Path(path).expanduser().resolve()
    return (Path.cwd() / DEFAULT_AUDIO_PATH).resolve()


async def _get_or_create_location(session) -> Location:
    result = await session.execute(select(Location).where(Location.slug == LOCATION_SLUG))
    location = result.scalar_one_or_none()
    if location is not None:
        return location

    location = Location(
        slug=LOCATION_SLUG,
        name="Berezinsky Biosphere Reserve",
        description="Primeval forest and wetland soundscapes in eastern Belarus.",
        country_code="BY",
        region="Minsk Oblast",
        habitat="forest",
        exact_latitude=54.6042,
        exact_longitude=28.3194,
        coordinate_visibility="exact_public",
        sensitivity_level="none",
        timezone="Europe/Minsk",
        metadata_={"seed": False, "field_context": "berezinsky sample ingest"},
    )
    session.add(location)
    await session.flush()
    return location


async def _get_or_create_session(session, location: Location) -> RecordingSession:
    recording = await sessions_repository.get_session_by_slug_for_admin(session, SESSION_SLUG)
    if recording is not None:
        return recording

    return await sessions_repository.create_session(
        session,
        SessionCreate(
            location_id=location.id,
            slug=SESSION_SLUG,
            title="Berezinsky Sample",
            description="Field recording from Berezinsky Biosphere Reserve analyzed with BirdNET.",
            recorded_at=datetime(2026, 7, 7, 4, 30, tzinfo=UTC),
            recorder="ORNA field kit",
            weather="Morning forest ambience",
            access_level="public",
            processing_status="pending",
            is_featured=True,
            featured_sort_order=0,
            metadata={"source": "berezinsky-sample-ingest"},
        ),
    )


async def ingest_berezinsky_sample(audio_path: Path) -> UUID:
    """Upload the Berezinsky WAV sample and process it through the audio pipeline."""
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    storage_client = get_object_storage_client()
    if not storage_client.is_configured():
        raise RuntimeError("S3 storage is not configured")

    checksum = sha256_file(audio_path)
    storage_key = f"sessions/berezinsky/{audio_path.name}"

    async with AsyncSessionLocal() as session:
        location = await _get_or_create_location(session)
        recording = await _get_or_create_session(session, location)

        existing_asset = await session.execute(
            select(MediaAsset).where(
                MediaAsset.session_id == recording.id,
                MediaAsset.kind == "source_audio",
            )
        )
        asset = existing_asset.scalar_one_or_none()
        storage_client.upload_file(audio_path, storage_key, content_type="audio/wav")
        if asset is None:
            from orna_atlas.app.modules.media import service as media_service

            asset = await media_service.create_asset_for_session(
                session,
                recording.id,
                MediaAssetCreate(
                    kind="source_audio",
                    storage_key=storage_key,
                    mime_type="audio/wav",
                    size_bytes=audio_path.stat().st_size,
                    checksum=checksum,
                    enqueue_processing=False,
                    metadata={"source_filename": audio_path.name},
                ),
            )
        else:
            asset.storage_key = storage_key
            asset.checksum = checksum
            asset.size_bytes = audio_path.stat().st_size
            asset.processing_status = "uploaded"
            await session.commit()

        await process_media_asset(session, asset.id)
        return recording.id


async def _main(audio_path: Path) -> None:
    session_id = await ingest_berezinsky_sample(audio_path)
    print(f"Ingest complete for session {session_id} ({SESSION_SLUG})")
    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--audio-path",
        default=None,
        help="Path to the Berezinsky WAV sample (defaults to ./Березинский семпл.WAV)",
    )
    args = parser.parse_args()
    asyncio.run(_main(_resolve_audio_path(args.audio_path)))


if __name__ == "__main__":
    main()
