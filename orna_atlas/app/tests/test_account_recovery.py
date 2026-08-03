import asyncio
from datetime import UTC, datetime
import json
import threading
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException, Request, Response
from fastapi.testclient import TestClient
from redis.exceptions import RedisError

from orna_atlas.app.core.async_utils import finish_cancelled_compensation
from orna_atlas.app.core.config import Settings
from orna_atlas.app.core.domain_errors import AuthenticationError, ServiceUnavailableError
from orna_atlas.app.core.rate_limit import auth_rate_limit
from orna_atlas.app.core.security import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    get_optional_catalog_user,
)
from orna_atlas.app.db.session import get_db_session
from orna_atlas.app.main import create_app
from orna_atlas.app.modules.auth import account_tokens, router, service
from orna_atlas.app.modules.auth.schemas import PasswordResetRequest, TokenResponse


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.closed = False

    async def eval(self, script: str, numkeys: int, *args):
        keys = list(args[:numkeys])
        values = list(args[numkeys:])
        if "account_token_prepare_v3" in script:
            token_key, version_key, current_key = keys
            payload, ttl = values
            if token_key in self.values:
                return [0, "", ""]
            version = int(self.values.get(version_key, "0")) + 1
            previous = self.values.get(current_key, "")
            decoded_payload = json.loads(str(payload))
            decoded_payload["issue_version"] = str(version)
            decoded_payload["state"] = "pending"
            self.values[token_key] = json.dumps(decoded_payload, separators=(",", ":"))
            self.values[version_key] = str(version)
            self.ttls[token_key] = int(ttl)
            self.ttls[version_key] = int(ttl)
            return [1, str(version), previous]
        if "account_token_activate_v3" in script:
            token_key, current_key = keys
            issue_version, digest, token_prefix = values
            stored = self.values.get(token_key)
            if stored is None:
                return 0
            payload = json.loads(stored)
            if payload.get("issue_version") != str(issue_version):
                self.values.pop(token_key, None)
                return 0
            if payload.get("state") in {"active", "claimed", "finalized"}:
                if self.values.get(current_key) == digest:
                    return 1
                return 0
            if payload.get("state") != "pending":
                self.values.pop(token_key, None)
                return 0
            current_digest = self.values.get(current_key, "")
            if current_digest and current_digest != digest:
                current_stored = self.values.get(f"{token_prefix}{current_digest}")
                if current_stored:
                    current_payload = json.loads(current_stored)
                    if int(current_payload["issue_version"]) > int(payload["issue_version"]):
                        self.values.pop(token_key, None)
                        return 0
            payload["state"] = "active"
            self.values[token_key] = json.dumps(payload, separators=(",", ":"))
            self.values[current_key] = str(digest)
            self.ttls[current_key] = self.ttls[token_key]
            if current_digest and current_digest != digest:
                self.values.pop(f"{token_prefix}{current_digest}", None)
            return 1
        if "account_token_rollback_v3" in script:
            (token_key,) = keys
            stored = self.values.get(token_key)
            if stored is None or json.loads(stored).get("state") not in {
                "active", "claimed", "finalized",
            }:
                self.values.pop(token_key, None)
            return 1
        if "account_token_claim_v1" in script:
            (token_key,) = keys
            current_prefix, digest, claim_id = values
            stored = self.values.get(token_key)
            if stored is None:
                return [0, ""]
            try:
                payload = json.loads(stored)
                user_id = payload["user_id"]
            except (KeyError, TypeError, json.JSONDecodeError):
                self.values.pop(token_key, None)
                return [-1, ""]
            current_key = f"{current_prefix}{user_id}"
            if self.values.get(current_key) != digest:
                if payload.get("state") == "pending":
                    return [0, ""]
                self.values.pop(token_key, None)
                return [0, ""]
            if payload.get("state") == "claimed" and payload.get("claim_id") == claim_id:
                return [1, stored]
            if payload.get("state") != "active":
                return [0, ""]
            payload["state"] = "claimed"
            payload["claim_id"] = str(claim_id)
            self.values[token_key] = json.dumps(payload, separators=(",", ":"))
            return [1, stored]
        if "account_token_finalize_claim_v1" in script:
            (token_key,) = keys
            current_prefix, digest, claim_id = values
            stored = self.values.get(token_key)
            if stored is None:
                return 0
            payload = json.loads(stored)
            current_key = f"{current_prefix}{payload['user_id']}"
            if payload.get("state") == "finalized":
                return 1 if self.values.get(current_key) == digest else 0
            if payload.get("state") != "claimed" or payload.get("claim_id") != claim_id:
                return 0
            if self.values.get(current_key) != digest:
                return 0
            payload["state"] = "finalized"
            payload.pop("claim_id", None)
            self.values[token_key] = json.dumps(payload, separators=(",", ":"))
            return 1
        if "account_token_rollback_claim_v1" in script:
            (token_key,) = keys
            (claim_id,) = values
            stored = self.values.get(token_key)
            if stored is None:
                return 0
            payload = json.loads(stored)
            if payload.get("state") != "claimed" or payload.get("claim_id") != claim_id:
                return 0
            payload["state"] = "active"
            payload.pop("claim_id", None)
            self.values[token_key] = json.dumps(payload, separators=(",", ":"))
            return 1
        raise AssertionError("unexpected Redis script")

    async def set(
        self,
        key: str,
        value: str,
        *,
        ex: int,
        nx: bool = False,
        get: bool = False,
    ) -> bool | str | None:
        assert ex > 0
        previous = self.values.get(key)
        if nx and previous is not None:
            return False
        self.values[key] = value
        if get:
            return previous
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def getdel(self, key: str) -> str | None:
        return self.values.pop(key, None)

    async def delete(self, key: str) -> int:
        return int(self.values.pop(key, None) is not None)

    async def aclose(self) -> None:
        self.closed = True


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "SMTP_HOST": "smtp.example.test",
        "SMTP_FROM_EMAIL": "accounts@example.test",
        "OAUTH_FRONTEND_URL": "https://orna.land/membership",
    }
    values.update(overrides)
    return Settings.model_validate(values)


@pytest.mark.asyncio
async def test_email_verification_token_is_opaque_fragment_bound_and_one_time(monkeypatch) -> None:
    redis = FakeRedis()
    delivered: dict[str, str] = {}
    user_id = uuid4()
    monkeypatch.setattr(account_tokens, "get_redis_client", lambda: redis)

    def capture_email(
        _settings: Settings,
        recipient: str,
        subject: str,
        body: str,
    ) -> None:
        delivered.update(recipient=recipient, subject=subject, body=body)

    monkeypatch.setattr(account_tokens, "_send_email", capture_email)

    await account_tokens.send_email_verification(
        settings=settings(),
        user_id=user_id,
        email="Listener@Example.test",
    )

    assert delivered["recipient"] == "listener@example.test"
    assert delivered["subject"] == "Verify your ORNA Atlas email"
    link = next(part for part in delivered["body"].split() if part.startswith("https://"))
    parsed = urlparse(link)
    assert parsed.query == ""
    token = parse_qs(parsed.fragment)["verify_email_token"][0]
    assert len(token) >= 32
    assert token not in next(iter(redis.values))
    stored = json.loads(next(iter(redis.values.values())))
    assert stored == {
        "kind": "email_verification",
        "user_id": str(user_id),
        "email": "listener@example.test",
        "issue_version": "1",
        "state": "active",
    }

    claims = await account_tokens.consume_token("email_verification", token)
    assert claims == {
        "kind": "email_verification",
        "user_id": str(user_id),
        "email": "listener@example.test",
    }
    assert await account_tokens.consume_token("email_verification", token) is None


@pytest.mark.asyncio
async def test_new_account_token_supersedes_previous_link_for_same_user(monkeypatch) -> None:
    redis = FakeRedis()
    links: list[str] = []
    user_id = uuid4()
    monkeypatch.setattr(account_tokens, "get_redis_client", lambda: redis)

    def capture_email(
        _settings: Settings,
        _recipient: str,
        _subject: str,
        body: str,
    ) -> None:
        links.append(next(part for part in body.split() if part.startswith("https://")))

    monkeypatch.setattr(account_tokens, "_send_email", capture_email)
    for _ in range(2):
        await account_tokens.send_email_verification(
            settings=settings(),
            user_id=user_id,
            email="listener@example.test",
        )

    old_token = parse_qs(urlparse(links[0]).fragment)["verify_email_token"][0]
    current_token = parse_qs(urlparse(links[1]).fragment)["verify_email_token"][0]
    assert await account_tokens.consume_token("email_verification", old_token) is None
    assert await account_tokens.consume_token("email_verification", current_token) == {
        "kind": "email_verification",
        "user_id": str(user_id),
        "email": "listener@example.test",
    }


@pytest.mark.asyncio
async def test_failed_resend_restores_the_previously_delivered_token(monkeypatch) -> None:
    redis = FakeRedis()
    links: list[str] = []
    user_id = uuid4()
    monkeypatch.setattr(account_tokens, "get_redis_client", lambda: redis)

    def capture_email(_settings, _recipient, _subject, body: str) -> None:
        links.append(next(part for part in body.split() if part.startswith("https://")))

    monkeypatch.setattr(account_tokens, "_send_email", capture_email)
    await account_tokens.send_email_verification(
        settings=settings(), user_id=user_id, email="listener@example.test"
    )
    delivered_token = parse_qs(urlparse(links[0]).fragment)["verify_email_token"][0]

    def fail_email(*_args) -> None:
        raise ServiceUnavailableError("delivery failed")

    monkeypatch.setattr(account_tokens, "_send_email", fail_email)
    with pytest.raises(ServiceUnavailableError):
        await account_tokens.send_email_verification(
            settings=settings(), user_id=user_id, email="listener@example.test"
        )

    assert await account_tokens.consume_token("email_verification", delivered_token) == {
        "kind": "email_verification",
        "user_id": str(user_id),
        "email": "listener@example.test",
    }
    delivered_key = account_tokens._token_key("email_verification", delivered_token)
    assert set(redis.values) == {
        account_tokens._token_version_key("email_verification", user_id),
        account_tokens._current_token_key("email_verification", user_id),
        delivered_key,
    }
    assert json.loads(redis.values[delivered_key])["state"] == "finalized"


@pytest.mark.asyncio
async def test_pending_resend_is_not_consumable_and_keeps_the_active_token(monkeypatch) -> None:
    redis = FakeRedis()
    links: list[str] = []
    user_id = uuid4()
    started = threading.Event()
    release = threading.Event()
    monkeypatch.setattr(account_tokens, "get_redis_client", lambda: redis)

    def capture_email(_settings, _recipient, _subject, body: str) -> None:
        links.append(next(part for part in body.split() if part.startswith("https://")))

    monkeypatch.setattr(account_tokens, "_send_email", capture_email)
    await account_tokens.send_email_verification(
        settings=settings(), user_id=user_id, email="listener@example.test"
    )
    active_token = parse_qs(urlparse(links[0]).fragment)["verify_email_token"][0]

    def block_resend(_settings, _recipient, _subject, body: str) -> None:
        links.append(next(part for part in body.split() if part.startswith("https://")))
        started.set()
        assert release.wait(timeout=5)

    monkeypatch.setattr(account_tokens, "_send_email", block_resend)
    resend = asyncio.create_task(
        account_tokens.send_email_verification(
            settings=settings(), user_id=user_id, email="listener@example.test"
        )
    )
    assert await asyncio.to_thread(started.wait, 5)
    pending_token = parse_qs(urlparse(links[1]).fragment)["verify_email_token"][0]

    assert await account_tokens.consume_token("email_verification", pending_token) is None
    assert await account_tokens.consume_token("email_verification", active_token) == {
        "kind": "email_verification",
        "user_id": str(user_id),
        "email": "listener@example.test",
    }

    release.set()
    await resend
    assert await account_tokens.consume_token("email_verification", pending_token) == {
        "kind": "email_verification",
        "user_id": str(user_id),
        "email": "listener@example.test",
    }


@pytest.mark.asyncio
async def test_older_successful_delivery_remains_valid_when_newer_delivery_fails(
    monkeypatch,
) -> None:
    redis = FakeRedis()
    links: list[str] = []
    user_id = uuid4()
    first_started = threading.Event()
    first_release = threading.Event()
    second_started = threading.Event()
    second_release = threading.Event()
    call_count = 0
    call_lock = threading.Lock()
    monkeypatch.setattr(account_tokens, "get_redis_client", lambda: redis)

    def ordered_delivery(_settings, _recipient, _subject, body: str) -> None:
        nonlocal call_count
        links.append(next(part for part in body.split() if part.startswith("https://")))
        with call_lock:
            call_count += 1
            call_number = call_count
        if call_number == 1:
            first_started.set()
            assert first_release.wait(timeout=5)
            return
        second_started.set()
        assert second_release.wait(timeout=5)
        raise ServiceUnavailableError("newer delivery failed")

    monkeypatch.setattr(account_tokens, "_send_email", ordered_delivery)
    first = asyncio.create_task(
        account_tokens.send_email_verification(
            settings=settings(), user_id=user_id, email="listener@example.test"
        )
    )
    assert await asyncio.to_thread(first_started.wait, 5)
    second = asyncio.create_task(
        account_tokens.send_email_verification(
            settings=settings(), user_id=user_id, email="listener@example.test"
        )
    )
    assert await asyncio.to_thread(second_started.wait, 5)

    first_release.set()
    await first
    second_release.set()
    with pytest.raises(ServiceUnavailableError):
        await second

    first_token = parse_qs(urlparse(links[0]).fragment)["verify_email_token"][0]
    assert await account_tokens.consume_token("email_verification", first_token) == {
        "kind": "email_verification",
        "user_id": str(user_id),
        "email": "listener@example.test",
    }


@pytest.mark.asyncio
async def test_finalized_newer_delivery_prevents_delayed_older_activation(monkeypatch) -> None:
    redis = FakeRedis()
    links: list[str] = []
    user_id = uuid4()
    first_started = threading.Event()
    first_release = threading.Event()
    calls = 0
    monkeypatch.setattr(account_tokens, "get_redis_client", lambda: redis)

    def ordered_delivery(_settings, _recipient, _subject, body: str) -> None:
        nonlocal calls
        links.append(next(part for part in body.split() if part.startswith("https://")))
        calls += 1
        if calls == 1:
            first_started.set()
            assert first_release.wait(timeout=5)

    monkeypatch.setattr(account_tokens, "_send_email", ordered_delivery)
    first = asyncio.create_task(account_tokens.send_password_reset(
        settings=settings(), user_id=user_id, email="listener@example.test"
    ))
    assert await asyncio.to_thread(first_started.wait, 5)
    await account_tokens.send_password_reset(
        settings=settings(), user_id=user_id, email="listener@example.test"
    )
    newer_token = parse_qs(urlparse(links[1]).fragment)["reset_password_token"][0]
    assert await account_tokens.consume_token("password_reset", newer_token) is not None
    newer_key = account_tokens._token_key("password_reset", newer_token)
    await redis.eval(account_tokens._ROLLBACK_TOKEN_SCRIPT, 1, newer_key)
    assert json.loads(redis.values[newer_key])["state"] == "finalized"

    first_release.set()
    with pytest.raises(ServiceUnavailableError):
        await first
    older_token = parse_qs(urlparse(links[0]).fragment)["reset_password_token"][0]
    assert await account_tokens.consume_token("password_reset", older_token) is None


@pytest.mark.asyncio
async def test_activation_retry_preserves_a_concurrently_claimed_token(monkeypatch) -> None:
    redis = FakeRedis()
    delivered: dict[str, str] = {}
    user_id = uuid4()
    monkeypatch.setattr(account_tokens, "get_redis_client", lambda: redis)
    monkeypatch.setattr(
        account_tokens,
        "_send_email",
        lambda _settings, _recipient, _subject, body: delivered.update(body=body),
    )

    await account_tokens.send_email_verification(
        settings=settings(), user_id=user_id, email="listener@example.test"
    )
    link = next(part for part in delivered["body"].split() if part.startswith("https://"))
    token = parse_qs(urlparse(link).fragment)["verify_email_token"][0]
    token_key = account_tokens._token_key("email_verification", token)
    digest = account_tokens._token_digest(token)
    claim = await account_tokens.claim_token("email_verification", token)
    assert claim is not None
    payload = json.loads(redis.values[token_key])

    retried = await redis.eval(
        account_tokens._ACTIVATE_TOKEN_SCRIPT,
        2,
        token_key,
        account_tokens._current_token_key("email_verification", user_id),
        payload["issue_version"],
        digest,
        account_tokens._current_token_prefix("email_verification"),
    )

    assert retried == 1
    assert json.loads(redis.values[token_key])["state"] == "claimed"
    assert await account_tokens.finalize_token_claim(
        "email_verification", token, claim.claim_id
    )


@pytest.mark.asyncio
async def test_cancellation_waits_for_delivery_before_token_cleanup(monkeypatch) -> None:
    redis = FakeRedis()
    links: list[str] = []
    user_id = uuid4()
    started = threading.Event()
    release = threading.Event()
    monkeypatch.setattr(account_tokens, "get_redis_client", lambda: redis)

    def blocking_delivery(_settings, _recipient, _subject, body: str) -> None:
        links.append(next(part for part in body.split() if part.startswith("https://")))
        started.set()
        assert release.wait(timeout=5)

    monkeypatch.setattr(account_tokens, "_send_email", blocking_delivery)
    delivery = asyncio.create_task(
        account_tokens.send_email_verification(
            settings=settings(), user_id=user_id, email="listener@example.test"
        )
    )
    assert await asyncio.to_thread(started.wait, 5)
    delivery.cancel()
    await asyncio.sleep(0)
    assert not delivery.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await delivery

    delivered_token = parse_qs(urlparse(links[0]).fragment)["verify_email_token"][0]
    assert await account_tokens.consume_token("email_verification", delivered_token) == {
        "kind": "email_verification",
        "user_id": str(user_id),
        "email": "listener@example.test",
    }


@pytest.mark.asyncio
async def test_redis_mutation_preserves_the_first_recorded_cancellation(monkeypatch) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    close_started = asyncio.Event()
    close_release = asyncio.Event()

    class DelayedRedis:
        async def eval(self, *_args):
            started.set()
            await release.wait()
            return [0]

        async def aclose(self) -> None:
            close_started.set()
            await close_release.wait()

    monkeypatch.setattr(account_tokens, "get_redis_client", DelayedRedis)
    mutation = asyncio.create_task(account_tokens._eval_idempotent_mutation("script", 0))
    await started.wait()
    mutation.cancel("first-cancellation")
    await asyncio.sleep(0)
    release.set()
    await close_started.wait()
    mutation.cancel("second-during-close")
    await asyncio.sleep(0)
    close_release.set()

    result, cancellation = await mutation

    assert result == [0]
    assert cancellation is not None
    assert cancellation.args == ("first-cancellation",)


@pytest.mark.asyncio
async def test_cancelled_compensation_has_an_internal_deadline() -> None:
    blocked = asyncio.Event()
    finished = asyncio.Event()

    async def compensation() -> None:
        try:
            await blocked.wait()
        finally:
            finished.set()

    await finish_cancelled_compensation(compensation(), timeout_seconds=0.01)
    await asyncio.wait_for(finished.wait(), timeout=0.2)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rollback_error",
    [
        ServiceUnavailableError("Account token service unavailable"),
        RuntimeError("unexpected rollback failure"),
    ],
)
async def test_claim_cancellation_survives_rollback_failure(
    monkeypatch, rollback_error: BaseException
) -> None:
    user_id = uuid4()
    payload = json.dumps(
        {
            "kind": "password_reset",
            "user_id": str(user_id),
            "email": "listener@example.test",
        }
    )
    calls = 0

    async def mutate(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return [1, payload], asyncio.CancelledError()
        raise rollback_error

    monkeypatch.setattr(account_tokens, "_eval_idempotent_mutation", mutate)

    task = asyncio.create_task(account_tokens.claim_token("password_reset", "r" * 43))
    with pytest.raises(asyncio.CancelledError):
        await task

    assert task.cancelled()
    assert calls == 2


@pytest.mark.asyncio
async def test_issuance_preserves_first_cancellation_during_outer_client_close(
    monkeypatch,
) -> None:
    activation_started = asyncio.Event()
    release_activation = asyncio.Event()
    outer_close_started = asyncio.Event()
    release_outer_close = asyncio.Event()

    class OuterRedis:
        async def eval(self, script: str, *_args):
            assert "account_token_prepare_v3" in script
            return [1, "1", ""]

        async def aclose(self) -> None:
            outer_close_started.set()
            await release_outer_close.wait()

    class ActivationRedis:
        async def eval(self, script: str, *_args):
            assert "account_token_activate_v3" in script
            activation_started.set()
            await release_activation.wait()
            return 1

        async def aclose(self) -> None:
            return None

    clients = iter((OuterRedis(), ActivationRedis()))
    monkeypatch.setattr(account_tokens, "get_redis_client", lambda: next(clients))
    monkeypatch.setattr(account_tokens, "_send_email", lambda *_args: None)
    issuance = asyncio.create_task(
        account_tokens.send_password_reset(
            settings=settings(), user_id=uuid4(), email="listener@example.test"
        )
    )
    await activation_started.wait()
    issuance.cancel("first-activation")
    await asyncio.sleep(0)
    release_activation.set()
    await outer_close_started.wait()
    issuance.cancel("second-outer-close")
    await asyncio.sleep(0)
    release_outer_close.set()

    with pytest.raises(asyncio.CancelledError) as captured:
        await issuance

    assert captured.value.args == ("first-activation",)


@pytest.mark.asyncio
async def test_timed_out_redis_compensation_does_not_leak_nested_tasks(monkeypatch) -> None:
    blocked = asyncio.Event()
    eval_finished = asyncio.Event()

    class BlockingRedis:
        async def eval(self, *_args):
            try:
                await blocked.wait()
            finally:
                eval_finished.set()

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(account_tokens, "get_redis_client", BlockingRedis)
    existing = set(asyncio.all_tasks())
    await finish_cancelled_compensation(
        account_tokens._eval_idempotent_mutation(
            "rollback", 0, abort_on_cancellation=True
        ),
        timeout_seconds=0.01,
    )
    await asyncio.wait_for(eval_finished.wait(), timeout=0.2)
    await asyncio.sleep(0)

    leaked = [task for task in asyncio.all_tasks() - existing if not task.done()]
    assert leaked == []


@pytest.mark.asyncio
async def test_password_reset_token_uses_short_ttl_and_fragment_link(monkeypatch) -> None:
    redis = FakeRedis()
    delivered: dict[str, str] = {}
    user_id = uuid4()
    monkeypatch.setattr(account_tokens, "get_redis_client", lambda: redis)
    monkeypatch.setattr(
        account_tokens,
        "_send_email",
        lambda _settings, recipient, subject, body: delivered.update(
            recipient=recipient, subject=subject, body=body
        ),
    )

    await account_tokens.send_password_reset(
        settings=settings(),
        user_id=user_id,
        email="listener@example.test",
    )

    assert set(redis.ttls.values()) == {account_tokens.PASSWORD_RESET_TTL_SECONDS}
    assert delivered["subject"] == "Reset your ORNA Atlas password"
    link = next(part for part in delivered["body"].split() if part.startswith("https://"))
    parsed = urlparse(link)
    assert parsed.query == ""
    token = parse_qs(parsed.fragment)["reset_password_token"][0]
    claims = await account_tokens.consume_token("password_reset", token)
    assert claims == {
        "kind": "password_reset",
        "user_id": str(user_id),
        "email": "listener@example.test",
    }


@pytest.mark.asyncio
async def test_unknown_redis_mutation_outcomes_are_repaired_idempotently(monkeypatch) -> None:
    class UnknownOutcomeRedis(FakeRedis):
        activation_failed = False
        claim_failed = False

        async def eval(self, script: str, numkeys: int, *args):
            result = await super().eval(script, numkeys, *args)
            if "account_token_activate_v3" in script and not self.activation_failed:
                self.activation_failed = True
                raise RedisError("activation response lost")
            if "account_token_claim_v1" in script and not self.claim_failed:
                self.claim_failed = True
                raise RedisError("claim response lost")
            return result

    redis = UnknownOutcomeRedis()
    links: list[str] = []
    user_id = uuid4()
    monkeypatch.setattr(account_tokens, "get_redis_client", lambda: redis)
    monkeypatch.setattr(
        account_tokens,
        "_send_email",
        lambda _settings, _recipient, _subject, body: links.append(
            next(part for part in body.split() if part.startswith("https://"))
        ),
    )

    await account_tokens.send_email_verification(
        settings=settings(), user_id=user_id, email="listener@example.test"
    )
    token = parse_qs(urlparse(links[0]).fragment)["verify_email_token"][0]
    claim = await account_tokens.claim_token("email_verification", token)

    assert claim is not None
    assert claim.claims["user_id"] == str(user_id)
    assert await account_tokens.rollback_token_claim(
        "email_verification", token, claim.claim_id
    ) is True
    assert await account_tokens.consume_token("email_verification", token) == {
        "kind": "email_verification",
        "user_id": str(user_id),
        "email": "listener@example.test",
    }


@pytest.mark.asyncio
async def test_cancelled_claim_rolls_back_an_executed_unknown_outcome(monkeypatch) -> None:
    class CancellableClaimRedis(FakeRedis):
        block_claim = False
        started = asyncio.Event()
        release = asyncio.Event()

        async def eval(self, script: str, numkeys: int, *args):
            result = await super().eval(script, numkeys, *args)
            if "account_token_claim_v1" in script and self.block_claim:
                self.block_claim = False
                self.started.set()
                await self.release.wait()
            return result

    redis = CancellableClaimRedis()
    links: list[str] = []
    user_id = uuid4()
    monkeypatch.setattr(account_tokens, "get_redis_client", lambda: redis)
    monkeypatch.setattr(
        account_tokens,
        "_send_email",
        lambda _settings, _recipient, _subject, body: links.append(
            next(part for part in body.split() if part.startswith("https://"))
        ),
    )
    await account_tokens.send_email_verification(
        settings=settings(), user_id=user_id, email="listener@example.test"
    )
    token = parse_qs(urlparse(links[0]).fragment)["verify_email_token"][0]

    redis.block_claim = True
    claiming = asyncio.create_task(account_tokens.claim_token("email_verification", token))
    await asyncio.wait_for(redis.started.wait(), timeout=2)
    claiming.cancel()
    redis.release.set()
    with pytest.raises(asyncio.CancelledError):
        await claiming

    assert await account_tokens.consume_token("email_verification", token) == {
        "kind": "email_verification",
        "user_id": str(user_id),
        "email": "listener@example.test",
    }


@pytest.mark.asyncio
async def test_partial_redis_issuance_failure_removes_orphaned_token_payload(monkeypatch) -> None:
    class FailingPointerRedis(FakeRedis):
        async def eval(self, script: str, numkeys: int, *args):
            if "account_token_prepare_v3" in script:
                keys = list(args[:numkeys])
                values = list(args[numkeys:])
                token_key = keys[0]
                self.values[token_key] = str(values[0])
                raise RedisError("pointer unavailable")
            return await super().eval(script, numkeys, *args)

    redis = FailingPointerRedis()
    monkeypatch.setattr(account_tokens, "get_redis_client", lambda: redis)
    monkeypatch.setattr(account_tokens, "_send_email", lambda *_args: None)

    with pytest.raises(ServiceUnavailableError):
        await account_tokens.send_password_reset(
            settings=settings(),
            user_id=uuid4(),
            email="listener@example.test",
        )

    assert not any(key.startswith("auth:password_reset:") for key in redis.values)


@pytest.mark.asyncio
async def test_unverified_account_requests_verification_for_authenticated_user(monkeypatch) -> None:
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        email="listener@example.test",
        email_verified_at=None,
        is_active=True,
    )
    load_user = AsyncMock(return_value=user)
    send = AsyncMock()
    monkeypatch.setattr(service.users_repository, "get_by_id", load_user)
    monkeypatch.setattr(service.account_tokens, "send_email_verification", send)
    configured = settings()
    monkeypatch.setattr(service, "get_settings", lambda: configured)

    await service.request_email_verification(AsyncMock(), user_id)

    send.assert_awaited_once_with(
        settings=configured,
        user_id=user_id,
        email="listener@example.test",
    )


@pytest.mark.asyncio
async def test_email_verification_confirmation_marks_matching_user_and_audits(monkeypatch) -> None:
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        email="listener@example.test",
        email_verified_at=None,
        is_active=True,
    )
    session = AsyncMock()
    finalize_claim = AsyncMock(return_value=True)
    monkeypatch.setattr(
        service.account_tokens,
        "claim_token",
        AsyncMock(return_value=SimpleNamespace(
            claim_id="claim-1",
            claims={
                "kind": "email_verification",
                "user_id": str(user_id),
                "email": "listener@example.test",
            },
        )),
    )
    monkeypatch.setattr(service.account_tokens, "finalize_token_claim", finalize_claim)
    monkeypatch.setattr(
        service.users_repository, "get_by_id_for_update", AsyncMock(return_value=user)
    )
    audit = AsyncMock()
    monkeypatch.setattr(service, "add_audit_event", audit)

    verified = await service.confirm_email_verification(session, "v" * 43)

    assert verified is user
    assert isinstance(user.email_verified_at, datetime)
    assert user.email_verified_at.tzinfo is UTC
    audit.assert_awaited_once_with(
        session,
        event_type="auth.email_verified",
        subject_type="user",
        subject_id=str(user_id),
        actor_user_id=user_id,
    )
    session.commit.assert_awaited_once()
    finalize_claim.assert_awaited_once_with(
        "email_verification", "v" * 43, "claim-1"
    )


@pytest.mark.asyncio
async def test_unknown_verification_commit_finalizes_token_claim(monkeypatch) -> None:
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        email="listener@example.test",
        email_verified_at=None,
        is_active=True,
    )
    claim = SimpleNamespace(
        claim_id="claim-1",
        claims={
            "kind": "email_verification",
            "user_id": str(user_id),
            "email": "listener@example.test",
        },
    )
    session = AsyncMock()
    session.commit.side_effect = RuntimeError("database unavailable")
    session.rollback.side_effect = RuntimeError("rollback unavailable")
    claim_token = AsyncMock(return_value=claim)
    rollback_claim = AsyncMock()
    finalize_claim = AsyncMock()
    monkeypatch.setattr(service.account_tokens, "claim_token", claim_token, raising=False)
    monkeypatch.setattr(
        service.account_tokens, "rollback_token_claim", rollback_claim, raising=False
    )
    monkeypatch.setattr(
        service.account_tokens, "finalize_token_claim", finalize_claim, raising=False
    )
    monkeypatch.setattr(
        service.account_tokens,
        "consume_token",
        AsyncMock(side_effect=AssertionError("confirmation must claim before commit")),
    )
    monkeypatch.setattr(
        service.users_repository, "get_by_id_for_update", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(service, "add_audit_event", AsyncMock())

    with pytest.raises(RuntimeError, match="database unavailable"):
        await service.confirm_email_verification(session, "v" * 43)

    session.rollback.assert_awaited_once()
    rollback_claim.assert_not_awaited()
    finalize_claim.assert_awaited_once_with(
        "email_verification", "v" * 43, "claim-1"
    )


@pytest.mark.asyncio
async def test_precommit_verification_failure_releases_token_claim(monkeypatch) -> None:
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        email="listener@example.test",
        email_verified_at=None,
        is_active=True,
    )
    claim = SimpleNamespace(
        claim_id="claim-precommit",
        claims={"user_id": str(user_id), "email": user.email},
    )
    session = AsyncMock()
    rollback_claim = AsyncMock()
    finalize_claim = AsyncMock()
    monkeypatch.setattr(service.account_tokens, "claim_token", AsyncMock(return_value=claim))
    monkeypatch.setattr(service.account_tokens, "rollback_token_claim", rollback_claim)
    monkeypatch.setattr(service.account_tokens, "finalize_token_claim", finalize_claim)
    monkeypatch.setattr(
        service.users_repository, "get_by_id_for_update", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(
        service, "add_audit_event", AsyncMock(side_effect=RuntimeError("audit failed"))
    )

    with pytest.raises(RuntimeError, match="audit failed"):
        await service.confirm_email_verification(session, "v" * 43)

    session.rollback.assert_awaited_once()
    rollback_claim.assert_awaited_once_with(
        "email_verification", "v" * 43, "claim-precommit"
    )
    finalize_claim.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_password_reset_request_is_a_noop_without_email(monkeypatch) -> None:
    session = AsyncMock()
    monkeypatch.setattr(service.users_repository, "get_by_email", AsyncMock(return_value=None))
    send = AsyncMock()
    monkeypatch.setattr(service.account_tokens, "send_password_reset", send)

    await service.request_password_reset(session, "missing@example.test")

    send.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_password_reset_delivery_log_omits_exception_email(monkeypatch, caplog) -> None:
    submitted_email = "victim@example.test"
    context = AsyncMock()
    context.__aenter__.return_value = object()
    monkeypatch.setattr(service, "AsyncSessionLocal", MagicMock(return_value=context))
    monkeypatch.setattr(
        service,
        "request_password_reset",
        AsyncMock(side_effect=RuntimeError(f"parameters: ({submitted_email!r},)")),
    )

    with caplog.at_level("ERROR"):
        await service.deliver_password_reset(submitted_email)

    assert "Password reset delivery failed" in caplog.text
    assert submitted_email not in caplog.text


@pytest.mark.asyncio
async def test_password_reset_changes_hash_revokes_sessions_and_audits(monkeypatch) -> None:
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        email="listener@example.test",
        password_hash="old-hash",
        is_active=True,
    )
    session = AsyncMock()
    finalize_claim = AsyncMock(return_value=True)
    monkeypatch.setattr(
        service.account_tokens,
        "claim_token",
        AsyncMock(return_value=SimpleNamespace(
            claim_id="claim-2",
            claims={
                "kind": "password_reset",
                "user_id": str(user_id),
                "email": "listener@example.test",
            },
        )),
    )
    monkeypatch.setattr(service.account_tokens, "finalize_token_claim", finalize_claim)
    monkeypatch.setattr(
        service.users_repository, "get_by_id_for_update", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(service, "hash_password", lambda password: f"hashed:{password}")
    revoke_all = AsyncMock()
    monkeypatch.setattr(service.repository, "revoke_all_for_user", revoke_all)
    audit = AsyncMock()
    monkeypatch.setattr(service, "add_audit_event", audit)

    reset_user = await service.confirm_password_reset(
        session,
        "r" * 43,
        "new secure password",
    )

    assert reset_user is user
    assert user.password_hash == "hashed:new secure password"
    revoke_all.assert_awaited_once_with(session, user_id)
    audit.assert_awaited_once_with(
        session,
        event_type="auth.password_reset",
        subject_type="user",
        subject_id=str(user_id),
        actor_user_id=user_id,
    )
    session.commit.assert_awaited_once()
    finalize_claim.assert_awaited_once_with("password_reset", "r" * 43, "claim-2")


@pytest.mark.asyncio
async def test_unknown_password_reset_commit_finalizes_and_reports_unavailable(
    monkeypatch,
) -> None:
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        email="listener@example.test",
        password_hash="old-hash",
        is_active=True,
    )
    claim = SimpleNamespace(
        claim_id="claim-unknown",
        claims={
            "kind": "password_reset",
            "user_id": str(user_id),
            "email": user.email,
        },
    )
    session = AsyncMock()
    session.commit.side_effect = RuntimeError("commit outcome unknown")
    finalize_claim = AsyncMock(return_value=True)
    monkeypatch.setattr(service.account_tokens, "claim_token", AsyncMock(return_value=claim))
    monkeypatch.setattr(service.account_tokens, "finalize_token_claim", finalize_claim)
    monkeypatch.setattr(
        service.users_repository, "get_by_id_for_update", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(service, "hash_password", lambda password: f"hashed:{password}")
    monkeypatch.setattr(service.repository, "revoke_all_for_user", AsyncMock())
    monkeypatch.setattr(service, "add_audit_event", AsyncMock())

    with pytest.raises(
        ServiceUnavailableError, match="Password reset outcome is unavailable"
    ):
        await service.confirm_password_reset(
            session,
            "r" * 43,
            "new secure password",
        )

    session.rollback.assert_awaited_once()
    finalize_claim.assert_awaited_once_with(
        "password_reset", "r" * 43, "claim-unknown"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["precommit", "commit"])
async def test_cancelled_email_verification_preserves_original_during_compensation(
    monkeypatch, phase: str
) -> None:
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        email="listener@example.test",
        email_verified_at=None,
        is_active=True,
    )
    claim = SimpleNamespace(
        claim_id="email-claim-cancelled",
        claims={
            "kind": "email_verification",
            "user_id": str(user_id),
            "email": user.email,
        },
    )
    original = asyncio.CancelledError("original")
    second = asyncio.CancelledError("second")
    session = AsyncMock()
    session.rollback.side_effect = second
    get_user = AsyncMock(return_value=user)
    if phase == "precommit":
        get_user.side_effect = original
    else:
        session.commit.side_effect = original
    rollback_claim = AsyncMock(return_value=True)
    finalize_claim = AsyncMock(return_value=True)
    monkeypatch.setattr(service.account_tokens, "claim_token", AsyncMock(return_value=claim))
    monkeypatch.setattr(service.account_tokens, "rollback_token_claim", rollback_claim)
    monkeypatch.setattr(service.account_tokens, "finalize_token_claim", finalize_claim)
    monkeypatch.setattr(service.users_repository, "get_by_id_for_update", get_user)
    monkeypatch.setattr(service, "add_audit_event", AsyncMock())

    with pytest.raises(asyncio.CancelledError) as captured:
        await service.confirm_email_verification(session, "v" * 43)

    assert captured.value is original
    if phase == "precommit":
        rollback_claim.assert_awaited_once_with(
            "email_verification", "v" * 43, "email-claim-cancelled"
        )
        finalize_claim.assert_not_awaited()
    else:
        finalize_claim.assert_awaited_once_with(
            "email_verification", "v" * 43, "email-claim-cancelled"
        )
        rollback_claim.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_password_reset_commit_preserves_original_during_compensation(
    monkeypatch,
) -> None:
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        email="listener@example.test",
        password_hash="old-hash",
        is_active=True,
    )
    claim = SimpleNamespace(
        claim_id="claim-cancelled",
        claims={
            "kind": "password_reset",
            "user_id": str(user_id),
            "email": user.email,
        },
    )
    original = asyncio.CancelledError("original")
    second = asyncio.CancelledError("second")
    session = AsyncMock()
    session.commit.side_effect = original
    session.rollback.side_effect = second
    finalize_claim = AsyncMock(return_value=True)
    monkeypatch.setattr(service.account_tokens, "claim_token", AsyncMock(return_value=claim))
    monkeypatch.setattr(service.account_tokens, "finalize_token_claim", finalize_claim)
    monkeypatch.setattr(
        service.users_repository, "get_by_id_for_update", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(service, "hash_password", lambda password: f"hashed:{password}")
    monkeypatch.setattr(service.repository, "revoke_all_for_user", AsyncMock())
    monkeypatch.setattr(service, "add_audit_event", AsyncMock())

    with pytest.raises(asyncio.CancelledError) as captured:
        await service.confirm_password_reset(
            session,
            "r" * 43,
            "new secure password",
        )

    assert captured.value is original
    finalize_claim.assert_awaited_once_with(
        "password_reset", "r" * 43, "claim-cancelled"
    )


def test_recovery_openapi_is_post_body_only_and_exposes_verification_status() -> None:
    from orna_atlas.app.main import app

    schema = app.openapi()
    paths = schema["paths"]
    expected = {
        "/api/v1/auth/email-verification/request",
        "/api/v1/auth/email-verification/confirm",
        "/api/v1/auth/password-reset/request",
        "/api/v1/auth/password-reset/confirm",
    }
    assert expected <= paths.keys()
    for path in expected:
        assert set(paths[path]) == {"post"}
        operation = paths[path]["post"]
        if path.endswith("/confirm") or path.endswith("password-reset/request"):
            assert operation["requestBody"]["required"] is True
        if path.endswith("/confirm"):
            response_400 = operation["responses"]["400"]
            assert response_400["content"]["application/json"]["schema"] == {
                "$ref": "#/components/schemas/AccountRecoveryError"
            }
            assert "422" not in operation["responses"]
    verification_request = paths["/api/v1/auth/email-verification/request"]["post"]
    assert verification_request["security"] == [
        {"HTTPBearer": []},
        {"APIKeyCookie": []},
    ]
    assert not any(
        parameter["in"] in {"header", "cookie"}
        and parameter["name"] in {"authorization", "orna_access"}
        for parameter in verification_request.get("parameters", [])
    )
    user_schema = schema["components"]["schemas"]["UserRead"]
    assert user_schema["properties"]["email_verified"] == {
        "type": "boolean",
        "title": "Email Verified",
    }
    assert "email_verified" in user_schema["required"]


def test_optional_auth_openapi_allows_anonymous_sessions_without_weakening_auth() -> None:
    from orna_atlas.app.main import app

    paths = app.openapi()["paths"]
    for path, method in (
        ("/api/v1/sessions", "get"),
        ("/api/v1/sessions/{locator}", "get"),
        ("/api/v1/sessions/{session_id}/playback-grants", "post"),
        ("/api/v1/collections", "get"),
        ("/api/v1/collections/{slug}", "get"),
        ("/api/v1/search", "get"),
        ("/api/v1/atlas/points", "get"),
    ):
        assert paths[path][method]["security"] == [
            {},
            {"HTTPBearer": []},
            {"APIKeyCookie": []},
        ]
    assert paths["/api/v1/auth/email-verification/request"]["post"]["security"] == [
        {"HTTPBearer": []},
        {"APIKeyCookie": []},
    ]


@pytest.mark.asyncio
async def test_optional_auth_requires_refresh_when_only_refresh_cookie_remains() -> None:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/atlas/points",
            "headers": [(b"cookie", f"{REFRESH_COOKIE}=refresh-token".encode())],
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_optional_catalog_user(request, current_user=None)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Access authentication requires refresh"


def test_refresh_cookie_is_scoped_for_catalog_recovery() -> None:
    response = Response()

    router._set_auth_cookies(
        response,
        cast(TokenResponse, SimpleNamespace(access_token="access-token")),
        "refresh-token",
    )

    refresh_cookie = next(
        value
        for value in response.headers.getlist("set-cookie")
        if value.startswith(f"{REFRESH_COOKIE}=")
    )
    assert "Path=/" in refresh_cookie
    assert "HttpOnly" in refresh_cookie


@pytest.mark.asyncio
async def test_logout_clears_root_scoped_refresh_cookie(monkeypatch) -> None:
    logout = AsyncMock()
    monkeypatch.setattr(router.service, "logout", logout)
    response = Response()
    session = AsyncMock()

    await router.logout(response, "refresh-token", session)

    logout.assert_awaited_once_with(session, "refresh-token")
    refresh_cookie = next(
        value
        for value in response.headers.getlist("set-cookie")
        if value.startswith(f"{REFRESH_COOKIE}=")
    )
    assert "Path=/" in refresh_cookie
    assert "Max-Age=0" in refresh_cookie


@pytest.mark.asyncio
async def test_invalid_refresh_clears_root_scoped_auth_cookies(monkeypatch) -> None:
    monkeypatch.setattr(
        router.service,
        "rotate_refresh_token",
        AsyncMock(side_effect=AuthenticationError("Invalid refresh token")),
    )

    result = cast(Response, await router.refresh(Response(), "revoked-token", AsyncMock()))

    assert result.status_code == 401
    assert result.headers["Cache-Control"] == "no-store"
    refresh_cookie = next(
        value
        for value in result.headers.getlist("set-cookie")
        if value.startswith(f"{REFRESH_COOKIE}=")
    )
    assert "Path=/" in refresh_cookie
    assert "Max-Age=0" in refresh_cookie


@pytest.mark.asyncio
async def test_password_reset_request_schedules_delivery_outside_response_path(monkeypatch) -> None:
    deliver = AsyncMock()
    monkeypatch.setattr(router.service, "deliver_password_reset", deliver)
    background_tasks = BackgroundTasks()
    response = Response()

    result = await router.request_password_reset(
        PasswordResetRequest(email="listener@example.com"),
        response,
        background_tasks,
    )

    assert result.accepted is True
    assert response.headers["Cache-Control"] == "no-store"
    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    assert task.func is deliver
    assert task.args == ("listener@example.com",)
    deliver.assert_not_awaited()


async def _no_rate_limit() -> None:
    return None


async def _fake_session():
    yield object()


def test_recovery_error_response_is_never_cacheable(monkeypatch) -> None:
    async def invalid_token(*_args, **_kwargs):
        raise AuthenticationError("invalid")

    monkeypatch.setattr(service, "confirm_email_verification", invalid_token)
    app = create_app()
    app.dependency_overrides[auth_rate_limit] = _no_rate_limit
    app.dependency_overrides[get_db_session] = _fake_session

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/email-verification/confirm",
            json={"token": "v" * 43},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid or expired email verification token"}
    assert response.headers["Cache-Control"] == "no-store"


def test_ambiguous_password_reset_clears_http_only_auth_cookies(monkeypatch) -> None:
    async def unavailable(*_args, **_kwargs):
        raise ServiceUnavailableError("Password reset outcome is unavailable")

    monkeypatch.setattr(service, "confirm_password_reset", unavailable)
    app = create_app()
    app.dependency_overrides[auth_rate_limit] = _no_rate_limit
    app.dependency_overrides[get_db_session] = _fake_session

    with TestClient(app, raise_server_exceptions=False) as client:
        client.cookies.set(ACCESS_COOKIE, "old-access", path="/")
        client.cookies.set(REFRESH_COOKIE, "old-refresh", path="/")
        response = client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"token": "r" * 43, "password": "new secure password"},
        )

    assert response.status_code == 503
    assert response.headers["Cache-Control"] == "no-store"
    set_cookies = response.headers.get_list("set-cookie")
    assert any(
        value.startswith(f"{ACCESS_COOKIE}=") and "Max-Age=0" in value
        for value in set_cookies
    )
    assert any(
        value.startswith(f"{REFRESH_COOKIE}=") and "Max-Age=0" in value
        for value in set_cookies
    )


def test_malformed_recovery_confirmation_uses_the_same_sanitized_contract() -> None:
    app = create_app()
    app.dependency_overrides[auth_rate_limit] = _no_rate_limit
    app.dependency_overrides[get_db_session] = _fake_session

    with TestClient(app) as client:
        verification = client.post(
            "/api/v1/auth/email-verification/confirm",
            json={"token": "short"},
        )
        password_reset = client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"token": "short", "password": "new secure password"},
        )

    assert verification.status_code == 400
    assert verification.json() == {"detail": "Invalid or expired email verification token"}
    assert password_reset.status_code == 400
    assert password_reset.json() == {"detail": "Invalid or expired password reset token"}
    assert verification.headers["Cache-Control"] == "no-store"
    assert password_reset.headers["Cache-Control"] == "no-store"


def test_password_reset_confirmation_clears_authentication_cookies(monkeypatch) -> None:
    monkeypatch.setattr(service, "confirm_password_reset", AsyncMock())
    app = create_app()
    app.dependency_overrides[auth_rate_limit] = _no_rate_limit
    app.dependency_overrides[get_db_session] = _fake_session

    with TestClient(app) as client:
        client.cookies.set(ACCESS_COOKIE, "old-access")
        client.cookies.set(REFRESH_COOKIE, "old-refresh", path="/")
        response = client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"token": "r" * 43, "password": "new secure password"},
        )

    set_cookies = response.headers.get_list("set-cookie")
    assert response.status_code == 200
    assert response.json() == {"status": "password_reset"}
    assert response.headers["Cache-Control"] == "no-store"
    assert any(cookie.startswith(f"{ACCESS_COOKIE}=") and "Max-Age=0" in cookie for cookie in set_cookies)
    assert any(cookie.startswith(f"{REFRESH_COOKIE}=") and "Max-Age=0" in cookie for cookie in set_cookies)


def test_unauthenticated_verification_request_is_never_cacheable() -> None:
    app = create_app()
    app.dependency_overrides[auth_rate_limit] = _no_rate_limit
    app.dependency_overrides[get_db_session] = _fake_session

    with TestClient(app) as client:
        response = client.post("/api/v1/auth/email-verification/request")

    assert response.status_code == 401
    assert response.headers["Cache-Control"] == "no-store"
