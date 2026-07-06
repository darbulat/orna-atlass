export type LocationRead = {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  country_code: string | null;
  region: string | null;
  habitat: string | null;
  latitude: number | null;
  longitude: number | null;
  timezone: string;
};

export type MediaAssetRead = {
  id: string;
  session_id: string;
  kind: string;
  mime_type: string;
  duration_seconds: number | null;
  size_bytes: number | null;
  checksum: string | null;
};

export type RecordingIntegrity = {
  human_noise_level: string;
  post_processing: string;
  microphone_setup: string | null;
  recordist_notes: string | null;
};

export type Waveform = {
  session_id: string | null;
  duration_seconds: number | null;
  peaks: number[];
  sample_rate: number;
  status: string;
};

export type SessionAnnotation = {
  offset_seconds: number;
  duration_seconds: number | null;
  label: string;
  annotation_type: string;
  confidence: number | null;
  metadata: Record<string, unknown>;
};

export type SessionDetail = {
  id: string;
  location_id: string;
  slug: string;
  title: string;
  description: string | null;
  recorded_at: string;
  duration_seconds: number | null;
  recorder: string | null;
  weather: string | null;
  access_level: string;
  media_assets: MediaAssetRead[];
  location: LocationRead;
  recording_integrity: RecordingIntegrity;
  waveform: Waveform;
  annotations: SessionAnnotation[];
};

export type PlaybackGrant = {
  session_id: string;
  status: string;
  stream_url: string;
  expires_at: string;
  refresh_after_seconds: number;
};

export type AtlasSessionSummary = {
  id: string;
  slug: string;
  title: string;
  recorded_at: string;
  duration_seconds: number | null;
};

export type AtlasPoint = {
  type: "point";
  id: string;
  slug: string;
  name: string;
  description: string | null;
  country_code: string | null;
  region: string | null;
  habitat: string | null;
  latitude: number;
  longitude: number;
  timezone: string;
  sensitivity_level: string;
  session_count: number;
  latest_session: AtlasSessionSummary | null;
};

export type AtlasCluster = {
  type: "cluster";
  id: string;
  latitude: number;
  longitude: number;
  count: number;
  habitats: string[];
};

export type AtlasPointsResponse = {
  bbox: [number, number, number, number] | null;
  zoom: number;
  mode: "points" | "clusters";
  points: Array<AtlasPoint | AtlasCluster>;
  cache_key: string;
};

export type SearchResult = {
  type: "location" | "session";
  id: string;
  slug: string;
  title: string;
  subtitle: string | null;
  habitat: string | null;
  latitude: number | null;
  longitude: number | null;
  session_slug: string | null;
};

const browserApiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const serverApiBaseUrl = process.env.API_SERVER_URL ?? browserApiBaseUrl;

export function apiUrl(path: string): string {
  const baseUrl = typeof window === "undefined" ? serverApiBaseUrl : browserApiBaseUrl;
  return `${baseUrl}${path}`;
}

export async function fetchSessionDetail(slug: string): Promise<SessionDetail | null> {
  try {
    const response = await fetch(apiUrl(`/api/v1/sessions/${slug}`), {
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as SessionDetail;
  } catch {
    return null;
  }
}

export async function fetchAtlasPoints(
  _view: string | undefined,
  habitats: string[] = [],
): Promise<AtlasPointsResponse> {
  const zoom = 5;
  const params = new URLSearchParams({ zoom: String(zoom), limit: "250" });
  habitats.forEach((habitat) => params.append("habitat", habitat));

  try {
    const response = await fetch(apiUrl(`/api/v1/atlas/points?${params.toString()}`), {
      next: { revalidate: 60 },
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      return { bbox: null, zoom, mode: "points", points: [], cache_key: "atlas:points:empty" };
    }
    return (await response.json()) as AtlasPointsResponse;
  } catch {
    return { bbox: null, zoom, mode: "points", points: [], cache_key: "atlas:points:empty" };
  }
}

export async function searchAtlas(query: string, limit = 8): Promise<SearchResult[]> {
  const trimmed = query.trim();
  if (trimmed.length < 2) {
    return [];
  }
  const params = new URLSearchParams({ q: trimmed, limit: String(limit) });

  try {
    const response = await fetch(apiUrl(`/api/v1/search?${params.toString()}`), {
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      return [];
    }
    return (await response.json()) as SearchResult[];
  } catch {
    return [];
  }
}

export async function requestPlaybackGrant(sessionId: string): Promise<PlaybackGrant> {
  const response = await fetch(apiUrl(`/api/v1/sessions/${sessionId}/playback-grants`), {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error("Unable to create playback grant");
  }
  return (await response.json()) as PlaybackGrant;
}
