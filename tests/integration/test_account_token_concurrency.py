import asyncio
import json
import os
import threading
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from orna_atlas.app.core.config import Settings
from orna_atlas.app.core.domain_errors import ServiceUnavailableError
from orna_atlas.app.modules.auth import account_tokens

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 to run disposable dependency tests",
    ),
]


def _settings(redis_url: str) -> Settings:
    return Settings.model_validate(
        {
            "_env_file": None,
            "REDIS_URL": redis_url,
            "SMTP_HOST": "smtp.example.test",
            "SMTP_FROM_EMAIL": "accounts@example.test",
            "OAUTH_FRONTEND_URL": "https://orna.land/membership",
        }
    )


def _token_from_body(body: str) -> str:
    link = next(part for part in body.split() if part.startswith("https://"))
    return parse_qs(urlparse(link).fragment)["verify_email_token"][0]


@pytest.mark.asyncio
async def test_real_redis_serializes_pending_resend_activation_and_concurrent_consume(
    monkeypatch,
) -> None:
    redis_url = os.environ["REDIS_URL"]
    settings = _settings(redis_url)
    user_id = uuid4()
    links: list[str] = []
    started = threading.Event()
    release = threading.Event()

    monkeypatch.setattr(
        account_tokens,
        "get_redis_client",
        lambda: Redis.from_url(redis_url, decode_responses=True),
    )

    def capture_email(_settings, _recipient, _subject, body: str) -> None:
        links.append(body)

    cleanup = Redis.from_url(redis_url, decode_responses=True)
    try:
        monkeypatch.setattr(account_tokens, "_send_email", capture_email)
        await account_tokens.send_email_verification(
            settings=settings,
            user_id=user_id,
            email="listener@example.test",
        )
        active_token = _token_from_body(links[0])

        def block_resend(_settings, _recipient, _subject, body: str) -> None:
            links.append(body)
            started.set()
            if not release.wait(timeout=10):
                raise AssertionError("resend release timed out")

        monkeypatch.setattr(account_tokens, "_send_email", block_resend)
        resend = asyncio.create_task(
            account_tokens.send_email_verification(
                settings=settings,
                user_id=user_id,
                email="listener@example.test",
            )
        )
        assert await asyncio.to_thread(started.wait, 10)
        pending_token = _token_from_body(links[1])

        assert await account_tokens.consume_token("email_verification", pending_token) is None
        assert await account_tokens.consume_token("email_verification", active_token) is not None

        release.set()
        await resend
        concurrent_results = await asyncio.gather(
            account_tokens.consume_token("email_verification", pending_token),
            account_tokens.consume_token("email_verification", pending_token),
        )
        assert sum(result is not None for result in concurrent_results) == 1

        started.clear()
        release.clear()
        monkeypatch.setattr(account_tokens, "_send_email", block_resend)
        delayed_old = asyncio.create_task(
            account_tokens.send_email_verification(
                settings=settings,
                user_id=user_id,
                email="listener@example.test",
            )
        )
        assert await asyncio.to_thread(started.wait, 10)
        delayed_old_token = _token_from_body(links[2])

        monkeypatch.setattr(account_tokens, "_send_email", capture_email)
        await account_tokens.send_email_verification(
            settings=settings,
            user_id=user_id,
            email="listener@example.test",
        )
        finalized_newer_token = _token_from_body(links[3])
        newer_claim = await account_tokens.claim_token(
            "email_verification", finalized_newer_token
        )
        assert newer_claim is not None
        finalized_newer_key = account_tokens._token_key(
            "email_verification", finalized_newer_token
        )
        finalized_newer_stored = await cleanup.get(finalized_newer_key)
        assert finalized_newer_stored is not None
        finalized_newer_payload = json.loads(finalized_newer_stored)
        # Reproduce a lost activation response whose retry races after confirmation
        # has already claimed the token. The retry is idempotent and must not erase
        # the claim or the version evidence needed by finalization.
        assert await cleanup.eval(
            account_tokens._ACTIVATE_TOKEN_SCRIPT,
            2,
            finalized_newer_key,
            account_tokens._current_token_key("email_verification", user_id),
            finalized_newer_payload["issue_version"],
            account_tokens._token_digest(finalized_newer_token),
            account_tokens._current_token_prefix("email_verification"),
        ) == 1
        assert await account_tokens.finalize_token_claim(
            "email_verification", finalized_newer_token, newer_claim.claim_id
        )
        # An issuance retry can receive another ambiguous activation response and
        # enter cleanup after this token has already advanced to finalized. That
        # rollback must preserve the tombstone which rejects delayed older mail.
        await cleanup.eval(
            account_tokens._ROLLBACK_TOKEN_SCRIPT,
            1,
            finalized_newer_key,
        )

        release.set()
        with pytest.raises(ServiceUnavailableError, match="superseded before activation"):
            await delayed_old
        assert await account_tokens.consume_token(
            "email_verification", delayed_old_token
        ) is None
    finally:
        release.set()
        keys = [
            key
            async for key in cleanup.scan_iter(
                match=f"auth:email_verification:*{user_id}*",
                count=100,
            )
        ]
        for body in links:
            token = _token_from_body(body)
            keys.append(account_tokens._token_key("email_verification", token))
        if keys:
            await cleanup.delete(*set(keys))
        await cleanup.aclose()
