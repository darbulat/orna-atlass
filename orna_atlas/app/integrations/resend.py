import base64
import hashlib
import hmac
import json
import time
from typing import Any

import httpx

from orna_atlas.app.core.config import Settings, decode_resend_webhook_secret


WEBHOOK_TOLERANCE_SECONDS = 300


class ResendProviderError(RuntimeError):
    """Retryable provider failure without credential-bearing request details."""


def verify_webhook(
    payload: bytes,
    *,
    message_id: str | None,
    timestamp: str | None,
    signature: str | None,
    secret: str,
) -> dict[str, Any]:
    if not payload or not message_id or not timestamp or not signature:
        raise ValueError("Missing webhook signature data")
    try:
        timestamp_value = int(timestamp)
    except ValueError as exc:
        raise ValueError("Invalid webhook timestamp") from exc
    if abs(int(time.time()) - timestamp_value) > WEBHOOK_TOLERANCE_SECONDS:
        raise ValueError("Webhook timestamp is outside the allowed window")
    try:
        signing_key = decode_resend_webhook_secret(secret)
    except ValueError as exc:
        raise ValueError("Invalid webhook secret") from exc
    signed_content = b".".join((message_id.encode(), timestamp.encode(), payload))
    expected = base64.b64encode(
        hmac.new(signing_key, signed_content, hashlib.sha256).digest()
    ).decode()
    signatures = [part[3:] for part in signature.split() if part.startswith("v1,")]
    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        raise ValueError("Invalid webhook signature")
    try:
        event = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid webhook payload") from exc
    if not isinstance(event, dict):
        raise ValueError("Invalid webhook payload")
    return event


class ResendClient:
    def __init__(self, settings: Settings) -> None:
        if settings.resend_api_key is None:
            raise ValueError("RESEND_API_KEY is not configured")
        self._api_key = settings.resend_api_key

    async def forward_received_email(
        self,
        *,
        email_id: str,
        to: str,
        from_email: str,
        idempotency_key: str,
    ) -> None:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        timeout = httpx.Timeout(30.0, connect=5.0)
        async with httpx.AsyncClient(
            base_url="https://api.resend.com", headers=headers, timeout=timeout
        ) as client:
            email_response = await client.get(
                f"/emails/receiving/{email_id}", params={"html_format": "cid"}
            )
            email_response.raise_for_status()
            email = email_response.json()

            attachment_response = await client.get(
                f"/emails/receiving/{email_id}/attachments", params={"limit": 100}
            )
            attachment_response.raise_for_status()
            attachment_items = attachment_response.json().get("data", [])
            attachments: list[dict[str, str]] = []
            async with httpx.AsyncClient(timeout=timeout) as download_client:
                for item in attachment_items:
                    download_response = await download_client.get(item["download_url"])
                    if not download_response.is_success:
                        raise ResendProviderError(
                            "Attachment download failed "
                            f"with status {download_response.status_code}"
                        ) from None
                    attachment = {
                        "filename": item.get("filename") or f"attachment-{item['id']}",
                        "content": base64.b64encode(download_response.content).decode(),
                        "content_type": item["content_type"],
                    }
                    if item.get("content_id"):
                        attachment["content_id"] = item["content_id"].strip("<>")
                    attachments.append(attachment)

            outgoing: dict[str, Any] = {
                "from": from_email,
                "to": [to],
                "subject": email.get("subject") or "(no subject)",
            }
            if email.get("html"):
                outgoing["html"] = email["html"]
            if email.get("text"):
                outgoing["text"] = email["text"]
            if "html" not in outgoing and "text" not in outgoing:
                outgoing["text"] = "The received email did not contain a text or HTML body."
            if email.get("from"):
                outgoing["reply_to"] = email["from"]
            if attachments:
                outgoing["attachments"] = attachments

            send_response = await client.post(
                "/emails",
                json=outgoing,
                headers={"Idempotency-Key": idempotency_key},
            )
            send_response.raise_for_status()
