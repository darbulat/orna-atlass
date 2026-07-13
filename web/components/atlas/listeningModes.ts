import type { AtlasPoint } from "../../lib/api/sessions";

export type ListeningMode = "Dawn" | "Day" | "Dusk" | "Night";

export const listeningModes: ListeningMode[] = ["Dawn", "Day", "Dusk", "Night"];
export const listeningModeKicker: Record<ListeningMode, string> = {
  Dawn: "Now at dawn",
  Day: "Now in daylight",
  Dusk: "Now at dusk",
  Night: "Now at night",
};

function localMinutes(timezone: string, baseTime: string): number | null {
  const generatedAt = new Date(baseTime);
  if (Number.isNaN(generatedAt.getTime())) return null;
  try {
    const parts = new Intl.DateTimeFormat("en-GB", {
      hour: "2-digit",
      hourCycle: "h23",
      minute: "2-digit",
      timeZone: timezone,
    }).formatToParts(generatedAt);
    const hour = Number(parts.find((part) => part.type === "hour")?.value);
    const minute = Number(parts.find((part) => part.type === "minute")?.value);
    return Number.isNaN(hour) || Number.isNaN(minute) ? null : hour * 60 + minute;
  } catch {
    return null;
  }
}

export function listeningModeForLocation(
  location: AtlasPoint,
  baseTime: string,
  activeDawnSlugs: Set<string> = new Set(),
): ListeningMode {
  if (activeDawnSlugs.has(location.slug)) return "Dawn";
  const minutes = localMinutes(location.timezone, baseTime);
  if (minutes == null) return "Day";
  if (minutes >= 270 && minutes < 450) return "Dawn";
  if (minutes >= 450 && minutes < 1020) return "Day";
  if (minutes >= 1020 && minutes < 1200) return "Dusk";
  return "Night";
}

export function filterLocationsByMode(
  locations: AtlasPoint[],
  mode: ListeningMode,
  baseTime: string,
  activeDawnSlugs: Set<string>,
) {
  return locations.filter(
    (location) => listeningModeForLocation(location, baseTime, activeDawnSlugs) === mode,
  );
}
