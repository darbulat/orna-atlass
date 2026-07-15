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
