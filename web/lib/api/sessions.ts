import type { components } from "./generated";
import { ApiError, fetchJson } from "./client";
import { refreshAuthentication } from "./auth-refresh";

export type LocationRead = components["schemas"]["LocationRead"];
export type MediaAssetRead = components["schemas"]["PublicMediaAssetRead"];
export type ProcessingJobRead = components["schemas"]["ProcessingJobRead"];
export type RecordingIntegrity = components["schemas"]["RecordingIntegrityRead"];
export type Waveform = components["schemas"]["WaveformRead"];
export type SessionAnnotation = components["schemas"]["PublicSessionAnnotationRead"];
export type BirdVocalPart = components["schemas"]["PublicBirdVocalPartRead"];
export type BirdPartsResponse = components["schemas"]["BirdPartsResponse"];
export type FeaturedSession = components["schemas"]["FeaturedSessionRead"];
export type SessionDetail = components["schemas"]["SessionDetailRead"];
export type PlaybackGrant = components["schemas"]["PlaybackGrantRead"];
export type AtlasSessionSummary = components["schemas"]["AtlasSessionSummary"];
export type AtlasPoint = components["schemas"]["AtlasPoint"];
export type AtlasCluster = components["schemas"]["AtlasCluster"];
export type AtlasPointsResponse = components["schemas"]["AtlasPointsResponse"];
export type DawnWindowConfig = components["schemas"]["DawnWindowConfig"];
export type DawnLocation = components["schemas"]["DawnLocation"];
export type DawnCurrentResponse = components["schemas"]["DawnCurrentResponse"];
export type DawnFollowResponse = components["schemas"]["DawnFollowResponse"];
export type SearchResult = components["schemas"]["SearchResult"];

export function includeDawnLocations(
  points: Array<AtlasPoint | AtlasCluster>,
  dawn: DawnCurrentResponse,
): Array<AtlasPoint | AtlasCluster> {
  const merged = [...points];
  const knownSlugs = new Set(points.filter((item): item is AtlasPoint => item.type === "point").map((item) => item.slug));
  for (const item of [...dawn.active_locations, ...dawn.next_locations]) {
    if (!knownSlugs.has(item.location.slug)) {
      merged.push(item.location);
      knownSlugs.add(item.location.slug);
    }
  }
  return merged;
}

const browserApiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "";
const serverApiBaseUrl = process.env.API_SERVER_URL
  ?? process.env.NEXT_PUBLIC_API_URL
  ?? "http://localhost:8000";

export function apiUrl(path: string): string {
  const baseUrl = typeof window === "undefined" ? serverApiBaseUrl : browserApiBaseUrl;
  return `${baseUrl}${path}`;
}

function refreshAccessCookie(signal?: AbortSignal): Promise<void> {
  return refreshAuthentication(() => fetchJson<components["schemas"]["TokenResponse"]>(
    apiUrl("/api/v1/auth/refresh"),
    {
      method: "POST",
      credentials: "include",
      cache: "no-store",
      headers: { Accept: "application/json" },
    },
  ), signal);
}

function invalidResponse(detail: string): ApiError {
  return new ApiError("The server returned an invalid response", { kind: "invalid_response", detail });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isIntegerInRange(value: unknown, minimum: number, maximum = Number.POSITIVE_INFINITY): value is number {
  return Number.isInteger(value) && (value as number) >= minimum && (value as number) <= maximum;
}

function isUuid(value: unknown): value is string {
  return typeof value === "string"
    && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}

function isDateTime(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2}):(\d{2})(?:\.\d+)?([Zz]|[+-]\d{2}:\d{2})$/);
  if (!match) return false;
  const [, yearText, monthText, dayText, hourText, minuteText, secondText, offset] = match;
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const hour = Number(hourText);
  const minute = Number(minuteText);
  const second = Number(secondText);
  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const daysInMonth = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (year < 1 || month < 1 || month > 12 || day < 1 || day > daysInMonth[month - 1]
    || hour > 23 || minute > 59 || second > 59) return false;
  if (offset.toLowerCase() !== "z") {
    const offsetHour = Number(offset.slice(1, 3));
    const offsetMinute = Number(offset.slice(4, 6));
    if (offsetHour > 23 || offsetMinute > 59) return false;
  }
  return true;
}

function isOptionalNullableString(value: unknown): boolean {
  return value === undefined || value === null || typeof value === "string";
}

function isOptionalNullableDate(value: unknown): boolean {
  return value === undefined || value === null || isDateTime(value);
}

function isAtlasSessionSummary(value: unknown): value is AtlasSessionSummary {
  if (!isRecord(value)) return false;
  return isUuid(value.id)
    && typeof value.slug === "string"
    && typeof value.title === "string"
    && isDateTime(value.recorded_at)
    && (value.access_level === "public" || value.access_level === "members_only")
    && (value.duration_seconds === undefined
      || value.duration_seconds === null
      || Number.isInteger(value.duration_seconds));
}

function isAtlasPoint(value: unknown): value is AtlasPoint {
  if (!isRecord(value) || value.type !== "point") return false;
  const visibilityIsPublic = value.coordinate_visibility === "exact_public"
    || value.coordinate_visibility === "approximate_public";
  return isUuid(value.id)
    && typeof value.slug === "string"
    && typeof value.name === "string"
    && isOptionalNullableString(value.description)
    && isOptionalNullableString(value.country_code)
    && isOptionalNullableString(value.region)
    && isOptionalNullableString(value.habitat)
    && isFiniteNumber(value.latitude)
    && value.latitude >= -90
    && value.latitude <= 90
    && isFiniteNumber(value.longitude)
    && value.longitude >= -180
    && value.longitude <= 180
    && typeof value.timezone === "string"
    && visibilityIsPublic
    && typeof value.sensitivity_level === "string"
    && isIntegerInRange(value.session_count, 0)
    && (value.latest_session === undefined
      || value.latest_session === null
      || isAtlasSessionSummary(value.latest_session));
}

function isAtlasCluster(value: unknown): value is AtlasCluster {
  if (!isRecord(value) || value.type !== "cluster") return false;
  return typeof value.id === "string"
    && isFiniteNumber(value.latitude)
    && value.latitude >= -90
    && value.latitude <= 90
    && isFiniteNumber(value.longitude)
    && value.longitude >= -180
    && value.longitude <= 180
    && isIntegerInRange(value.count, 1)
    && (value.habitats === undefined
      || (Array.isArray(value.habitats) && value.habitats.every((item) => typeof item === "string")));
}

export function validateAtlasPointsResponse(value: unknown): AtlasPointsResponse {
  if (!isRecord(value)) throw invalidResponse("Atlas response is not an object");
  const validBbox = value.bbox === null || (Array.isArray(value.bbox)
    && value.bbox.length === 4
    && value.bbox.every(isFiniteNumber));
  if (!validBbox
    || !isIntegerInRange(value.zoom, 0, 22)
    || (value.mode !== "points" && value.mode !== "clusters")
    || !Array.isArray(value.points)
    || !value.points.every((point) => isAtlasPoint(point) || isAtlasCluster(point))
    || typeof value.cache_key !== "string") {
    throw invalidResponse("Atlas response does not match its public contract");
  }
  return value as AtlasPointsResponse;
}

function isOptionalNullableCoordinate(value: unknown, minimum: number, maximum: number): boolean {
  return value === undefined || value === null
    || (isFiniteNumber(value) && value >= minimum && value <= maximum);
}

function isSearchResult(value: unknown): value is SearchResult {
  if (!isRecord(value)) return false;
  return (value.type === "location" || value.type === "session")
    && isUuid(value.id)
    && typeof value.slug === "string"
    && typeof value.title === "string"
    && isOptionalNullableString(value.subtitle)
    && isOptionalNullableString(value.habitat)
    && isOptionalNullableString(value.session_slug)
    && isOptionalNullableCoordinate(value.latitude, -90, 90)
    && isOptionalNullableCoordinate(value.longitude, -180, 180)
    && (value.atlas_point === undefined || value.atlas_point === null || isAtlasPoint(value.atlas_point));
}

export function validateSearchResults(value: unknown): SearchResult[] {
  if (!Array.isArray(value) || !value.every(isSearchResult)) {
    throw invalidResponse("Search response does not match its public contract");
  }
  return value;
}

function isDawnLocation(value: unknown): value is DawnLocation {
  if (!isRecord(value)) return false;
  const validState = ["active", "upcoming", "past", "polar"].includes(value.state as string);
  const validPhase = ["night", "civil_dawn", "daylight", "civil_dusk", "polar_day", "polar_night"]
    .includes(value.solar_phase as string);
  return isAtlasPoint(value.location)
    && typeof value.local_date === "string"
    && typeof value.local_time === "string"
    && isOptionalNullableDate(value.civil_dawn_at)
    && isOptionalNullableDate(value.sunrise_at)
    && isOptionalNullableDate(value.sunset_at)
    && isOptionalNullableDate(value.civil_dusk_at)
    && isOptionalNullableDate(value.window_starts_at)
    && isOptionalNullableDate(value.window_ends_at)
    && (value.minutes_until_sunrise === undefined
      || value.minutes_until_sunrise === null
      || Number.isInteger(value.minutes_until_sunrise))
    && validState
    && validPhase;
}

export function validateDawnCurrentResponse(value: unknown): DawnCurrentResponse {
  if (!isRecord(value) || !isRecord(value.window)) {
    throw invalidResponse("Dawn response is not an object");
  }
  if (!isDateTime(value.generated_at)
    || !isIntegerInRange(value.window.before_minutes, 1)
    || !isIntegerInRange(value.window.after_minutes, 1)
    || !isIntegerInRange(value.window.refresh_seconds, 1)
    || !Array.isArray(value.active_locations)
    || !value.active_locations.every(isDawnLocation)
    || !Array.isArray(value.next_locations)
    || !value.next_locations.every(isDawnLocation)
    || typeof value.cache_key !== "string") {
    throw invalidResponse("Dawn response does not match its public contract");
  }
  return value as DawnCurrentResponse;
}

export function fetchFeaturedSessions(limit = 6): Promise<FeaturedSession[]> {
  return fetchJson<FeaturedSession[]>(apiUrl(`/api/v1/sessions/featured?limit=${limit}`), {
    next: { revalidate: 120 },
    headers: { Accept: "application/json" },
  });
}

export function fetchBirdParts(sessionId: string): Promise<BirdPartsResponse> {
  return fetchJson<BirdPartsResponse>(apiUrl(`/api/v1/sessions/${sessionId}/bird-parts`), {
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
}

function requestSessionDetail(
  slug: string,
  forwardedHeaders: HeadersInit = {},
): Promise<SessionDetail> {
  return fetchJson<SessionDetail>(apiUrl(`/api/v1/sessions/${slug}`), {
    cache: "no-store",
    credentials: "include",
    headers: { Accept: "application/json", ...forwardedHeaders },
  });
}

export async function fetchSessionDetail(
  slug: string,
  forwardedHeaders: HeadersInit = {},
): Promise<SessionDetail> {
  const requestDetail = () => requestSessionDetail(slug, forwardedHeaders);

  try {
    return await requestDetail();
  } catch (error) {
    if (typeof window === "undefined" || !(error instanceof ApiError) || error.status !== 401) {
      throw error;
    }
  }

  await refreshAccessCookie();
  return requestDetail();
}

export async function recoverBrowserSessionDetail(slug: string): Promise<SessionDetail> {
  try {
    return await fetchSessionDetail(slug);
  } catch (error) {
    if (typeof window === "undefined" || !(error instanceof ApiError) || error.status !== 404) {
      throw error;
    }
  }

  await refreshAccessCookie();
  return requestSessionDetail(slug);
}

export function fetchAtlasPoints(
  _view: string | undefined,
  habitats: string[] = [],
  options: { cache?: RequestCache } = {},
): Promise<AtlasPointsResponse> {
  const zoom = 5;
  // Request the API's complete supported point window so client-side features
  // such as nearest-location selection do not operate on the smaller display page.
  const params = new URLSearchParams({ zoom: String(zoom), limit: "1000" });
  habitats.forEach((habitat) => params.append("habitat", habitat));

  return fetchJson<unknown>(apiUrl(`/api/v1/atlas/points?${params.toString()}`), {
    ...(options.cache ? { cache: options.cache } : { next: { revalidate: 60 } }),
    headers: { Accept: "application/json" },
  }).then(validateAtlasPointsResponse);
}

export function searchAtlas(query: string, limit = 8): Promise<SearchResult[]> {
  const trimmed = query.trim();
  if (trimmed.length < 2) {
    return Promise.resolve([]);
  }
  const params = new URLSearchParams({ q: trimmed, limit: String(limit) });

  return fetchJson<unknown>(apiUrl(`/api/v1/search?${params.toString()}`), {
    cache: "no-store",
    headers: { Accept: "application/json" },
  }).then(validateSearchResults);
}

export function fetchCurrentDawn(
  limit = 250,
  options: { cache?: RequestCache } = {},
): Promise<DawnCurrentResponse> {
  const normalizedLimit = Math.max(1, Math.min(Math.ceil(limit), 1000));
  const params = new URLSearchParams({ limit: String(normalizedLimit) });

  return fetchJson<unknown>(apiUrl(`/api/v1/atlas/dawn/current?${params.toString()}`), {
    ...(options.cache ? { cache: options.cache } : { next: { revalidate: 60 } }),
    headers: { Accept: "application/json" },
  }).then(validateDawnCurrentResponse);
}

export function fetchFollowDawn(): Promise<DawnFollowResponse> {
  return fetchJson<DawnFollowResponse>(apiUrl("/api/v1/atlas/dawn/follow"), {
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
}

export async function requestPlaybackGrant(sessionId: string, signal?: AbortSignal): Promise<PlaybackGrant> {
  const requestGrant = () => fetchJson<PlaybackGrant>(apiUrl(`/api/v1/sessions/${sessionId}/playback-grants`), {
    method: "POST",
    credentials: "include",
    signal,
    headers: { Accept: "application/json" },
  });

  try {
    return await requestGrant();
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401) {
      throw error;
    }
  }

  await refreshAccessCookie(signal);
  return requestGrant();
}
