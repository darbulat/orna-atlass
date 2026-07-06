from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from math import acos, asin, atan, cos, degrees, floor, radians, sin, tan
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

OFFICIAL_SUNRISE_ZENITH = 90.833
CIVIL_DAWN_ZENITH = 96.0


@dataclass(frozen=True)
class DawnWindow:
    local_date: date
    timezone: str
    civil_dawn_at: datetime | None
    sunrise_at: datetime | None
    window_starts_at: datetime | None
    window_ends_at: datetime | None


def get_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def sunrise_utc(
    *,
    latitude: float,
    longitude: float,
    local_date: date,
    zenith: float = OFFICIAL_SUNRISE_ZENITH,
) -> datetime | None:
    """Approximate sunrise using NOAA's public sunrise equation."""
    day_number = local_date.timetuple().tm_yday
    longitude_hour = longitude / 15
    approximate_time = day_number + ((6 - longitude_hour) / 24)
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
    if cos_hour_angle > 1 or cos_hour_angle < -1:
        return None
    hour_angle = (360 - degrees(acos(cos_hour_angle))) / 15
    local_mean_time = hour_angle + right_ascension - (0.06571 * approximate_time) - 6.622
    utc_hour = local_mean_time - longitude_hour
    sunrise_time = datetime.combine(local_date, time(), tzinfo=UTC)
    sunrise_time += timedelta(hours=utc_hour)
    return sunrise_time


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
    local_now = now.astimezone(tz)
    local_date = local_now.date()
    sunrise_at = sunrise_utc(latitude=latitude, longitude=longitude, local_date=local_date)
    civil_dawn_at = sunrise_utc(
        latitude=latitude,
        longitude=longitude,
        local_date=local_date,
        zenith=CIVIL_DAWN_ZENITH,
    )
    return DawnWindow(
        local_date=local_date,
        timezone=timezone,
        civil_dawn_at=civil_dawn_at,
        sunrise_at=sunrise_at,
        window_starts_at=None if sunrise_at is None else sunrise_at - timedelta(minutes=before_minutes),
        window_ends_at=None if sunrise_at is None else sunrise_at + timedelta(minutes=after_minutes),
    )
