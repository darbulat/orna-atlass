from typing import Any

from orna_atlas.app.core.config import SUPPORT_INBOUND_EMAIL, Settings
from orna_atlas.app.integrations.resend import ResendClient


class SupportEmailService:
    """Own recipient policy and the inbound-support forwarding use case."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def handle_received_event(self, event: dict[str, Any], *, message_id: str) -> None:
        if event.get("type") != "email.received":
            return
        data = event.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("to"), list):
            return
        if not any(
            isinstance(recipient, str) and recipient.strip().lower() == SUPPORT_INBOUND_EMAIL
            for recipient in data["to"]
        ):
            return

        email_id = data.get("email_id")
        if not isinstance(email_id, str) or not email_id:
            raise ValueError("Invalid support email event")
        if self._settings.support_forward_to is None:
            raise ValueError("SUPPORT_FORWARD_TO is not configured")

        await ResendClient(self._settings).forward_received_email(
            email_id=email_id,
            to=self._settings.support_forward_to,
            from_email=self._settings.support_from_email,
            idempotency_key=f"support-{message_id}",
        )
