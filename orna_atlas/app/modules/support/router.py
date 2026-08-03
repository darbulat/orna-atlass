from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from orna_atlas.app.core.config import Settings, get_settings
from orna_atlas.app.integrations.resend import ResendClient, verify_webhook


router = APIRouter(prefix="/support", tags=["support"])
AppSettings = Annotated[Settings, Depends(get_settings)]


def _is_support_email(event: dict[str, Any]) -> bool:
    if event.get("type") != "email.received":
        return False
    data = event.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("to"), list):
        return False
    return any(
        isinstance(recipient, str) and recipient.strip().lower() == "support@orna.land"
        for recipient in data["to"]
    )


@router.post("/webhooks/resend", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
async def resend_email_webhook(request: Request, settings: AppSettings) -> Response:
    if settings.resend_webhook_secret is None or settings.support_forward_to is None:
        raise HTTPException(status_code=503, detail="Support email forwarding is not configured")
    payload = await request.body()
    try:
        event = verify_webhook(
            payload,
            message_id=request.headers.get("svix-id"),
            timestamp=request.headers.get("svix-timestamp"),
            signature=request.headers.get("svix-signature"),
            secret=settings.resend_webhook_secret,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook") from exc
    if not _is_support_email(event):
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    data = event["data"]
    email_id = data.get("email_id")
    message_id = request.headers.get("svix-id")
    if not isinstance(email_id, str) or not email_id or message_id is None:
        raise HTTPException(status_code=400, detail="Invalid webhook")
    await ResendClient(settings).forward_received_email(
        email_id=email_id,
        to=settings.support_forward_to,
        from_email=settings.support_from_email,
        idempotency_key=f"support-{message_id}",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
