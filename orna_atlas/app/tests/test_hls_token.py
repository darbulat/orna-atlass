from datetime import UTC, datetime
from uuid import uuid4

import pytest

from orna_atlas.app.modules.media.hls_token import HlsTokenError, issue_hls_token, verify_hls_token


def test_hls_token_is_asset_scoped_and_expires():
    asset_id = uuid4()
    token = issue_hls_token(asset_id, expires_at=datetime.fromtimestamp(200, UTC), secret="secret")
    assert verify_hls_token(token, asset_id, now=datetime.fromtimestamp(199, UTC), secret="secret") == 200
    with pytest.raises(HlsTokenError):
        verify_hls_token(token, uuid4(), now=datetime.fromtimestamp(199, UTC), secret="secret")
    with pytest.raises(HlsTokenError):
        verify_hls_token(token, asset_id, now=datetime.fromtimestamp(201, UTC), secret="secret")


def test_hls_token_carries_key_id_and_accepts_rotated_key():
    asset_id = uuid4()
    token = issue_hls_token(
        asset_id,
        expires_at=datetime.fromtimestamp(200, UTC),
        secret="retired-secret",
        key_id="retired-2026-07",
    )

    assert token.startswith("retired-2026-07.")
    assert verify_hls_token(
        token,
        asset_id,
        now=datetime.fromtimestamp(199, UTC),
        key_id="current-2026-08",
        secret="current-secret",
        previous_secrets={"retired-2026-07": "retired-secret"},
    ) == 200


def test_hls_token_rejects_unknown_key_id():
    asset_id = uuid4()
    token = issue_hls_token(
        asset_id,
        expires_at=datetime.fromtimestamp(200, UTC),
        secret="unknown-secret",
        key_id="unknown",
    )

    with pytest.raises(HlsTokenError, match="Unknown HLS token key"):
        verify_hls_token(
            token,
            asset_id,
            now=datetime.fromtimestamp(199, UTC),
            key_id="current",
            secret="current-secret",
            previous_secrets={},
        )
