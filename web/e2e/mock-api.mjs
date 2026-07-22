import { createServer } from "node:http";

const port = Number(process.env.PORT ?? 4010);
const origin = process.env.WEB_ORIGIN ?? "http://127.0.0.1:3100";
const locationId = "10000000-0000-4000-8000-000000000001";
const firstSessionId = "20000000-0000-4000-8000-000000000001";
const secondSessionId = "20000000-0000-4000-8000-000000000002";
const now = "2026-07-14T23:00:00Z";

const location = {
  id: locationId,
  slug: "pine-marsh",
  name: "Pine Marsh",
  description: "A protected wetland listening site.",
  country_code: "EE",
  region: "Harju",
  habitat: "Wetland",
  latitude: 59.42,
  longitude: 24.71,
  coordinate_visibility: "approximate_public",
  sensitivity_level: "medium",
  coordinates_protected: true,
  timezone: "UTC",
};

const atlasPoint = {
  type: "point",
  id: locationId,
  slug: location.slug,
  name: location.name,
  description: location.description,
  country_code: location.country_code,
  region: location.region,
  habitat: location.habitat,
  latitude: location.latitude,
  longitude: location.longitude,
  timezone: location.timezone,
  coordinate_visibility: location.coordinate_visibility,
  sensitivity_level: location.sensitivity_level,
  session_count: 2,
  latest_session: {
    id: secondSessionId,
    slug: "second-session",
    title: "Second Session",
    recorded_at: now,
    duration_seconds: 3600,
    access_level: "public",
  },
};

const ridgePoint = {
  ...atlasPoint,
  id: "10000000-0000-4000-8000-000000000009",
  slug: "ridge-dawn",
  name: "Ridge Dawn",
  latitude: 58.42,
  longitude: 23.71,
};

const morningPoint = {
  ...atlasPoint,
  id: "10000000-0000-4000-8000-000000000010",
  slug: "morning-marsh",
  name: "Morning Marsh",
  timezone: "Asia/Dhaka",
};

const lockedPoint = {
  ...atlasPoint,
  id: "10000000-0000-4000-8000-000000000011",
  slug: "members-cove",
  name: "Members Cove",
  latest_session: {
    ...atlasPoint.latest_session,
    id: "20000000-0000-4000-8000-000000000011",
    slug: "members-cove-long-form",
    title: "Members Cove Long Form",
    access_level: "members_only",
  },
};

function session(id, slug, title) {
  return {
    id,
    location_id: locationId,
    slug,
    title,
    description: "A deterministic browser-test field recording.",
    recorded_at: now,
    duration_seconds: 3600,
    recorder: "ORNA test recorder",
    weather: "Clear",
    photo_url: null,
    altitude_meters: 42,
    temperature_celsius: 12.5,
    wind_speed_kph: 8.2,
    humidity_percent: 73,
    moon_phase: "Waxing crescent",
    access_level: "public",
    publication_status: "published",
    processing_status: "ready",
    media_assets: [
      {
        id: `30000000-0000-4000-8000-00000000000${id === firstSessionId ? "1" : "2"}`,
        session_id: id,
        kind: "streaming_rendition",
        mime_type: "audio/mpeg",
        processing_status: "ready",
        duration_seconds: 3600,
        size_bytes: 1024,
        checksum: null,
        revision: 1,
        is_active: true,
        archived_at: null,
        source_asset_id: null,
        metadata: {},
        created_at: now,
      },
    ],
    location,
    recording_integrity: {
      human_noise_level: "low",
      post_processing: "none",
      microphone_setup: "stereo pair",
      recordist_notes: null,
    },
    waveform: {
      session_id: id,
      duration_seconds: 3600,
      peaks: [0.15, 0.42, 0.24, 0.66, 0.31],
      sample_rate: 1,
      status: "ready",
    },
    annotations: [],
    bird_parts: {
      session_id: id,
      analysis_provider: "birdnet",
      analysis_model_version: "test",
      parts: [
        { id: `${id}-part-1`, species_code: "erirob", species_common_name: "European Robin", species_scientific_name: "Erithacus rubecula", call_type: "song", confidence: 0.91, starts_at_seconds: 120, ends_at_seconds: 126 },
        { id: `${id}-part-2`, species_code: "erirob", species_common_name: "European Robin", species_scientific_name: "Erithacus rubecula", call_type: "song", confidence: 0.87, starts_at_seconds: 240, ends_at_seconds: 247 },
        { id: `${id}-part-3`, species_code: "parmaj", species_common_name: "Great Tit", species_scientific_name: "Parus major", call_type: "call", confidence: 0.78, starts_at_seconds: 360, ends_at_seconds: 364 },
      ],
    },
    is_featured: true,
    featured_sort_order: 1,
    metadata: {},
    created_at: now,
    updated_at: now,
  };
}

const sessions = new Map([
  ["first-session", session(firstSessionId, "first-session", "First Session")],
  ["second-session", session(secondSessionId, "second-session", "Second Session")],
]);
const grantCounts = new Map();
let nextAtlasResponse = "ok";
let nextDawnResponse = "ok";
let nextSearchResponse = "ok";

function headers(extra = {}) {
  return {
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Allow-Headers": "Content-Type, Accept",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Origin": origin,
    "Content-Type": "application/json",
    ...extra,
  };
}

function send(response, status, payload, extraHeaders) {
  response.writeHead(status, headers(extraHeaders));
  response.end(payload === null ? "" : JSON.stringify(payload));
}

function grant(sessionId) {
  const count = (grantCounts.get(sessionId) ?? 0) + 1;
  grantCounts.set(sessionId, count);
  return {
    session_id: sessionId,
    status: "ready",
    stream_url: `/mock-audio/${sessionId}/${count}.mp3`,
    expires_at: new Date(Date.now() + 31_000).toISOString(),
    refresh_after_seconds: 1,
  };
}

const server = createServer((request, response) => {
  const url = new URL(request.url ?? "/", `http://${request.headers.host ?? `127.0.0.1:${port}`}`);
  const path = url.pathname;

  if (request.method === "OPTIONS") {
    send(response, 204, null);
    return;
  }
  if (path === "/health") {
    send(response, 200, { status: "ok" });
    return;
  }
  if (request.method === "POST" && path === "/__e2e/atlas-response") {
    const mode = url.searchParams.get("mode");
    if (!["valid-optional-point", "valid-boundary-fields", "locked-point", "session-navigation", "carousel-boundaries", "dawn-only-location", "multiple-dawn", "next-only-dawn", "next-only-dawn-list", "dawn-refresh-location", "invalid-date", "malformed-atlas", "malformed-point", "malformed-dawn", "malformed-dawn-refresh", "unavailable"].includes(mode)) {
      send(response, 400, { detail: "Unsupported atlas response mode" });
      return;
    }
    nextAtlasResponse = mode === "malformed-dawn" || mode === "malformed-dawn-refresh" || mode === "dawn-refresh-location" || mode === "next-only-dawn-list" ? "ok" : mode;
    nextDawnResponse = mode === "carousel-boundaries"
      ? "empty"
      : mode === "malformed-dawn" || mode === "malformed-dawn-refresh"
      ? "malformed"
      : mode === "multiple-dawn"
        ? "multiple"
        : mode === "next-only-dawn" || mode === "next-only-dawn-list"
          ? "next-only"
          : mode === "dawn-refresh-location"
            ? "before-refresh"
            : "ok";
    send(response, 204, null);
    return;
  }
  if (request.method === "POST" && path === "/__e2e/search-response") {
    const mode = url.searchParams.get("mode");
    if (!["hidden-public", "next-only-dawn"].includes(mode)) {
      send(response, 400, { detail: "Unsupported search response mode" });
      return;
    }
    nextSearchResponse = mode;
    send(response, 204, null);
    return;
  }
  if (request.method === "GET" && path === "/api/v1/auth/oauth/providers") {
    send(response, 200, { providers: ["google", "apple", "facebook"] });
    return;
  }
  if (request.method === "GET" && path === "/api/v1/sessions/featured") {
    const featured = sessions.get("first-session");
    send(response, 200, [{
      id: featured.id,
      slug: featured.slug,
      title: featured.title,
      description: featured.description,
      recorded_at: featured.recorded_at,
      duration_seconds: featured.duration_seconds,
      featured_sort_order: 1,
      location,
    }]);
    return;
  }
  if (request.method === "GET" && path === "/api/v1/collections") {
    send(response, 200, [{
      id: "40000000-0000-4000-8000-000000000001",
      slug: "wetland-dawn",
      title: "Wetland Dawn",
      description: "A test collection.",
      sort_order: 1,
      location_count: 1,
      session_count: 2,
    }]);
    return;
  }
  if (request.method === "GET" && path === "/api/v1/collections/wetland-dawn") {
    send(response, 200, {
      id: "40000000-0000-4000-8000-000000000001",
      slug: "wetland-dawn",
      title: "Wetland Dawn",
      description: "A test collection.",
      sort_order: 1,
      location_count: 1,
      session_count: 2,
      locations: [location],
      sessions: [...sessions.values()],
      metadata: {},
      created_at: now,
      updated_at: now,
    });
    return;
  }
  if (request.method === "GET" && path === "/api/v1/atlas/points") {
    const responseMode = nextAtlasResponse;
    nextAtlasResponse = "ok";
    if (responseMode === "unavailable") {
      send(response, 503, { detail: "Atlas fixture unavailable" });
      return;
    }
    if (responseMode === "malformed-atlas") {
      send(response, 200, { bbox: null, zoom: 5, mode: "points", points: "invalid", cache_key: "e2e:malformed" });
      return;
    }
    if (responseMode === "malformed-point") {
      send(response, 200, {
        bbox: null,
        zoom: 5,
        mode: "points",
        points: [{ ...atlasPoint, latest_session: {} }],
        cache_key: "e2e:malformed-point",
      });
      return;
    }
    if (responseMode === "valid-optional-point") {
      send(response, 200, {
        bbox: null,
        zoom: 5,
        mode: "points",
        points: [{ ...atlasPoint, country_code: null, latest_session: undefined }],
        cache_key: "e2e:valid-optional-point",
      });
      return;
    }
    if (responseMode === "valid-boundary-fields") {
      send(response, 200, {
        bbox: null,
        zoom: 5,
        mode: "points",
        points: [{
          ...atlasPoint,
          id: "00000000-0000-0000-0000-000000000000",
          timezone: "",
          sensitivity_level: "",
          latest_session: {
            ...atlasPoint.latest_session,
            id: "00000000-0000-0000-0000-000000000000",
            recorded_at: "2026-01-01t12:00:00z",
            duration_seconds: -1,
          },
        }],
        cache_key: "e2e:valid-boundary-fields",
      });
      return;
    }
    if (responseMode === "locked-point") {
      send(response, 200, {
        bbox: null,
        zoom: 5,
        mode: "points",
        points: [lockedPoint, atlasPoint],
        cache_key: "e2e:locked-point",
      });
      return;
    }
    if (responseMode === "session-navigation" || responseMode === "carousel-boundaries") {
      const firstPoint = {
        ...atlasPoint,
        id: "10000000-0000-4000-8000-000000000012",
        slug: "first-wetland",
        name: "First Wetland",
        latest_session: {
          ...atlasPoint.latest_session,
          id: firstSessionId,
          slug: "first-session",
          title: "First Session",
        },
      };
      const secondPoint = {
        ...ridgePoint,
        timezone: atlasPoint.timezone,
        latest_session: {
          ...atlasPoint.latest_session,
          id: secondSessionId,
          slug: "second-session",
          title: "Second Session",
        },
      };
      const thirdPoint = {
        ...secondPoint,
        id: "10000000-0000-4000-8000-000000000014",
        slug: "third-reedbed",
        name: "Third Reedbed",
        latitude: 57.42,
        longitude: 22.71,
      };
      send(response, 200, {
        bbox: null,
        zoom: 5,
        mode: "points",
        points: responseMode === "carousel-boundaries"
          ? [firstPoint, secondPoint, thirdPoint]
          : [firstPoint, secondPoint],
        cache_key: "e2e:session-navigation",
      });
      return;
    }
    if (responseMode === "invalid-date") {
      send(response, 200, {
        bbox: null,
        zoom: 5,
        mode: "points",
        points: [{
          ...atlasPoint,
          latest_session: { ...atlasPoint.latest_session, recorded_at: "2026-01-01T24:00:00Z" },
        }],
        cache_key: "e2e:invalid-date",
      });
      return;
    }
    if (responseMode === "next-only-dawn") {
      send(response, 200, {
        bbox: null,
        zoom: 5,
        mode: "points",
        points: [morningPoint, ridgePoint],
        cache_key: "e2e:next-only-dawn",
      });
      return;
    }
    if (responseMode === "multiple-dawn") {
      send(response, 200, {
        bbox: null,
        zoom: 5,
        mode: "points",
        points: [ridgePoint, atlasPoint],
        cache_key: "e2e:multiple-dawn",
      });
      return;
    }
    if (responseMode === "dawn-only-location") {
      send(response, 200, {
        bbox: null,
        zoom: 5,
        mode: "points",
        points: [],
        cache_key: "e2e:dawn-only-location",
      });
      return;
    }
    send(response, 200, { bbox: null, zoom: 5, mode: "points", points: [atlasPoint], cache_key: "e2e:atlas" });
    return;
  }
  if (request.method === "GET" && path === "/api/v1/atlas/dawn/current") {
    const responseMode = nextDawnResponse;
    nextDawnResponse = "ok";
    if (responseMode === "malformed") {
      send(response, 200, {});
      return;
    }
    const refreshSeconds = responseMode === "before-refresh" ? 1 : 60;
    const activePoints = responseMode === "empty"
      ? []
      : responseMode === "multiple"
      ? [atlasPoint, ridgePoint]
      : responseMode === "after-refresh"
        ? [ridgePoint]
        : responseMode === "next-only"
          ? []
          : [atlasPoint];
    const nextPoints = responseMode === "next-only" ? [ridgePoint] : [];
    if (responseMode === "before-refresh") {
      nextDawnResponse = "after-refresh";
    }
    send(response, 200, {
      generated_at: now,
      window: { before_minutes: 45, after_minutes: 30, refresh_seconds: refreshSeconds },
      active_locations: activePoints.map((point) => ({
        location: point,
        local_date: "2026-07-14",
        local_time: "23:00",
        civil_dawn_at: null,
        sunrise_at: null,
        sunset_at: null,
        civil_dusk_at: null,
        window_starts_at: null,
        window_ends_at: null,
        minutes_until_sunrise: 30,
        state: "active",
        solar_phase: "civil_dawn",
      })),
      next_locations: nextPoints.map((point) => ({
        location: point,
        local_date: "2026-07-14",
        local_time: "23:00",
        civil_dawn_at: null,
        sunrise_at: null,
        sunset_at: null,
        civil_dusk_at: null,
        window_starts_at: null,
        window_ends_at: null,
        minutes_until_sunrise: 360,
        state: "upcoming",
        solar_phase: "night",
      })),
      cache_key: `e2e:dawn:${responseMode}`,
    });
    return;
  }
  if (request.method === "GET" && path === "/api/v1/search") {
    const responseMode = nextSearchResponse;
    nextSearchResponse = "ok";
    if (responseMode === "next-only-dawn") {
      send(response, 200, [{
        type: "location",
        id: ridgePoint.id,
        slug: ridgePoint.slug,
        title: ridgePoint.name,
        subtitle: ridgePoint.region,
        habitat: ridgePoint.habitat,
        latitude: ridgePoint.latitude,
        longitude: ridgePoint.longitude,
        session_slug: null,
        atlas_point: ridgePoint,
      }]);
      return;
    }
    if (responseMode === "hidden-public") {
      const hiddenPoint = {
        ...atlasPoint,
        id: "00000000-0000-4000-8000-000000000099",
        slug: "hidden-roost",
        name: "Hidden Roost",
        coordinate_visibility: "hidden_public",
      };
      send(response, 200, [{
        type: "location",
        id: hiddenPoint.id,
        slug: hiddenPoint.slug,
        title: hiddenPoint.name,
        subtitle: null,
        habitat: null,
        latitude: hiddenPoint.latitude,
        longitude: hiddenPoint.longitude,
        session_slug: null,
        atlas_point: hiddenPoint,
      }]);
      return;
    }
    send(response, 200, [{
      type: "location",
      id: locationId,
      slug: location.slug,
      title: location.name,
      subtitle: location.region,
      habitat: location.habitat,
      latitude: location.latitude,
      longitude: location.longitude,
      session_slug: null,
      atlas_point: atlasPoint,
    }]);
    return;
  }
  const sessionMatch = path.match(/^\/api\/v1\/sessions\/([^/]+)$/);
  if (request.method === "GET" && sessionMatch) {
    const selected = sessions.get(decodeURIComponent(sessionMatch[1]));
    send(response, selected ? 200 : 404, selected ?? { detail: "Session not found" });
    return;
  }
  const grantMatch = path.match(/^\/api\/v1\/sessions\/([^/]+)\/playback-grants$/);
  if (request.method === "POST" && grantMatch) {
    const selected = [...sessions.values()].find((item) => item.id === grantMatch[1]);
    send(response, selected ? 200 : 404, selected ? grant(selected.id) : { detail: "Session not found" });
    return;
  }
  if (request.method === "GET" && path === "/api/v1/users/me") {
    send(response, 401, { detail: "Not authenticated" });
    return;
  }
  if (request.method === "GET" && path === "/api/v1/memberships/me") {
    send(response, 401, { detail: "Not authenticated" });
    return;
  }
  if (request.method === "POST" && path === "/api/v1/auth/magic-link/request") {
    send(response, 202, { accepted: true });
    return;
  }
  if (request.method === "POST" && path === "/api/v1/auth/login") {
    send(response, 200, {
      access_token: "e2e-token",
      token_type: "bearer",
      expires_at: new Date(Date.now() + 3600_000).toISOString(),
      user: {
        id: "50000000-0000-4000-8000-000000000001",
        email: "member@example.com",
        role: "member",
        is_active: true,
        created_at: now,
      },
    });
    return;
  }

  send(response, 404, { detail: `No e2e fixture for ${request.method} ${path}` });
});

server.listen(port, "127.0.0.1");

function stop() {
  server.close(() => process.exit(0));
}

process.on("SIGINT", stop);
process.on("SIGTERM", stop);
