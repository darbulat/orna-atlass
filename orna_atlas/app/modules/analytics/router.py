from enum import StrEnum

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict

from orna_atlas.app.core.metrics import CONVERSION_EVENTS

router = APIRouter(prefix="/analytics", tags=["analytics"])


class ConversionEventName(StrEnum):
    GLOBE_VIEW = "globe_view"
    SESSION_PREVIEW_START = "session_preview_start"
    SESSION_PREVIEW_SECOND = "session_preview_second"
    LOCKED_POINT_HIT = "locked_point_hit"
    PAYWALL_SHOWN = "paywall_shown"
    SIGNUP_STARTED = "signup_started"
    SIGNUP_COMPLETED = "signup_completed"
    MEMBER_SESSION_PLAY = "member_session_play"
    SUBSCRIPTION_INTENT = "subscription_intent"
    COLLECTIONS_VIEW = "collections_view"
    SEARCH_OPENED = "search_opened"
    LOGIN_OPENED = "login_opened"
    MEMBERSHIP_CTA_CLICK = "membership_cta_click"
    MARKER_CLICK = "marker_click"
    RESET_VIEW_CLICK = "reset_view_click"
    TIME_FILTER_DAWN = "time_filter_dawn"
    TIME_FILTER_DAY = "time_filter_day"
    TIME_FILTER_DUSK = "time_filter_dusk"
    TIME_FILTER_NIGHT = "time_filter_night"
    CAROUSEL_SCROLL = "carousel_scroll"
    LOCATION_SEARCH = "location_search"
    CARD_INLINE_PLAY = "card_inline_play"
    CARD_OPEN = "card_open"
    SEE_ALL_CLICK = "see_all_click"
    PLAYER_PLAY = "player_play"
    PLAYER_PAUSE = "player_pause"
    PLAYER_SEEK = "player_seek"
    FAVORITE_ADD = "favorite_add"
    FAVORITE_REQUIRES_LOGIN = "favorite_requires_login"
    PLAYER_NEXT = "player_next"
    PLAYER_PREV = "player_prev"
    TIMELINE_SPECIES_CLICK = "timeline_species_click"
    SESSION_CLOSE = "session_close"
    PAYWALL_SIGNUP_CLICK = "paywall_signup_click"
    PAYWALL_LEARN_MORE = "paywall_learn_more"
    PAYWALL_DISMISSED = "paywall_dismissed"
    SIGNUP_EMAIL_SUBMIT = "signup_email_submit"
    MEMBERSHIP_RESERVE_CLICK = "membership_reserve_click"
    POINT_OPENED = "point_opened"
    PLAY_STARTED = "play_started"
    FAVORITE_CLICKED = "favorite_clicked"
    LOCK_CLICKED = "lock_clicked"
    REGISTRATION_STARTED = "registration_started"
    MEMBERSHIP_INTEREST_SUBMITTED = "membership_interest_submitted"
    SAMPLE_PLAY_STARTED = "sample_play_started"
    LISTENING_30_SECONDS = "listening_30_seconds"
    LISTENING_5_MINUTES = "listening_5_minutes"
    REGISTRATION_COMPLETED = "registration_completed"
    HERO_CTA_CLICKED = "hero_cta_clicked"
    LISTENING_PATH_SELECTED = "listening_path_selected"
    MEMBERSHIP_CTA_CLICKED = "membership_cta_clicked"
    FINAL_CTA_CLICKED = "final_cta_clicked"


class ConversionPlacement(StrEnum):
    GLOBE = "globe"
    GLOBE_CONTROLS = "globe_controls"
    TIME_FILTER = "time_filter"
    LOCATION_SEARCH = "location_search"
    LOCATION_CAROUSEL = "location_carousel"
    POPULAR_LOCATIONS = "popular_locations"
    COLLECTIONS = "collections"
    GLOBE_MARKER = "globe_marker"
    LOCATION_CARD = "location_card"
    SESSION_OVERLAY = "session_overlay"
    SOFT_PAYWALL = "soft_paywall"
    HEADER = "header"
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
