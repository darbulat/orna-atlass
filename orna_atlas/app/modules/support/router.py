from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from orna_atlas.app.core.config import Settings, get_settings
from orna_atlas.app.integrations.resend import verify_webhook
from orna_atlas.app.modules.support.service import SupportEmailService


router = APIRouter(prefix="/support", tags=["support"])
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_support_email_service(settings: AppSettings) -> SupportEmailService:
    return SupportEmailService(settings)


SupportService = Annotated[SupportEmailService, Depends(get_support_email_service)]


@router.post("/webhooks/resend", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
async def resend_email_webhook(
    request: Request,
    settings: AppSettings,
    service: SupportService,
) -> Response:
    if settings.resend_webhook_secret is None or settings.support_forward_to is None:
        raise HTTPException(status_code=503, detail="Support email forwarding is not configured")
    payload = await request.body()
    message_id = request.headers.get("svix-id")
    try:
        event = verify_webhook(
            payload,
            message_id=message_id,
            timestamp=request.headers.get("svix-timestamp"),
            signature=request.headers.get("svix-signature"),
            secret=settings.resend_webhook_secret,
        )
        if message_id is None:
            raise ValueError("Missing webhook message ID")
        await service.handle_received_event(event, message_id=message_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
