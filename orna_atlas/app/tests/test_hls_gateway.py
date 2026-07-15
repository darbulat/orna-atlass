from uuid import uuid4

import pytest

from orna_atlas.app.modules.media.hls_gateway import HlsObjectNotFound, resolve_hls_object_key


def test_gateway_resolves_only_verified_inventory_members():
    asset_id = uuid4()
    prefix = f"sessions/session/hls/{asset_id}"
    metadata = {
        "format": "hls",
        "object_keys": [f"{prefix}/index.m3u8", f"{prefix}/segment_000000.m4s"],
    }

    assert (
        resolve_hls_object_key(
            storage_key=f"{prefix}/index.m3u8",
            metadata=metadata,
            object_name="segment_000000.m4s",
        )
        == f"{prefix}/segment_000000.m4s"
    )


@pytest.mark.parametrize("name", ["missing.m4s", "../secret", "https://evil.test/x.m4s"])
def test_gateway_rejects_unverified_or_unsafe_objects(name: str):
    with pytest.raises(HlsObjectNotFound):
        resolve_hls_object_key(
            storage_key="sessions/session/hls/build/index.m3u8",
            metadata={"format": "hls", "object_keys": []},
            object_name=name,
        )
