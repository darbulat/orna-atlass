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
  processing_status: string;
  duration_seconds: number | null;
  size_bytes: number | null;
  checksum: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  processing_jobs?: ProcessingJobRead[];
};

export type ProcessingJobRead = {
  id: string;
  asset_id: string;
  job_type: string;
  status: string;
  attempt_count: number;
  error_code: string | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
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
  processing_status: string;
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

export type DawnWindowConfig = {
  before_minutes: number;
  after_minutes: number;
  refresh_seconds: number;
};

export type DawnLocation = {
  location: AtlasPoint;
  local_date: string;
  local_time: string;
  civil_dawn_at: string | null;
  sunrise_at: string | null;
  window_starts_at: string | null;
  window_ends_at: string | null;
  minutes_until_sunrise: number | null;
  state: "active" | "upcoming" | "past" | "polar";
};

export type DawnCurrentResponse = {
  generated_at: string;
  window: DawnWindowConfig;
  active_locations: DawnLocation[];
  next_locations: DawnLocation[];
  cache_key: string;
};

export type DawnFollowResponse = {
  generated_at: string;
  window: DawnWindowConfig;
  locations: DawnLocation[];
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
  atlas_point: AtlasPoint | null;
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

export async function fetchCurrentDawn(): Promise<DawnCurrentResponse> {
  try {
    const response = await fetch(apiUrl("/api/v1/atlas/dawn/current"), {
      next: { revalidate: 60 },
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error("Unable to load dawn");
    }
    return (await response.json()) as DawnCurrentResponse;
  } catch {
    return {
      generated_at: new Date().toISOString(),
      window: { before_minutes: 45, after_minutes: 30, refresh_seconds: 60 },
      active_locations: [],
      next_locations: [],
      cache_key: "atlas:dawn:current:empty",
    };
  }
}

export async function fetchFollowDawn(): Promise<DawnFollowResponse> {
  try {
    const response = await fetch(apiUrl("/api/v1/atlas/dawn/follow"), {
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error("Unable to load follow dawn");
    }
    return (await response.json()) as DawnFollowResponse;
  } catch {
    return {
      generated_at: new Date().toISOString(),
      window: { before_minutes: 45, after_minutes: 30, refresh_seconds: 60 },
      locations: [],
      cache_key: "atlas:dawn:follow:empty",
    };
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
