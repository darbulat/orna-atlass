import type { components } from "./generated";
import { ApiError, fetchJson } from "./client";

export type LocationRead = components["schemas"]["LocationRead"];
export type MediaAssetRead = components["schemas"]["MediaAssetRead"];
export type ProcessingJobRead = components["schemas"]["ProcessingJobRead"];
export type RecordingIntegrity = components["schemas"]["RecordingIntegrityRead"];
export type Waveform = components["schemas"]["WaveformRead"];
export type SessionAnnotation = components["schemas"]["SessionAnnotationRead"];
export type BirdVocalPart = components["schemas"]["BirdVocalPartRead"];
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

const browserApiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "";
const serverApiBaseUrl = process.env.API_SERVER_URL
  ?? process.env.NEXT_PUBLIC_API_URL
  ?? "http://localhost:8000";

export function apiUrl(path: string): string {
  const baseUrl = typeof window === "undefined" ? serverApiBaseUrl : browserApiBaseUrl;
  return `${baseUrl}${path}`;
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

export function fetchSessionDetail(
  slug: string,
  forwardedHeaders: HeadersInit = {},
): Promise<SessionDetail> {
  return fetchJson<SessionDetail>(apiUrl(`/api/v1/sessions/${slug}`), {
    cache: "no-store",
    headers: { Accept: "application/json", ...forwardedHeaders },
  });
}

export function fetchAtlasPoints(
  _view: string | undefined,
  habitats: string[] = [],
): Promise<AtlasPointsResponse> {
  const zoom = 5;
  // Request the API's complete supported point window so client-side features
  // such as nearest-location selection do not operate on the smaller display page.
  const params = new URLSearchParams({ zoom: String(zoom), limit: "1000" });
  habitats.forEach((habitat) => params.append("habitat", habitat));

  return fetchJson<AtlasPointsResponse>(apiUrl(`/api/v1/atlas/points?${params.toString()}`), {
    next: { revalidate: 60 },
    headers: { Accept: "application/json" },
  });
}

export function searchAtlas(query: string, limit = 8): Promise<SearchResult[]> {
  const trimmed = query.trim();
  if (trimmed.length < 2) {
    return Promise.resolve([]);
  }
  const params = new URLSearchParams({ q: trimmed, limit: String(limit) });

  return fetchJson<SearchResult[]>(apiUrl(`/api/v1/search?${params.toString()}`), {
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
}

export function fetchCurrentDawn(limit = 250): Promise<DawnCurrentResponse> {
  const normalizedLimit = Math.max(1, Math.min(Math.ceil(limit), 1000));
  const params = new URLSearchParams({ limit: String(normalizedLimit) });

  return fetchJson<DawnCurrentResponse>(apiUrl(`/api/v1/atlas/dawn/current?${params.toString()}`), {
    next: { revalidate: 60 },
    headers: { Accept: "application/json" },
  });
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

  await fetchJson<components["schemas"]["TokenResponse"]>(apiUrl("/api/v1/auth/refresh"), {
    method: "POST",
    credentials: "include",
    signal,
    headers: { Accept: "application/json" },
  });
  return requestGrant();
}
