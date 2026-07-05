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

const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function apiUrl(path: string): string {
  return `${apiBaseUrl}${path}`;
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
