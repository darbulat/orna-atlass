from enum import StrEnum

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict

from orna_atlas.app.core.metrics import CONVERSION_EVENTS

router = APIRouter(prefix="/analytics", tags=["analytics"])


class ConversionEventName(StrEnum):
    SAMPLE_PLAY_STARTED = "sample_play_started"
    LISTENING_30_SECONDS = "listening_30_seconds"
    LISTENING_5_MINUTES = "listening_5_minutes"
    REGISTRATION_COMPLETED = "registration_completed"
    HERO_CTA_CLICKED = "hero_cta_clicked"
    LISTENING_PATH_SELECTED = "listening_path_selected"
    MEMBERSHIP_CTA_CLICKED = "membership_cta_clicked"
    FINAL_CTA_CLICKED = "final_cta_clicked"


class ConversionPlacement(StrEnum):
    GLOBAL_PLAYER = "global_player"
    HERO_SAMPLE = "hero_sample"
    HERO_PRIMARY = "hero_primary"
    HERO_SECONDARY = "hero_secondary"
    INTENT_FOCUS = "intent_focus"
    INTENT_RESTORE = "intent_restore"
    INTENT_UNWIND = "intent_unwind"
    INTENT_EXPLORE = "intent_explore"
    PRICING_CARD = "pricing_card"
    FOOTER_ATLAS = "footer_atlas"
    FOOTER_MEMBERSHIP = "footer_membership"
    MEMBERSHIP_FORM = "membership_form"


class ConversionEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ConversionEventName
    placement: ConversionPlacement


class ConversionEventAccepted(BaseModel):
    accepted: bool


@router.post(
    "/events",
    response_model=ConversionEventAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def accept_conversion_event(event: ConversionEventCreate) -> ConversionEventAccepted:
    CONVERSION_EVENTS.labels(name=event.name.value, placement=event.placement.value).inc()
    return ConversionEventAccepted(accepted=True)
