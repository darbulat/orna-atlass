import { createServer } from "node:http";

const port = Number(process.env.PORT ?? 4010);
const origin = process.env.WEB_ORIGIN ?? "http://127.0.0.1:3100";
const locationId = "10000000-0000-4000-8000-000000000001";
const firstSessionId = "20000000-0000-4000-8000-000000000001";
const secondSessionId = "20000000-0000-4000-8000-000000000002";
const now = "2026-07-14T23:00:00Z";
const adminLocationId = "11000000-0000-4000-8000-000000000001";
const adminSessionId = "21000000-0000-4000-8000-000000000001";
const adminCollectionId = "41000000-0000-4000-8000-000000000001";
const adminUserId = "51000000-0000-4000-8000-000000000001";
let nextAdminMutation = "ok";
let adminAccessRevoked = false;
let adminRefreshPending = false;
let holdNextAdminIdentity = false;
let heldAdminIdentityResponse = null;
const adminRequestCounts = new Map();

function countAdminRequest(method, path) {
  const key = `${method} ${path}`;
  adminRequestCounts.set(key, (adminRequestCounts.get(key) ?? 0) + 1);
}

function adminStatePayload() {
  return {
    access_revoked: adminAccessRevoked,
    refresh_pending: adminRefreshPending,
    identity_held: heldAdminIdentityResponse !== null,
    request_counts: Object.fromEntries(adminRequestCounts.entries()),
  };
}

const adminLocation = {
  id: adminLocationId,
  slug: "hidden-nesting-site",
  name: "Hidden Nesting Site",
  description: "Admin-only location fixture.",
  country_code: "EE",
  region: "Harju",
  habitat: "Wetland",
  exact_latitude: 59.555555,
  exact_longitude: 24.555555,
  public_latitude: 11.111111,
  public_longitude: 22.222222,
  coordinate_visibility: "hidden_public",
  sensitivity_level: "protected",
  timezone: "UTC",
  metadata: {},
  archived_at: null,
  created_at: now,
  updated_at: now,
  revision: 'W/"location-r1"',
};
const initialAdminLocationName = adminLocation.name;
const initialAdminLocationUpdatedAt = adminLocation.updated_at;
const initialAdminLocationRevision = adminLocation.revision;

const adminSession = {
  id: adminSessionId,
  location_id: adminLocationId,
  slug: "draft-admin-session",
  title: "Draft Admin Session",
  recorded_at: now,
  access_level: "private",
  publication_status: "draft",
  processing_status: "pending",
  is_featured: false,
  metadata: {},
  created_at: now,
  updated_at: now,
  revision: 'W/"session-r1"',
};

const adminCollection = {
  id: adminCollectionId,
  slug: "admin-collection",
  title: "Admin Collection",
  description: null,
  is_public: false,
  sort_order: 0,
  metadata: {},
  location_ids: [adminLocationId],
  session_ids: [adminSessionId],
  created_at: now,
  updated_at: now,
  revision: 'W/"collection-r1"',
};

const adminUser = {
  user: {
    id: adminUserId,
    email: "target-admin@example.test",
    email_verified: true,
    role: "admin",
    is_active: true,
    created_at: now,
  },
  revision: 'W/"user-r1"',
  membership: {
    id: "61000000-0000-4000-8000-000000000001",
    user_id: adminUserId,
    plan: "member",
    status: "active",
    is_entitled: true,
    starts_at: now,
    expires_at: null,
  },
};

const adminAudit = {
  id: "71000000-0000-4000-8000-000000000001",
  actor_user_id: adminUserId,
  event_type: "location.updated",
  subject_type: "location",
  subject_id: adminLocationId,
  ip_address: "192.0.2.10",
  user_agent: "ORNA e2e browser",
  metadata: { changed_fields: ["name"] },
  created_at: now,
};

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
  photo_url: "http://127.0.0.1:4010/mock-location-photo-v2.png",
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
let sessionDetailAuthState = "ok";
let sessionDetailAuthReads = 0;
let sessionDetailRefreshCalls = 0;
let nextSearchResponse = "ok";
let lastAtlasCookie = "";

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
  if (request.method === "POST" && path === "/__e2e/admin-mutation") {
    const mode = url.searchParams.get("mode");
    if (!["ok", "stale", "unavailable"].includes(mode)) {
      send(response, 400, { detail: "Unsupported admin mutation mode" });
      return;
    }
    nextAdminMutation = mode;
    send(response, 204, null);
    return;
  }
  if (path === "/__e2e/admin-state" && request.method === "POST") {
    adminAccessRevoked = url.searchParams.get("revoked") === "true";
    adminRefreshPending = url.searchParams.get("unauthorized_once") === "true";
    if (url.searchParams.get("hold_next_identity") === "true") {
      holdNextAdminIdentity = true;
    }
    if (url.searchParams.get("release_identity") === "true" && heldAdminIdentityResponse !== null) {
      send(
        heldAdminIdentityResponse,
        200,
        { id: adminUserId, role: "admin", is_admin: true, mode: "token" },
        { "Cache-Control": "no-store" },
      );
      heldAdminIdentityResponse = null;
    }
    if (url.searchParams.get("reset") === "true") {
      adminRequestCounts.clear();
      nextAdminMutation = "ok";
      adminLocation.name = initialAdminLocationName;
      adminLocation.updated_at = initialAdminLocationUpdatedAt;
      adminLocation.revision = initialAdminLocationRevision;
      holdNextAdminIdentity = false;
      if (heldAdminIdentityResponse !== null) {
        heldAdminIdentityResponse.destroy();
        heldAdminIdentityResponse = null;
      }
    }
    send(response, 204, null);
    return;
  }
  if (path === "/__e2e/admin-state" && request.method === "GET") {
    send(response, 200, adminStatePayload());
    return;
  }
  const cookie = request.headers.cookie ?? "";
  const hasAdminCookie = cookie.includes("orna_access=admin-e2e")
    || cookie.includes("orna_access=malformed-admin-e2e")
    || cookie.includes("orna_access=pagination-admin-e2e")
    || cookie.includes("orna_access=stale-admin-e2e")
    || cookie.includes("orna_access=unavailable-admin-e2e");
  const hasMemberCookie = cookie.includes("orna_access=member-e2e");
  if (path.startsWith("/api/v1/admin/")) countAdminRequest(request.method ?? "GET", path);
  if (request.method === "GET" && path === "/api/v1/admin/me") {
    if (holdNextAdminIdentity && hasAdminCookie) {
      holdNextAdminIdentity = false;
      heldAdminIdentityResponse = response;
      return;
    }
    if (adminRefreshPending) {
      send(response, 401, { detail: "Access token expired" });
      return;
    }
    if (hasMemberCookie || adminAccessRevoked) {
      send(response, 403, { detail: "Admin role required" });
      return;
    }
    if (!hasAdminCookie) {
      send(response, 401, { detail: "Authentication is required" });
      return;
    }
    send(response, 200, { id: adminUserId, role: "admin", is_admin: true, mode: "token" }, { "Cache-Control": "no-store" });
    return;
  }
  if (hasAdminCookie && request.method === "GET" && path === "/api/v1/admin/locations") {
    const pageLimit = Math.min(100, Math.max(1, Number.parseInt(url.searchParams.get("limit") ?? "50", 10) || 50));
    const payload = cookie.includes("malformed-admin-e2e")
      ? [{ ...adminLocation, coordinate_visibility: "unknown_privileged_state" }]
      : cookie.includes("pagination-admin-e2e")
        ? Array.from({ length: pageLimit }, (_, index) => ({
            ...adminLocation,
            id: `11000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
          }))
        : [adminLocation];
    send(response, 200, payload, { "Cache-Control": "no-store" });
    return;
  }
  if (hasAdminCookie && request.method === "GET" && path === "/api/v1/admin/sessions") {
    send(response, 200, [adminSession], { "Cache-Control": "no-store" });
    return;
  }
  if (hasAdminCookie && request.method === "GET" && path === "/api/v1/admin/collections") {
    send(response, 200, [adminCollection], { "Cache-Control": "no-store" });
    return;
  }
  if (hasAdminCookie && request.method === "GET" && path === "/api/v1/admin/users") {
    send(response, 200, [adminUser], { "Cache-Control": "no-store" });
    return;
  }
  if (hasAdminCookie && request.method === "GET" && path === `/api/v1/admin/users/${adminUserId}`) {
    send(response, 200, adminUser, { ETag: adminUser.revision, "Cache-Control": "no-store" });
    return;
  }
  if (hasAdminCookie && request.method === "GET" && path === "/api/v1/admin/audit-events") {
    send(response, 200, [adminAudit], { "Cache-Control": "no-store" });
    return;
  }
  if (hasAdminCookie && request.method === "PATCH" && path === `/api/v1/admin/locations/${adminLocationId}`) {
    if (request.headers["if-match"] !== adminLocation.revision) {
      send(response, 412, { detail: "Resource changed" }, { "Cache-Control": "no-store" });
      return;
    }
    adminLocation.name = "Renamed location";
    adminLocation.updated_at = "2026-07-14T23:01:00Z";
    adminLocation.revision = 'W/"location-r2"';
    send(response, 200, adminLocation, { ETag: adminLocation.revision, "Cache-Control": "no-store" });
    return;
  }
  const isAdminMutation = hasAdminCookie
    && request.method !== "GET"
    && path.startsWith("/api/v1/admin/");
  if (isAdminMutation) {
    if (cookie.includes("orna_access=stale-admin-e2e") || nextAdminMutation === "stale") {
      nextAdminMutation = "ok";
      send(response, 412, { detail: "Resource changed" });
      return;
    }
    if (cookie.includes("orna_access=unavailable-admin-e2e") || nextAdminMutation === "unavailable") {
      nextAdminMutation = "ok";
      send(response, 503, { detail: "Dependency unavailable" });
      return;
    }
    send(response, request.method === "POST" ? 201 : 200, { status: "queued" }, { "Cache-Control": "no-store" });
    return;
  }

  if (path === "/mock-location-photo-v2.png") {
    response.writeHead(200, {
      "Access-Control-Allow-Origin": origin,
      "Cache-Control": "no-store",
      "Content-Type": "image/png",
    });
    response.end(Buffer.from("iVBORw0KGgoAAAANSUhEUgAAACAAAAASCAIAAAC1qksFAAAAJElEQVR42mNMqMhioCVgYqAxGLVg1IJRC0YtGLVg1AIGBgYGABOzAWYcuWFqAAAAAElFTkSuQmCC", "base64"));
    return;
  }
  if (request.method === "POST" && path === "/api/v1/auth/refresh") {
    if (adminRefreshPending) {
      adminRefreshPending = false;
      send(response, 200, { access_token: "refreshed-admin" });
      return;
    }
    if (["expired-until-refresh", "hidden-until-refresh"].includes(sessionDetailAuthState)) {
      sessionDetailRefreshCalls += 1;
      sessionDetailAuthState = "ok";
      send(response, 200, { access_token: "refreshed" });
      return;
    }
    send(response, 401, { detail: "Authentication is required" }, {
      "Set-Cookie": [
        "orna_access=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax",
        "orna_refresh=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax",
      ],
    });
    return;
  }
  if (request.method === "POST" && path === "/__e2e/session-detail-auth") {
    const mode = url.searchParams.get("mode");
    if (!["expired-until-refresh", "hidden-until-refresh"].includes(mode)) {
      send(response, 400, { detail: "Unsupported session detail auth mode" });
      return;
    }
    sessionDetailAuthState = mode;
    sessionDetailAuthReads = 0;
    sessionDetailRefreshCalls = 0;
    send(response, 204, null);
    return;
  }
  if (request.method === "GET" && path === "/__e2e/session-detail-auth") {
    send(response, 200, {
      detail_reads: sessionDetailAuthReads,
      refresh_calls: sessionDetailRefreshCalls,
      state: sessionDetailAuthState,
    });
    return;
  }
  if (request.method === "GET" && path === "/__e2e/atlas-request") {
    send(response, 200, { cookie: lastAtlasCookie });
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
    if (!["hidden-public", "next-only-dawn", "session-pine-marsh"].includes(mode)) {
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
    lastAtlasCookie = request.headers.cookie ?? "";
    if (lastAtlasCookie.includes("orna_refresh=invalid-refresh-e2e")) {
      send(response, 401, { detail: "Access authentication requires refresh" });
      return;
    }
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
        points: [{ ...atlasPoint, country_code: null, photo_url: null, latest_session: undefined }],
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
    if (responseMode === "session-pine-marsh") {
      send(response, 200, [{
        type: "session",
        id: firstSessionId,
        slug: atlasPoint.slug,
        title: "First Session",
        subtitle: atlasPoint.name,
        habitat: atlasPoint.habitat,
        latitude: atlasPoint.latitude,
        longitude: atlasPoint.longitude,
        session_slug: "first-session",
        atlas_point: atlasPoint,
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
    sessionDetailAuthReads += 1;
    if (sessionDetailAuthState === "hidden-until-refresh") {
      send(response, 404, { detail: "Session not found" });
      return;
    }
    if (sessionDetailAuthState === "expired-until-refresh") {
      send(response, 401, { detail: "Access token expired" });
      return;
    }

    if (decodeURIComponent(sessionMatch[1]) === "members-cove-long-form") {
      send(response, 404, { detail: "Session not found" });
      return;
    }
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
  if (request.method === "GET" && path === "/api/v1/billing/offer") {
    send(response, 200, {
      product_code: "lifetime_member",
      name: "Lifetime Member Access",
      description: "Permanent access to available members-only field recordings.",
      amount_minor: 200,
      currency: "KZT",
      is_recurring: false,
      checkout_available: false,
      refund_summary: "Full refund requests are accepted within 14 calendar days.",
    });
    return;
  }
  if (request.method === "GET" && path === "/api/v1/billing/purchases/me") {
    send(response, 200, []);
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
