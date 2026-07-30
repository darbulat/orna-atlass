import type { components } from "./generated";

export type AdminLocationRow = components["schemas"]["AdminLocationRead"];
export type AdminSessionRow = components["schemas"]["AdminSessionResource"];
export type AdminCollectionRow = components["schemas"]["AdminCollectionResource"];
type AdminUserResource = components["schemas"]["AdminUserResource"];
export type AdminUserRow = {
  id: AdminUserResource["user"]["id"];
  email: AdminUserResource["user"]["email"];
  role: AdminUserResource["user"]["role"];
  is_active: AdminUserResource["user"]["is_active"];
  created_at: AdminUserResource["user"]["created_at"];
  membership_status: AdminUserResource["membership"]["status"];
  revision: AdminUserResource["revision"];
};
export type AdminAuditRow = components["schemas"]["AuditEventRead"];

export type AdminListState<T> =
  | { kind: "empty" }
  | { kind: "unsupported"; status: number; message: string }
  | { kind: "error"; status: number; message: string }
  | { kind: "ok"; items: T[] };

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const RFC3339_PATTERN = /^\d{4}-\d{2}-\d{2}[tT]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[zZ]|[+-]\d{2}:\d{2})$/;

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireString(value: unknown, field: string): string {
  if (typeof value !== "string") throw new Error(`Invalid privileged field: ${field}`);
  return value;
}

function requireUuid(value: unknown, field: string): string {
  const result = requireString(value, field);
  if (!UUID_PATTERN.test(result)) throw new Error(`Invalid privileged UUID: ${field}`);
  return result;
}

function requireDateTime(value: unknown, field: string): string {
  const result = requireString(value, field);
  if (!RFC3339_PATTERN.test(result) || Number.isNaN(Date.parse(result))) {
    throw new Error(`Invalid privileged date-time: ${field}`);
  }
  return result;
}

function requireNullableString(value: unknown, field: string): string | null {
  if (value === null) return null;
  return requireString(value, field);
}

function requireOptionalNullableString(value: unknown, field: string): void {
  if (value !== undefined && value !== null && typeof value !== "string") {
    throw new Error(`Invalid privileged nullable field: ${field}`);
  }
}

function requireBoolean(value: unknown, field: string): boolean {
  if (typeof value !== "boolean") throw new Error(`Invalid privileged boolean: ${field}`);
  return value;
}

function requireNumber(value: unknown, field: string, minimum?: number, maximum?: number): number {
  if (
    typeof value !== "number"
    || !Number.isFinite(value)
    || (minimum !== undefined && value < minimum)
    || (maximum !== undefined && value > maximum)
  ) {
    throw new Error(`Invalid privileged number: ${field}`);
  }
  return value;
}

function requireOptionalNullableNumber(value: unknown, field: string): void {
  if (value !== undefined && value !== null && (typeof value !== "number" || !Number.isFinite(value))) {
    throw new Error(`Invalid privileged nullable number: ${field}`);
  }
}

function requireEnum<T extends string>(value: unknown, allowed: readonly T[], field: string): T {
  if (typeof value !== "string" || !allowed.includes(value as T)) {
    throw new Error(`Invalid privileged enum: ${field}`);
  }
  return value as T;
}

function requireRecord(value: unknown, field: string): Record<string, unknown> {
  if (!isRecord(value)) throw new Error(`Invalid privileged object: ${field}`);
  return value;
}

function requireOptionalUuidArray(value: unknown, field: string): void {
  if (value === undefined) return;
  if (!Array.isArray(value) || !value.every((entry) => typeof entry === "string" && UUID_PATTERN.test(entry))) {
    throw new Error(`Invalid privileged UUID array: ${field}`);
  }
}

function unwrapAdminListPayload(payload: unknown): unknown[] {
  if (Array.isArray(payload)) return payload;
  if (!isRecord(payload)) throw new Error("Invalid admin list payload");
  if (Array.isArray(payload.items)) return payload.items;
  if (Array.isArray(payload.data)) return payload.data;
  throw new Error("Invalid admin list envelope");
}

export function parseLocationRows(payload: unknown): AdminLocationRow[] {
  return unwrapAdminListPayload(payload).map((value) => {
    const item = requireRecord(value, "location");
    requireUuid(item.id, "location.id");
    requireString(item.name, "location.name");
    requireString(item.slug, "location.slug");
    requireNullableString(item.description, "location.description");
    requireNullableString(item.country_code, "location.country_code");
    requireNullableString(item.region, "location.region");
    requireNullableString(item.habitat, "location.habitat");
    requireNumber(item.exact_latitude, "location.exact_latitude", -90, 90);
    requireNumber(item.exact_longitude, "location.exact_longitude", -180, 180);
    requireOptionalNullableNumber(item.public_latitude, "location.public_latitude");
    requireOptionalNullableNumber(item.public_longitude, "location.public_longitude");
    requireEnum(item.coordinate_visibility, ["exact_public", "approximate_public", "hidden_public"], "location.coordinate_visibility");
    requireEnum(item.sensitivity_level, ["none", "low", "medium", "high", "protected"], "location.sensitivity_level");
    requireString(item.timezone, "location.timezone");
    requireRecord(item.metadata, "location.metadata");
    requireOptionalNullableString(item.archived_at, "location.archived_at");
    if (typeof item.archived_at === "string") requireDateTime(item.archived_at, "location.archived_at");
    requireDateTime(item.created_at, "location.created_at");
    requireDateTime(item.updated_at, "location.updated_at");
    requireString(item.revision, "location.revision");
    return item as unknown as AdminLocationRow;
  });
}

export function parseSessionRows(payload: unknown): AdminSessionRow[] {
  return unwrapAdminListPayload(payload).map((value) => {
    const item = requireRecord(value, "session");
    requireUuid(item.id, "session.id");
    requireUuid(item.location_id, "session.location_id");
    requireString(item.title, "session.title");
    requireString(item.slug, "session.slug");
    requireEnum(item.publication_status, ["draft", "published", "archived"], "session.publication_status");
    requireEnum(item.processing_status, ["pending", "processing", "ready", "failed"], "session.processing_status");
    requireEnum(item.access_level, ["public", "members_only", "private"], "session.access_level");
    requireBoolean(item.is_featured, "session.is_featured");
    requireRecord(item.metadata, "session.metadata");
    requireDateTime(item.recorded_at, "session.recorded_at");
    requireDateTime(item.created_at, "session.created_at");
    requireDateTime(item.updated_at, "session.updated_at");
    requireString(item.revision, "session.revision");
    requireOptionalNullableString(item.description, "session.description");
    requireOptionalNullableString(item.recorder, "session.recorder");
    requireOptionalNullableString(item.weather, "session.weather");
    requireOptionalNullableNumber(item.duration_seconds, "session.duration_seconds");
    requireOptionalNullableNumber(item.featured_sort_order, "session.featured_sort_order");
    if (item.media_assets !== undefined && !Array.isArray(item.media_assets)) {
      throw new Error("Invalid privileged array: session.media_assets");
    }
    return item as unknown as AdminSessionRow;
  });
}

export function parseCollectionRows(payload: unknown): AdminCollectionRow[] {
  return unwrapAdminListPayload(payload).map((value) => {
    const item = requireRecord(value, "collection");
    requireUuid(item.id, "collection.id");
    requireString(item.title, "collection.title");
    requireString(item.slug, "collection.slug");
    requireNullableString(item.description, "collection.description");
    requireBoolean(item.is_public, "collection.is_public");
    requireNumber(item.sort_order, "collection.sort_order");
    requireRecord(item.metadata, "collection.metadata");
    requireOptionalUuidArray(item.location_ids, "collection.location_ids");
    requireOptionalUuidArray(item.session_ids, "collection.session_ids");
    requireDateTime(item.created_at, "collection.created_at");
    requireDateTime(item.updated_at, "collection.updated_at");
    requireString(item.revision, "collection.revision");
    return item as unknown as AdminCollectionRow;
  });
}

export function parseAdminUserRows(payload: unknown): AdminUserRow[] {
  return unwrapAdminListPayload(payload).map((value) => {
    const item = requireRecord(value, "user aggregate");
    const user = requireRecord(item.user, "user aggregate.user");
    const membership = requireRecord(item.membership, "user aggregate.membership");
    requireUuid(user.id, "user.id");
    requireString(user.email, "user.email");
    requireBoolean(user.email_verified, "user.email_verified");
    requireEnum(user.role, ["member", "editor", "admin"], "user.role");
    requireBoolean(user.is_active, "user.is_active");
    requireDateTime(user.created_at, "user.created_at");
    requireUuid(membership.user_id, "membership.user_id");
    requireEnum(membership.status, ["inactive", "active", "cancelled", "expired"], "membership.status");
    requireString(membership.plan, "membership.plan");
    requireBoolean(membership.is_entitled, "membership.is_entitled");
    requireOptionalNullableString(membership.id, "membership.id");
    if (typeof membership.id === "string") requireUuid(membership.id, "membership.id");
    requireOptionalNullableString(membership.starts_at, "membership.starts_at");
    requireOptionalNullableString(membership.expires_at, "membership.expires_at");
    if (typeof membership.starts_at === "string") requireDateTime(membership.starts_at, "membership.starts_at");
    if (typeof membership.expires_at === "string") requireDateTime(membership.expires_at, "membership.expires_at");
    requireString(item.revision, "user aggregate.revision");
    return {
      id: user.id as string,
      email: user.email as string,
      role: user.role as AdminUserRow["role"],
      is_active: user.is_active as boolean,
      created_at: user.created_at as string,
      membership_status: membership.status as AdminUserRow["membership_status"],
      revision: item.revision as string,
    };
  });
}

export function parseAuditRows(payload: unknown): AdminAuditRow[] {
  return unwrapAdminListPayload(payload).map((value) => {
    const item = requireRecord(value, "audit");
    requireUuid(item.id, "audit.id");
    requireString(item.event_type, "audit.event_type");
    requireString(item.subject_type, "audit.subject_type");
    requireNullableString(item.subject_id, "audit.subject_id");
    requireNullableString(item.actor_user_id, "audit.actor_user_id");
    requireNullableString(item.ip_address, "audit.ip_address");
    requireNullableString(item.user_agent, "audit.user_agent");
    requireRecord(item.metadata, "audit.metadata");
    requireDateTime(item.created_at, "audit.created_at");
    return item as unknown as AdminAuditRow;
  });
}

export function buildAdminUrl(path: string, params: Record<string, string | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) query.set(key, value);
  }
  return query.size ? `${path}?${query.toString()}` : path;
}
