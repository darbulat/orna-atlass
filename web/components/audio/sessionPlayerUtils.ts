import type { BirdVocalPart, SessionDetail } from "../../lib/api/sessions";

export const TIMELINE_TRACK_START = 34;
export const TIMELINE_TRACK_WIDTH = 61;

export type BirdTimelineTrack = {
  key: string;
  label: string;
  startsAt: number;
  endsAt: number;
  parts: BirdVocalPart[];
};

export function formatCoordinates(session: SessionDetail) {
  const { latitude, longitude } = session.location;
  if (latitude == null || longitude == null) {
    return session.location.coordinates_protected ? "Protected coordinates" : "Coordinates pending";
  }
  const coordinates = `${Math.abs(latitude).toFixed(3)}° ${latitude >= 0 ? "N" : "S"}  ${Math.abs(longitude).toFixed(3)}° ${longitude >= 0 ? "E" : "W"}`;
  return session.location.coordinates_protected ? `Approx. ${coordinates}` : coordinates;
}

export function formatDurationClock(seconds: number | null) {
  const total = Math.max(seconds ?? 0, 0);
  const hours = Math.floor(total / 3600).toString().padStart(2, "0");
  const minutes = Math.floor((total % 3600) / 60).toString().padStart(2, "0");
  const remaining = Math.floor(total % 60).toString().padStart(2, "0");
  return `${hours}:${minutes}:${remaining}`;
}

export function formatOffset(seconds: number) {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, "0");
  const remaining = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${remaining}`;
}

function timeFormatter(timeZone: string) {
  try {
    return new Intl.DateTimeFormat("en-US", { hour: "2-digit", minute: "2-digit", timeZone });
  } catch {
    return new Intl.DateTimeFormat("en-US", { hour: "2-digit", minute: "2-digit" });
  }
}

export function formatLocalTime(value: string, timeZone: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "--:--" : timeFormatter(timeZone).format(date);
}

export function formatClockTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "--:--" : new Intl.DateTimeFormat("en-US", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function groupBirdPartsBySpecies(parts: BirdVocalPart[]): BirdTimelineTrack[] {
  const tracks = new Map<string, BirdTimelineTrack>();
  parts.forEach((part) => {
    const key = part.species_code || part.species_common_name;
    const track = tracks.get(key);
    if (track) {
      track.startsAt = Math.min(track.startsAt, part.starts_at_seconds);
      track.endsAt = Math.max(track.endsAt, part.ends_at_seconds);
      track.parts.push(part);
    } else {
      tracks.set(key, {
        key,
        label: part.species_common_name,
        startsAt: part.starts_at_seconds,
        endsAt: part.ends_at_seconds,
        parts: [part],
      });
    }
  });
  return Array.from(tracks.values())
    .map((track) => ({
      ...track,
      parts: [...track.parts].sort((left, right) => left.starts_at_seconds - right.starts_at_seconds),
    }))
    .sort((left, right) => left.startsAt - right.startsAt || left.label.localeCompare(right.label));
}

export function buildWeatherItems(session: SessionDetail) {
  return [
    { label: "conditions", value: session.weather?.trim() || "Unavailable" },
    { label: "habitat", value: session.location.habitat?.trim() || "—" },
  ];
}

export function timelineTotalSeconds(session: SessionDetail) {
  const latestBirdPartEnd = Math.max(...(session.bird_parts?.parts.map((part) => part.ends_at_seconds) ?? [0]));
  return Math.max(session.duration_seconds ?? 0, latestBirdPartEnd, 1);
}

export function timelineTickLabels(recordedAt: string, durationSeconds: number, timeZone: string) {
  const start = new Date(recordedAt);
  const formatter = timeFormatter(timeZone);
  return Array.from({ length: 6 }, (_, index) => {
    const offset = (durationSeconds / 5) * index;
    if (Number.isNaN(start.getTime())) {
      const minutes = Math.floor(offset / 60).toString().padStart(2, "0");
      return `${minutes}:${Math.floor(offset % 60).toString().padStart(2, "0")}`;
    }
    return formatter.format(new Date(start.getTime() + offset * 1000));
  });
}

export function timelineLeft(seconds: number, totalSeconds: number) {
  return TIMELINE_TRACK_START + Math.min(Math.max(seconds / totalSeconds, 0), 1) * TIMELINE_TRACK_WIDTH;
}

export function timelineWidth(part: BirdVocalPart, totalSeconds: number) {
  return timelineRangeWidth(part.starts_at_seconds, part.ends_at_seconds, totalSeconds);
}

export function timelineRangeWidth(startsAt: number, endsAt: number, totalSeconds: number) {
  return Math.max((Math.max(endsAt - startsAt, 0) / totalSeconds) * TIMELINE_TRACK_WIDTH, 1.5);
}
