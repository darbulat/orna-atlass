import base64
import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from orna_atlas.app.core.config import Settings, get_settings
from orna_atlas.app.integrations.resend import (
    ResendClient,
    ResendProviderError,
    verify_webhook,
)
from orna_atlas.app.main import app as atlas_app
from orna_atlas.app.modules.support import router as support_router


SIGNING_KEY = b"test-resend-webhook-key"
WEBHOOK_SECRET = "whsec_" + base64.urlsafe_b64encode(SIGNING_KEY).decode().rstrip("=")


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "RESEND_API_KEY": "re_test_key",
        "RESEND_WEBHOOK_SECRET": WEBHOOK_SECRET,
        "SUPPORT_FORWARD_TO": "owner@example.test",
        "SUPPORT_FROM_EMAIL": "ORNA Support <support@orna.land>",
    }
    values.update(overrides)
    return Settings.model_validate(values)


def _signed_headers(
    payload: bytes, *, message_id: str = "msg_test", timestamp: int | None = None
) -> dict[str, str]:
    timestamp_value = str(timestamp if timestamp is not None else int(time.time()))
    signed_content = b".".join((message_id.encode(), timestamp_value.encode(), payload))
    signature = base64.b64encode(
        hmac.new(SIGNING_KEY, signed_content, hashlib.sha256).digest()
    ).decode()
    return {
        "svix-id": message_id,
        "svix-timestamp": timestamp_value,
        "svix-signature": f"v1,{signature}",
        "content-type": "application/json",
    }


def _app(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.include_router(support_router.router, prefix="/api/v1")
    app.dependency_overrides[get_settings] = lambda: settings
    return app


def test_support_webhook_is_registered_as_hidden_post_only_route() -> None:
    settings = _settings(
        RESEND_API_KEY=None,
        RESEND_WEBHOOK_SECRET=None,
        SUPPORT_FORWARD_TO=None,
    )
    atlas_app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(atlas_app)
    try:
        post_response = client.post("/api/v1/support/webhooks/resend", content=b"{}")
        get_response = client.get("/api/v1/support/webhooks/resend")
        schema = client.get("/openapi.json").json()
    finally:
        atlas_app.dependency_overrides.pop(get_settings, None)

    assert post_response.status_code == 503
    assert get_response.status_code == 405
    assert "/api/v1/support/webhooks/resend" not in schema["paths"]


@pytest.mark.parametrize(
    "configured",
    [
        {"RESEND_API_KEY": "re_test_key"},
        {"RESEND_WEBHOOK_SECRET": WEBHOOK_SECRET},
        {"SUPPORT_FORWARD_TO": "owner@example.test"},
    ],
)
def test_support_forwarding_configuration_is_all_or_none(
    configured: dict[str, str],
) -> None:
    with pytest.raises(ValidationError, match="must be configured together"):
        Settings.model_validate({"_env_file": None, **configured})


@pytest.mark.parametrize(
    "secret",
    [
        "AAAA",
        "whsec_AAAA",
        "whsec_%%%",
    ],
)
def test_support_forwarding_rejects_malformed_or_weak_webhook_secret(secret: str) -> None:
    with pytest.raises(ValidationError, match="RESEND_WEBHOOK_SECRET"):
        Settings.model_validate(
            {
                "_env_file": None,
                "RESEND_API_KEY": "re_test_key",
                "RESEND_WEBHOOK_SECRET": secret,
                "SUPPORT_FORWARD_TO": "owner@example.test",
            }
        )


def test_signed_support_email_is_forwarded_once(monkeypatch) -> None:
    payload = json.dumps(
        {
            "type": "email.received",
            "data": {"email_id": "email_123", "to": ["SUPPORT@ORNA.LAND"]},
        },
        separators=(",", ":"),
    ).encode()
    forward = AsyncMock()
    client_factory = MagicMock(return_value=SimpleNamespace(forward_received_email=forward))
    monkeypatch.setattr(support_router, "ResendClient", client_factory)

    response = TestClient(_app(_settings())).post(
        "/api/v1/support/webhooks/resend",
        content=payload,
        headers=_signed_headers(payload, message_id="msg_delivery_1"),
    )

    assert response.status_code == 204
    client_factory.assert_called_once()
    forward.assert_awaited_once_with(
        email_id="email_123",
        to="owner@example.test",
        from_email="ORNA Support <support@orna.land>",
        idempotency_key="support-msg_delivery_1",
    )


def test_signed_non_support_email_is_acknowledged_without_resend_api_call(monkeypatch) -> None:
    payload = json.dumps(
        {
            "type": "email.received",
            "data": {"email_id": "email_ignored", "to": ["accounts@orna.land"]},
        }
    ).encode()
    client_factory = AsyncMock()
    monkeypatch.setattr(support_router, "ResendClient", client_factory)

    response = TestClient(_app(_settings())).post(
        "/api/v1/support/webhooks/resend",
        content=payload,
        headers=_signed_headers(payload),
    )

    assert response.status_code == 204
    client_factory.assert_not_called()


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {
            "svix-id": "msg_invalid",
            "svix-timestamp": str(int(time.time())),
            "svix-signature": "v1,invalid",
        },
    ],
)
def test_missing_or_invalid_signature_is_rejected(headers: dict[str, str], monkeypatch) -> None:
    payload = (
        b'{"type":"email.received","data":{"email_id":"email_123","to":["support@orna.land"]}}'
    )
    client_factory = AsyncMock()
    monkeypatch.setattr(support_router, "ResendClient", client_factory)

    response = TestClient(_app(_settings())).post(
        "/api/v1/support/webhooks/resend", content=payload, headers=headers
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid webhook"}
    client_factory.assert_not_called()


def test_signed_malformed_payload_is_rejected(monkeypatch) -> None:
    payload = b"not-json"
    client_factory = MagicMock()
    monkeypatch.setattr(support_router, "ResendClient", client_factory)

    response = TestClient(_app(_settings())).post(
        "/api/v1/support/webhooks/resend",
        content=payload,
        headers=_signed_headers(payload),
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid webhook"}
    client_factory.assert_not_called()


def test_resend_api_failure_is_not_acknowledged(monkeypatch) -> None:
    payload = json.dumps(
        {
            "type": "email.received",
            "data": {"email_id": "email_retry", "to": ["support@orna.land"]},
        }
    ).encode()
    forward = AsyncMock(
        side_effect=httpx.ConnectError(
            "resend unavailable",
            request=httpx.Request("GET", "https://api.resend.com/emails/receiving/email_retry"),
        )
    )
    monkeypatch.setattr(
        support_router,
        "ResendClient",
        MagicMock(return_value=SimpleNamespace(forward_received_email=forward)),
    )

    response = TestClient(_app(_settings()), raise_server_exceptions=False).post(
        "/api/v1/support/webhooks/resend",
        content=payload,
        headers=_signed_headers(payload),
    )

    assert response.status_code == 500
    forward.assert_awaited_once()


def test_unconfigured_forwarding_fails_closed_before_signature_processing() -> None:
    settings = _settings(
        RESEND_API_KEY=None,
        RESEND_WEBHOOK_SECRET=None,
        SUPPORT_FORWARD_TO=None,
    )

    response = TestClient(_app(settings)).post("/api/v1/support/webhooks/resend", content=b"{}")

    assert response.status_code == 503
    assert response.json() == {"detail": "Support email forwarding is not configured"}


def test_webhook_verification_rejects_stale_delivery() -> None:
    payload = b'{"type":"email.received"}'
    headers = _signed_headers(payload, timestamp=int(time.time()) - 301)

    with pytest.raises(ValueError, match="outside the allowed window"):
        verify_webhook(
            payload,
            message_id=headers["svix-id"],
            timestamp=headers["svix-timestamp"],
            signature=headers["svix-signature"],
            secret=WEBHOOK_SECRET,
        )


def test_webhook_verification_rejects_malformed_secret_even_with_matching_empty_key() -> None:
    payload = b'{"type":"email.received"}'
    timestamp = str(int(time.time()))
    message_id = "msg_malformed_secret"
    signed_content = b".".join((message_id.encode(), timestamp.encode(), payload))
    empty_key_signature = base64.b64encode(
        hmac.new(b"", signed_content, hashlib.sha256).digest()
    ).decode()

    with pytest.raises(ValueError, match="Invalid webhook secret"):
        verify_webhook(
            payload,
            message_id=message_id,
            timestamp=timestamp,
            signature=f"v1,{empty_key_signature}",
            secret="whsec_%%%",
        )


@pytest.mark.asyncio
async def test_attachment_download_does_not_receive_resend_api_key(monkeypatch) -> None:
    observed_authorization: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed_authorization[request.url.host] = request.headers.get("authorization")
        if request.url.path == "/emails/receiving/email_123":
            return httpx.Response(200, json={"text": "Body"})
        if request.url.path == "/emails/receiving/email_123/attachments":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "att_external",
                            "filename": "recording.txt",
                            "content_type": "text/plain",
                            "download_url": "https://attachments.example.test/object",
                        }
                    ]
                },
            )
        if request.url.host == "attachments.example.test":
            return httpx.Response(200, content=b"attachment")
        if request.url.path == "/emails":
            return httpx.Response(200, json={"id": "sent_1"})
        return httpx.Response(404)

    real_async_client = httpx.AsyncClient

    def async_client(**kwargs: Any) -> httpx.AsyncClient:
        return real_async_client(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr("orna_atlas.app.integrations.resend.httpx.AsyncClient", async_client)

    await ResendClient(_settings()).forward_received_email(
        email_id="email_123",
        to="owner@example.test",
        from_email="ORNA Support <support@orna.land>",
        idempotency_key="support-msg_123",
    )

    assert observed_authorization["api.resend.com"] == "Bearer re_test_key"
    assert observed_authorization["attachments.example.test"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("download_status", [302, 403])
async def test_attachment_download_failure_does_not_expose_signed_url(
    monkeypatch, download_status: int
) -> None:
    signed_url = "https://attachments.example.test/object?token=private-download-token"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/emails/receiving/email_123":
            return httpx.Response(200, json={"text": "Body"})
        if request.url.path == "/emails/receiving/email_123/attachments":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "att_external",
                            "filename": "recording.txt",
                            "content_type": "text/plain",
                            "download_url": signed_url,
                        }
                    ]
                },
            )
        if request.url.host == "attachments.example.test":
            return httpx.Response(download_status)
        return httpx.Response(404)

    real_async_client = httpx.AsyncClient

    def async_client(**kwargs: Any) -> httpx.AsyncClient:
        return real_async_client(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr("orna_atlas.app.integrations.resend.httpx.AsyncClient", async_client)

    with pytest.raises(ResendProviderError) as error:
        await ResendClient(_settings()).forward_received_email(
            email_id="email_123",
            to="owner@example.test",
            from_email="ORNA Support <support@orna.land>",
            idempotency_key="support-msg_123",
        )

    assert "private-download-token" not in str(error.value)
    assert error.value.__cause__ is None
    assert error.value.__context__ is None


@pytest.mark.asyncio
async def test_resend_client_forwards_body_sender_and_attachments(monkeypatch) -> None:
    email_response = httpx.Response(
        200,
        json={
            "subject": "Need help",
            "from": "Listener <listener@example.test>",
            "text": "Original plain text",
            "html": "<p>Original HTML</p>",
        },
        request=httpx.Request("GET", "https://api.resend.com/emails/receiving/email_123"),
    )
    attachments_response = httpx.Response(
        200,
        json={
            "data": [
                {
                    "id": "att_1",
                    "filename": "recording.txt",
                    "content_type": "text/plain",
                    "content_id": "<cid-1>",
                    "download_url": "https://api.resend.com/download/att_1",
                }
            ]
        },
        request=httpx.Request(
            "GET", "https://api.resend.com/emails/receiving/email_123/attachments"
        ),
    )
    download_response = httpx.Response(
        200,
        content=b"attachment bytes",
        request=httpx.Request("GET", "https://api.resend.com/download/att_1"),
    )
    send_response = httpx.Response(
        200,
        json={"id": "sent_1"},
        request=httpx.Request("POST", "https://api.resend.com/emails"),
    )
    get = AsyncMock(side_effect=[email_response, attachments_response, download_response])
    post = AsyncMock(return_value=send_response)
    context = AsyncMock()
    context.__aenter__.return_value = SimpleNamespace(get=get, post=post)
    constructor_args: dict[str, object] = {}

    def async_client(**kwargs: object) -> AsyncMock:
        constructor_args.update(kwargs)
        return context

    monkeypatch.setattr("orna_atlas.app.integrations.resend.httpx.AsyncClient", async_client)

    await ResendClient(_settings()).forward_received_email(
        email_id="email_123",
        to="owner@example.test",
        from_email="ORNA Support <support@orna.land>",
        idempotency_key="support-msg_123",
    )

    assert constructor_args["base_url"] == "https://api.resend.com"
    assert constructor_args["headers"] == {"Authorization": "Bearer re_test_key"}
    post.assert_awaited_once_with(
        "/emails",
        json={
            "from": "ORNA Support <support@orna.land>",
            "to": ["owner@example.test"],
            "subject": "Need help",
            "html": "<p>Original HTML</p>",
            "text": "Original plain text",
            "reply_to": "Listener <listener@example.test>",
            "attachments": [
                {
                    "filename": "recording.txt",
                    "content": base64.b64encode(b"attachment bytes").decode(),
                    "content_type": "text/plain",
                    "content_id": "cid-1",
                }
            ],
        },
        headers={"Idempotency-Key": "support-msg_123"},
    )
