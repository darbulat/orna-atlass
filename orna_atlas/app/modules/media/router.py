from __future__ import annotations

import asyncio

from pathlib import PurePosixPath
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.core.config import get_settings
from orna_atlas.app.db.session import get_db_session
from orna_atlas.app.integrations.s3 import get_object_storage_client
from orna_atlas.app.modules.media import repository
from orna_atlas.app.modules.media.hls_gateway import HlsObjectNotFound, resolve_hls_object_key
from orna_atlas.app.modules.media.hls import HlsError, validate_hls_object_name
from orna_atlas.app.modules.media.hls_token import HlsTokenError, verify_hls_token

router = APIRouter(prefix="/media", tags=["media"])

_CONTENT_TYPES = {
    ".m3u8": "application/vnd.apple.mpegurl",
    ".mp4": "video/mp4",
    ".m4s": "video/iso.segment",
}


@router.get("/hls/{asset_id}/{token}/{object_name}")
async def get_hls_object(
    asset_id: UUID,
    token: str,
    object_name: str,
    session: AsyncSession = Depends(get_db_session),
):
    try:
        validate_hls_object_name(object_name)
        verify_hls_token(token, asset_id, secret=get_settings().auth_secret_key)
    except (HlsError, HlsTokenError) as exc:
        raise HTTPException(status_code=403, detail="Invalid or expired playback grant") from exc

    asset = await repository.get_asset(session, asset_id)
    metadata = asset.metadata_ if asset and isinstance(asset.metadata_, dict) else {}
    inventory = metadata.get("object_keys", [])
    if (
        asset is None
        or not asset.is_active
        or asset.processing_status != "ready"
        or metadata.get("format") != "hls"
        or not isinstance(inventory, list)
    ):
        raise HTTPException(status_code=404, detail="HLS rendition not found")

    try:
        key = resolve_hls_object_key(
            storage_key=asset.storage_key,
            metadata=metadata,
            object_name=object_name,
        )
    except HlsObjectNotFound:
        raise HTTPException(status_code=404, detail="HLS object not found")
    try:
        body = await asyncio.to_thread(get_object_storage_client().get_object_stream, key)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to read HLS object") from exc
    return StreamingResponse(
        body,
        media_type=_CONTENT_TYPES.get(PurePosixPath(object_name).suffix, "application/octet-stream"),
        headers={"Cache-Control": "private, max-age=60"},
    )
