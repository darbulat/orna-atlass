from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from math import acos, asin, atan, cos, degrees, floor, radians, sin, tan
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

OFFICIAL_SUNRISE_ZENITH = 90.833
CIVIL_DAWN_ZENITH = 96.0
SolarPhase = Literal[
    "night", "civil_dawn", "daylight", "civil_dusk", "polar_day", "polar_night"
]


@dataclass(frozen=True)
class DawnWindow:
    local_date: date
    timezone: str
    civil_dawn_at: datetime | None
    sunrise_at: datetime | None
    sunset_at: datetime | None
    civil_dusk_at: datetime | None
    window_starts_at: datetime | None
    window_ends_at: datetime | None
    solar_phase: SolarPhase


def get_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown IANA timezone: {name}") from exc


def sunrise_utc(
    *,
    latitude: float,
    longitude: float,
    local_date: date,
    zenith: float = OFFICIAL_SUNRISE_ZENITH,
) -> datetime | None:
    """Approximate sunrise using NOAA's public sunrise equation."""
    event, _polar = _solar_event_utc(
        latitude=latitude,
        longitude=longitude,
        local_date=local_date,
        zenith=zenith,
        rising=True,
    )
    return event


def _solar_event_utc(
    *,
    latitude: float,
    longitude: float,
    local_date: date,
    zenith: float,
    rising: bool,
) -> tuple[datetime | None, Literal["polar_day", "polar_night"] | None]:
    day_number = local_date.timetuple().tm_yday
    longitude_hour = longitude / 15
    event_hour = 6 if rising else 18
    approximate_time = day_number + ((event_hour - longitude_hour) / 24)
    mean_anomaly = (0.9856 * approximate_time) - 3.289
    true_longitude = (
        mean_anomaly
        + (1.916 * sin(radians(mean_anomaly)))
        + (0.020 * sin(radians(2 * mean_anomaly)))
        + 282.634
    ) % 360
    right_ascension = degrees(atan(0.91764 * tan(radians(true_longitude)))) % 360
    longitude_quadrant = floor(true_longitude / 90) * 90
    right_ascension_quadrant = floor(right_ascension / 90) * 90
    right_ascension = (right_ascension + longitude_quadrant - right_ascension_quadrant) / 15
    sin_declination = 0.39782 * sin(radians(true_longitude))
    cos_declination = cos(asin(sin_declination))
    cos_hour_angle = (
        cos(radians(zenith)) - (sin_declination * sin(radians(latitude)))
    ) / (cos_declination * cos(radians(latitude)))
    if cos_hour_angle > 1:
        return None, "polar_night"
    if cos_hour_angle < -1:
        return None, "polar_day"
    angle = degrees(acos(cos_hour_angle))
    hour_angle = ((360 - angle) if rising else angle) / 15
    local_mean_time = hour_angle + right_ascension - (0.06571 * approximate_time) - 6.622
    utc_hour = local_mean_time - longitude_hour
    event_time = datetime.combine(local_date, time(), tzinfo=UTC)
    return event_time + timedelta(hours=utc_hour), None


def dawn_window(
    *,
    latitude: float,
    longitude: float,
    timezone: str,
    now: datetime,
    before_minutes: int = 45,
    after_minutes: int = 30,
) -> DawnWindow:
    tz = get_timezone(timezone)
    local_date = now.astimezone(tz).date()
    sunrise_at, polar_state = _solar_event_utc(
        latitude=latitude,
        longitude=longitude,
        local_date=local_date,
        zenith=OFFICIAL_SUNRISE_ZENITH,
        rising=True,
    )
    civil_dawn_at, _ = _solar_event_utc(
        latitude=latitude,
        longitude=longitude,
        local_date=local_date,
        zenith=CIVIL_DAWN_ZENITH,
        rising=True,
    )
    sunset_at, _ = _solar_event_utc(
        latitude=latitude,
        longitude=longitude,
        local_date=local_date,
        zenith=OFFICIAL_SUNRISE_ZENITH,
        rising=False,
    )
    civil_dusk_at, _ = _solar_event_utc(
        latitude=latitude,
        longitude=longitude,
        local_date=local_date,
        zenith=CIVIL_DAWN_ZENITH,
        rising=False,
    )

    solar_phase: SolarPhase
    if polar_state is not None:
        solar_phase = polar_state
    elif civil_dawn_at is not None and sunrise_at is not None and civil_dawn_at <= now < sunrise_at:
        solar_phase = "civil_dawn"
    elif sunrise_at is not None and sunset_at is not None and sunrise_at <= now < sunset_at:
        solar_phase = "daylight"
    elif sunset_at is not None and civil_dusk_at is not None and sunset_at <= now < civil_dusk_at:
        solar_phase = "civil_dusk"
    else:
        solar_phase = "night"

    return DawnWindow(
        local_date=local_date,
        timezone=timezone,
        civil_dawn_at=civil_dawn_at,
        sunrise_at=sunrise_at,
        sunset_at=sunset_at,
        civil_dusk_at=civil_dusk_at,
        window_starts_at=None if sunrise_at is None else sunrise_at - timedelta(minutes=before_minutes),
        window_ends_at=None if sunrise_at is None else sunrise_at + timedelta(minutes=after_minutes),
        solar_phase=solar_phase,
    )
