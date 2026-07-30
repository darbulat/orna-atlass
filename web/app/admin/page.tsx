import Link from "next/link";
import { cookies, headers as requestHeaders } from "next/headers";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { apiUrl } from "../../lib/api/sessions";
import {
  SensitiveUserSearch,
  type SensitiveUserSearchState,
} from "../../components/admin/SensitiveUserSearch";
import { AdminSessionGuard } from "../../components/admin/AdminSessionGuard";
import {
  SensitiveOperationalSearch,
  type SensitiveOperationalSearchState,
} from "../../components/admin/SensitiveOperationalSearch";
import {
  buildAdminUrl,
  isRecord,
  parseAdminUserRows,
  parseAuditRows,
  parseCollectionRows,
  parseLocationRows,
  parseSessionRows,
  type AdminAuditRow,
  type AdminCollectionRow,
  type AdminListState,
  type AdminLocationRow,
  type AdminSessionRow,
  type AdminUserRow,
} from "../../lib/api/admin";

export const dynamic = "force-dynamic";
export const revalidate = 0;
export const fetchCache = "force-no-store";

const PAGE_STEP = 50;
const AUDIT_PAGE_STEP = 100;
const MAX_PAGE_LIMIT = 100;
const MAX_AUDIT_LIMIT = 500;

type SearchParams = {
  include_archived?: string | string[];
  location_q?: string | string[];
  location_coordinate_visibility?: string | string[];
  location_sensitivity_level?: string | string[];
  session_q?: string | string[];
  session_publication_status?: string | string[];
  session_processing_status?: string | string[];
  session_access_level?: string | string[];
  collection_q?: string | string[];
  collection_is_public?: string | string[];
  user_role?: string | string[];

  user_is_active?: string | string[];
  user_membership_status?: string | string[];
  audit_event_type?: string | string[];
  audit_subject_type?: string | string[];
  audit_created_from?: string | string[];
  audit_created_to?: string | string[];

  locations_limit?: string | string[];
  sessions_limit?: string | string[];
  collections_limit?: string | string[];
  users_limit?: string | string[];
  audits_limit?: string | string[];
  notice?: string | string[];
  notice_kind?: string | string[];
  notice_section?: string | string[];
};

type AdminOperationResult =
  | { kind: "success"; message: string; section: string }
  | { kind: "error"; message: string; section: string };

type AdminMeState =
  | { status: "unauthenticated"; message: string }
  | { status: "forbidden"; message: string }
  | { status: "unavailable"; message: string; details?: string }
  | { status: "ok"; identity: AdminIdentity };

type AdminIdentity = {
  id?: string;
  is_admin?: boolean;
  role?: string;
  mode?: string;
};


async function readAdminIdentity(cookieHeader: string): Promise<AdminMeState> {
  const response = await fetch(apiUrl("/api/v1/admin/me"), {
    headers: buildRequestHeaders(cookieHeader),
    cache: "no-store",
    method: "GET",
  });

  if (response.status === 401) {
    return { status: "unauthenticated", message: "Требуется вход в аккаунт." };
  }
  if (response.status === 403) {
    return { status: "forbidden", message: "У вас нет прав для админ-панели." };
  }
  if (!response.ok) {
    const details = await readErrorDetails(response);
    return {
      status: "unavailable",
      message: `Сервис админки вернул ${response.status}.`,
      details: details || undefined,
    };
  }

  try {
    const payload = await response.json();
    if (
      !isRecord(payload)
      || typeof payload.id !== "string"
      || payload.role !== "admin"
      || payload.is_admin !== true
      || (payload.mode !== "token" && payload.mode !== "local")
    ) {
      return { status: "unavailable", message: "Админ API вернул невалидный payload." };
    }
    const identityPayload = payload as Record<string, unknown>;
    return {
      status: "ok",
      identity: {
        id: asString(identityPayload.id),
        is_admin: asBoolean(identityPayload.is_admin),
        role: asString(identityPayload.role),
        mode: asString(identityPayload.mode),
      },
    };
  } catch {
    return { status: "unavailable", message: "Админ API вернул невалидный JSON." };
  }
}

async function readAdminList<T>(
  path: string,
  cookieHeader: string,
  normalize: (payload: unknown) => T[],
): Promise<AdminListState<T>> {
  const response = await fetch(apiUrl(path), {
    headers: buildRequestHeaders(cookieHeader),
    cache: "no-store",
    method: "GET",
  });

  if (response.status === 204) {
    return { kind: "empty" };
  }

  if (response.status === 404 || response.status === 405 || response.status === 501) {
    return {
      kind: "unsupported",
      status: response.status,
      message: "Этот списокный endpoint пока недоступен в текущем API.",
    };
  }

  if (!response.ok) {
    const details = await readErrorDetails(response);
    return {
      kind: "error",
      status: response.status,
      message: details || `Админ API вернул ${response.status}`,
    };
  }

  try {
    const payload = await response.json();
    const normalized = normalize(payload);
    return normalized.length === 0 ? { kind: "empty" } : { kind: "ok", items: normalized };
  } catch {
    return { kind: "error", status: response.status, message: "Сбой чтения данных админ-API." };
  }
}

function buildRequestHeaders(cookieHeader: string): Record<string, string> {
  return cookieHeader
    ? {
        cookie: cookieHeader,
        Accept: "application/json",
      }
    : { Accept: "application/json" };
}

async function readErrorDetails(response: Response): Promise<string | null> {
  try {
    const payload = await response.json();
    if (isRecord(payload) && typeof payload.detail === "string") {
      return payload.detail;
    }
  } catch {
    return null;
  }
  return null;
}

function normalizeSearchValue(value: string | string[] | undefined): string {
  if (Array.isArray(value)) return value[0]?.trim() ?? "";
  return value?.trim() ?? "";
}

function buildNoticeRedirect(
  section: string,
  kind: AdminOperationResult["kind"],
  message: string,
): string {
  const params = new URLSearchParams();
  params.set("notice_section", section);
  params.set("notice_kind", kind);
  params.set("notice", message.slice(0, 180));
  return `/admin?${params.toString()}`;
}

function buildOperationNoticeRedirect(
  section: string,
  kind: AdminOperationResult["kind"],
  _message: string,
  _formData?: FormData,
  status?: number,
): string {
  const genericMessage = kind === "success"
    ? "Операция выполнена."
    : status === 412
      ? "Запись была изменена другим администратором. Обновите список и используйте новую revision."
      : status === 428
        ? "Для изменения требуется актуальная revision / If-Match."
        : status === 403
          ? "Операция запрещена текущей политикой доступа."
          : typeof status === "number"
            ? `Операция отклонена (HTTP ${status}).`
            : "Операция отклонена.";
  return buildNoticeRedirect(section, kind, genericMessage);
}

function parseFormString(formData: FormData, name: string, max = 200): string | undefined {
  const value = formData.get(name);
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  return trimmed.slice(0, max);
}

function parseFormNumber(formData: FormData, name: string): number | undefined {
  const value = parseFormString(formData, name, 80);
  if (!value) return undefined;
  const num = Number(value);
  return Number.isFinite(num) ? num : undefined;
}

function parseFormBoolean(formData: FormData, name: string): boolean | undefined {
  const value = parseFormString(formData, name, 20);
  if (value === undefined) return undefined;
  if (["true", "1", "on", "yes"].includes(value.toLowerCase())) return true;
  if (["false", "0", "off", "no"].includes(value.toLowerCase())) return false;
  return undefined;
}

function parseFormUuidArray(
  formData: FormData,
  name: string,
  required: boolean,
): string[] | undefined {
  const raw = parseFormString(formData, name, 12000);
  if (!raw) return required ? [] : undefined;
  const parsed = JSON.parse(raw);
  if (!Array.isArray(parsed) || parsed.length > 200) {
    throw new Error("UUID list must be a JSON array with at most 200 items");
  }
  const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  if (!parsed.every((value) => typeof value === "string" && uuidPattern.test(value))) {
    throw new Error("UUID list contains an invalid value");
  }
  return parsed;
}

async function buildAdminCookiesHeader(): Promise<string> {
  const requestCookies = await cookies();
  return requestCookies
    .getAll()
    .map((cookie) => `${cookie.name}=${cookie.value}`)
    .join(";");
}

async function executeAdminMutation(
  path: string,
  method: "POST" | "PUT" | "PATCH" | "DELETE",
  payload?: Record<string, unknown>,
  ifMatch?: string,
): Promise<{ ok: boolean; status: number; message: string }> {
  const cookieHeader = await buildAdminCookiesHeader();
  const headers: Record<string, string> = buildRequestHeaders(cookieHeader);
  const origin = (await requestHeaders()).get("origin");
  if (origin) headers.Origin = origin;
  if (method !== "DELETE") headers["Content-Type"] = "application/json";
  if (ifMatch) headers["If-Match"] = ifMatch;

  const request: RequestInit = {
    method,
    headers,
    cache: "no-store",
  };

  if (payload && method !== "DELETE") {
    request.body = JSON.stringify(payload);
  }

  try {
    const response = await fetch(apiUrl(path), request);
    if (response.ok) {
      return { ok: true, status: response.status, message: "Операция выполнена." };
    }

    const details = await readErrorDetails(response);
    const statusMessage = response.status === 412
      ? "Запись была изменена другим администратором. Обновите список и используйте новую revision."
      : response.status === 428
        ? "Для операции требуется revision / If-Match из текущего списка."
        : response.status === 409
          ? "Операция конфликтует с текущим состоянием ресурса."
          : response.status === 422
            ? "Поля формы не прошли валидацию API."
            : undefined;
    return {
      ok: false,
      status: response.status,
      message: statusMessage || details || `Запрос вернул статус ${response.status}`,
    };
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : "Внутренняя ошибка";
    return { ok: false, status: 0, message: errorMessage };
  }
}

async function searchAdminUsersByEmailAction(
  formData: FormData,
): Promise<SensitiveUserSearchState> {
  "use server";

  const email = parseFormString(formData, "email", 100);
  if (!email || !email.includes("@")) {
    return { kind: "error", message: "Введите корректный email." };
  }

  const cookieHeader = await buildAdminCookiesHeader();
  const result = await readAdminList(
    buildAdminUrl("/api/v1/admin/users", {
      email,
      limit: String(PAGE_STEP),
      offset: "0",
    }),
    cookieHeader,
    parseAdminUserRows,
  );

  if (result.kind === "ok") return result;
  if (result.kind === "empty") return result;
  return { kind: "error", message: `Поиск недоступен (HTTP ${result.status}).` };
}

async function searchSensitiveOperationalDataAction(
  formData: FormData,
): Promise<SensitiveOperationalSearchState> {
  "use server";

  const kind = parseFormString(formData, "sensitive_filter_kind", 20);
  const locationId = parseFormString(formData, "session_location_id", 80);
  const actorUserId = parseFormString(formData, "audit_actor_user_id", 80);
  const subjectId = parseFormString(formData, "audit_subject_id", 120);
  const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const cookieHeader = await buildAdminCookiesHeader();

  if (kind === "sessions") {
    if (!locationId || !uuidPattern.test(locationId)) {
      return { kind: "error", message: "Введите корректный Location UUID." };
    }
    const result = await readAdminList(
      buildAdminUrl("/api/v1/admin/sessions", {
        location_id: locationId,
        limit: String(PAGE_STEP),
        offset: "0",
      }),
      cookieHeader,
      parseSessionRows,
    );
    if (result.kind === "ok") return { kind: "sessions", items: result.items };
    if (result.kind === "empty") return { kind: "sessions", items: [] };
    return { kind: "error", message: `Поиск недоступен (HTTP ${result.status}).` };
  }

  if (kind === "audits") {
    if ((!actorUserId && !subjectId) || (actorUserId && !uuidPattern.test(actorUserId))) {
      return { kind: "error", message: "Введите корректный actor UUID или subject ID." };
    }
    const result = await readAdminList(
      buildAdminUrl("/api/v1/admin/audit-events", {
        actor_user_id: actorUserId,
        subject_id: subjectId,
        limit: String(AUDIT_PAGE_STEP),
        offset: "0",
      }),
      cookieHeader,
      parseAuditRows,
    );
    if (result.kind === "ok") return { kind: "audits", items: result.items };
    if (result.kind === "empty") return { kind: "audits", items: [] };
    return { kind: "error", message: `Поиск недоступен (HTTP ${result.status}).` };
  }

  return { kind: "error", message: "Неизвестный тип transient-поиска." };
}

async function createLocationAction(formData: FormData) {
  'use server';

  const id = parseFormString(formData, "location_id");
  if (id) {
    redirect(buildOperationNoticeRedirect("Локации", "error", `Удалите служебный location_id из формы создания.`, formData));
  }

  const name = parseFormString(formData, "location_name", 180);
  const slug = parseFormString(formData, "location_slug", 120);
  const exactLatitude = parseFormNumber(formData, "location_lat");
  const exactLongitude = parseFormNumber(formData, "location_lng");
  const publicLatitude = parseFormNumber(formData, "location_public_lat");
  const publicLongitude = parseFormNumber(formData, "location_public_lng");
  const coordinateVisibility = parseFormString(formData, "location_coordinate_visibility", 80);
  const sensitivityLevel = parseFormString(formData, "location_sensitivity_level", 80);
  const region = parseFormString(formData, "location_region", 180);
  const description = parseFormString(formData, "location_description", 2000);
  const timezone = parseFormString(formData, "location_timezone", 80);

  if (!name || !slug || exactLatitude === undefined || exactLongitude === undefined) {
    redirect(buildOperationNoticeRedirect("Локации", "error", "Заполните название, slug и координаты.", formData));
  }

  const countryCode = parseFormString(formData, "location_country_code", 8);

  const payload: Record<string, unknown> = {
    name,
    slug,
    exact_latitude: exactLatitude,
    exact_longitude: exactLongitude,
  };

  if (countryCode) payload.country_code = countryCode;
  if (region) payload.region = region;
  if (description) payload.description = description;
  if (timezone) payload.timezone = timezone;
  if (publicLatitude !== undefined) payload.public_latitude = publicLatitude;
  if (publicLongitude !== undefined) payload.public_longitude = publicLongitude;
  if (coordinateVisibility) payload.coordinate_visibility = coordinateVisibility;
  if (sensitivityLevel) payload.sensitivity_level = sensitivityLevel;

  const result = await executeAdminMutation("/api/v1/admin/locations", "POST", payload);
  const section = "Локации";
  if (result.ok) {
    redirect(buildOperationNoticeRedirect(section, "success", `Локация ${name} создана.`, formData, result.status));
  }
  redirect(buildOperationNoticeRedirect(section, "error", `${result.message} (HTTP ${result.status}).`, formData, result.status));
}

async function updateLocationAction(formData: FormData) {
  'use server';

  const locationId = parseFormString(formData, "location_id", 80);
  const revision = parseFormString(formData, "revision", 160);
  const name = parseFormString(formData, "location_name", 180);
  const slug = parseFormString(formData, "location_slug", 120);
  const exactLatitude = parseFormNumber(formData, "location_lat");
  const exactLongitude = parseFormNumber(formData, "location_lng");
  const publicLatitude = parseFormNumber(formData, "location_public_lat");
  const publicLongitude = parseFormNumber(formData, "location_public_lng");
  const coordinateVisibility = parseFormString(formData, "location_coordinate_visibility", 80);
  const sensitivityLevel = parseFormString(formData, "location_sensitivity_level", 80);
  const region = parseFormString(formData, "location_region", 180);
  const description = parseFormString(formData, "location_description", 2000);
  const timezone = parseFormString(formData, "location_timezone", 80);

  if (!locationId || !revision) {
    redirect(buildOperationNoticeRedirect("Локации", "error", "Укажите ID и revision локации для обновления.", formData));
  }

  const payload: Record<string, unknown> = {};
  if (name) payload.name = name;
  if (slug) payload.slug = slug;
  if (exactLatitude !== undefined) payload.exact_latitude = exactLatitude;
  if (exactLongitude !== undefined) payload.exact_longitude = exactLongitude;
  if (publicLatitude !== undefined) payload.public_latitude = publicLatitude;
  if (publicLongitude !== undefined) payload.public_longitude = publicLongitude;
  if (coordinateVisibility) payload.coordinate_visibility = coordinateVisibility;
  if (sensitivityLevel) payload.sensitivity_level = sensitivityLevel;
  if (region) payload.region = region;
  if (description) payload.description = description;
  if (timezone) payload.timezone = timezone;

  if (Object.keys(payload).length === 0) {
    redirect(buildOperationNoticeRedirect("Локации", "error", "Укажите хотя бы одно поле для обновления.", formData));
  }

  const result = await executeAdminMutation(
    `/api/v1/admin/locations/${encodeURIComponent(locationId)}`,
    "PATCH",
    payload,
    revision,
  );
  if (result.ok) {
    redirect(buildOperationNoticeRedirect("Локации", "success", `Локация ${locationId} обновлена.`, formData, result.status));
  }
  redirect(buildOperationNoticeRedirect("Локации", "error", `${result.message} (HTTP ${result.status}).`, formData, result.status));
}

async function createSessionAction(formData: FormData) {
  'use server';

  const title = parseFormString(formData, "session_title", 180);
  const slug = parseFormString(formData, "session_slug", 120);
  const locationId = parseFormString(formData, "session_location_id", 80);
  const recordedAt = parseFormString(formData, "session_recorded_at", 60);

  if (!title || !slug || !locationId) {
    redirect(buildOperationNoticeRedirect("Сессии", "error", "Заполните title, slug и location_id.", formData));
  }

  if (!recordedAt) {
    redirect(buildOperationNoticeRedirect("Сессии", "error", "Укажите recorded_at.", formData));
  }

  const recordedDate = new Date(recordedAt);
  if (Number.isNaN(recordedDate.getTime())) {
    redirect(buildOperationNoticeRedirect("Сессии", "error", "Некорректный формат recorded_at.", formData));
  }

  const payload: Record<string, unknown> = {
    title,
    slug,
    location_id: locationId,
    recorded_at: recordedDate.toISOString(),
  };

  const result = await executeAdminMutation("/api/v1/admin/sessions", "POST", payload);
  if (result.ok) {
    redirect(buildOperationNoticeRedirect("Сессии", "success", `Сессия ${slug} создана.`, formData, result.status));
  }
  redirect(buildOperationNoticeRedirect("Сессии", "error", `${result.message} (HTTP ${result.status}).`, formData, result.status));
}

async function updateSessionAction(formData: FormData) {
  'use server';

  const sessionId = parseFormString(formData, "session_id", 80);
  const revision = parseFormString(formData, "revision", 160);
  const title = parseFormString(formData, "session_title", 180);
  const slug = parseFormString(formData, "session_slug", 120);
  const locationId = parseFormString(formData, "session_location_id", 80);
  const publicationStatus = parseFormString(formData, "session_publication_status", 80);
  const accessLevel = parseFormString(formData, "session_access_level", 80);

  if (!sessionId || !revision) {
    redirect(buildOperationNoticeRedirect("Сессии", "error", "Укажите ID и revision сессии для обновления.", formData));
  }

  const payload: Record<string, unknown> = {};
  if (title) payload.title = title;
  if (slug) payload.slug = slug;
  if (locationId) payload.location_id = locationId;
  if (publicationStatus) payload.publication_status = publicationStatus;
  if (accessLevel) payload.access_level = accessLevel;

  if (Object.keys(payload).length === 0) {
    redirect(buildOperationNoticeRedirect("Сессии", "error", "Укажите хотя бы одно поле для обновления.", formData));
  }

  const result = await executeAdminMutation(
    `/api/v1/admin/sessions/${encodeURIComponent(sessionId)}`,
    "PATCH",
    payload,
    revision,
  );
  if (result.ok) {
    redirect(buildOperationNoticeRedirect("Сессии", "success", `Сессия ${sessionId} обновлена.`, formData, result.status));
  }
  redirect(buildOperationNoticeRedirect("Сессии", "error", `${result.message} (HTTP ${result.status}).`, formData, result.status));
}

async function deleteSessionAction(formData: FormData) {
  'use server';

  const sessionId = parseFormString(formData, "session_id", 80);
  const revision = parseFormString(formData, "revision", 160);
  const confirmation = parseFormString(formData, "archive_confirmation", 80);
  if (!sessionId || !revision || confirmation !== sessionId) {
    redirect(buildOperationNoticeRedirect("Сессии", "error", "Укажите ID, revision и повторите ID сессии для подтверждения архивации.", formData));
  }

  const result = await executeAdminMutation(
    `/api/v1/admin/sessions/${encodeURIComponent(sessionId)}`,
    "DELETE",
    undefined,
    revision,
  );
  if (result.ok) {
    redirect(buildOperationNoticeRedirect("Сессии", "success", `Сессия ${sessionId} архивирована.`, formData, result.status));
  }
  redirect(buildOperationNoticeRedirect("Сессии", "error", `${result.message} (HTTP ${result.status}).`, formData, result.status));
}

async function createSessionAssetAction(formData: FormData) {
  'use server';

  const sessionId = parseFormString(formData, "session_id", 80);
  const storageKey = parseFormString(formData, "asset_storage_key", 512);
  if (!sessionId || !storageKey) {
    redirect(buildOperationNoticeRedirect("Сессии", "error", "Укажите session ID и storage key ассета.", formData));
  }

  const payload: Record<string, unknown> = {
    storage_key: storageKey,
    kind: parseFormString(formData, "asset_kind", 80) || "source_audio",
    mime_type: parseFormString(formData, "asset_mime_type", 120) || "audio/wav",
    enqueue_processing: parseFormBoolean(formData, "asset_enqueue_processing") ?? true,
  };
  const result = await executeAdminMutation(
    `/api/v1/admin/sessions/${encodeURIComponent(sessionId)}/assets`,
    "POST",
    payload,
  );
  const message = result.ok ? `Ассет зарегистрирован для ${sessionId}.` : `${result.message} (HTTP ${result.status}).`;
  redirect(buildOperationNoticeRedirect("Сессии", result.ok ? "success" : "error", message, formData, result.status));
}

async function registerSessionSegmentsAction(formData: FormData) {
  'use server';

  const sessionId = parseFormString(formData, "session_id", 80);
  const raw = parseFormString(formData, "segments_json", 12000);
  if (!sessionId || !raw) {
    redirect(buildOperationNoticeRedirect("Сессии", "error", "Укажите session ID и JSON сегментов.", formData));
  }

  let segments: Array<Record<string, unknown>>;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed) || parsed.length === 0 || parsed.length > 500) throw new Error("invalid batch");
    segments = parsed.map((item, index) => {
      if (!isRecord(item) || typeof item.storage_key !== "string") throw new Error("invalid segment");
      const sequenceNumber = typeof item.sequence_number === "number" ? item.sequence_number : index + 1;
      if (!Number.isInteger(sequenceNumber) || sequenceNumber !== index + 1) throw new Error("invalid sequence");
      return {
        sequence_number: sequenceNumber,
        storage_key: item.storage_key.slice(0, 512),
        ...(typeof item.checksum === "string" ? { checksum: item.checksum.slice(0, 128) } : {}),
      };
    });
  } catch {
    redirect(buildOperationNoticeRedirect("Сессии", "error", "JSON сегментов должен быть непустым массивом с последовательностью 1..N.", formData));
  }

  const result = await executeAdminMutation(
    `/api/v1/admin/sessions/${encodeURIComponent(sessionId)}/segments`,
    "POST",
    { segments },
  );
  const message = result.ok ? `Сегменты зарегистрированы для ${sessionId}.` : `${result.message} (HTTP ${result.status}).`;
  redirect(buildOperationNoticeRedirect("Сессии", result.ok ? "success" : "error", message, formData, result.status));
}

async function retrySessionProcessingAction(formData: FormData) {
  'use server';

  const sessionId = parseFormString(formData, "session_id", 80);
  if (!sessionId) {
    redirect(buildOperationNoticeRedirect("Сессии", "error", "Укажите session ID для retry.", formData));
  }
  const result = await executeAdminMutation(
    `/api/v1/admin/sessions/${encodeURIComponent(sessionId)}/segments/process`,
    "POST",
    {},
  );
  const message = result.ok ? `Retry HLS поставлен в очередь для ${sessionId}.` : `${result.message} (HTTP ${result.status}).`;
  redirect(buildOperationNoticeRedirect("Сессии", result.ok ? "success" : "error", message, formData, result.status));
}

async function retryAssetProcessingAction(formData: FormData) {
  'use server';

  const assetId = parseFormString(formData, "asset_id", 80);
  if (!assetId) {
    redirect(buildOperationNoticeRedirect("Сессии", "error", "Укажите asset ID для retry.", formData));
  }
  const result = await executeAdminMutation(
    `/api/v1/admin/media-assets/${encodeURIComponent(assetId)}/process`,
    "POST",
    {},
  );
  const message = result.ok ? `Retry обработки поставлен в очередь для ${assetId}.` : `${result.message} (HTTP ${result.status}).`;
  redirect(buildOperationNoticeRedirect("Сессии", result.ok ? "success" : "error", message, formData, result.status));
}

async function createCollectionAction(formData: FormData) {
  'use server';

  const title = parseFormString(formData, "collection_title", 180);
  const slug = parseFormString(formData, "collection_slug", 120);

  if (!title || !slug) {
    redirect(buildOperationNoticeRedirect("Коллекции", "error", "Заполните title и slug коллекции.", formData));
  }

  const payload: Record<string, unknown> = {
    title,
    slug,
  };

  try {
    payload.location_ids = parseFormUuidArray(formData, "collection_location_ids", true);
    payload.session_ids = parseFormUuidArray(formData, "collection_session_ids", true);
  } catch {
    redirect(buildOperationNoticeRedirect("Коллекции", "error", "Списки location/session IDs должны быть JSON-массивами UUID.", formData));
  }

  const isPublic = parseFormBoolean(formData, "collection_is_public");
  if (typeof isPublic === "boolean") {
    payload.is_public = isPublic;
  }

  const result = await executeAdminMutation("/api/v1/admin/collections", "POST", payload);
  if (result.ok) {
    redirect(buildOperationNoticeRedirect("Коллекции", "success", `Коллекция ${slug} создана.`, formData, result.status));
  }
  redirect(buildOperationNoticeRedirect("Коллекции", "error", `${result.message} (HTTP ${result.status}).`, formData, result.status));
}

async function updateCollectionAction(formData: FormData) {
  'use server';

  const collectionId = parseFormString(formData, "collection_id", 80);
  const revision = parseFormString(formData, "revision", 160);
  const title = parseFormString(formData, "collection_title", 180);
  const slug = parseFormString(formData, "collection_slug", 120);

  if (!collectionId || !revision) {
    redirect(buildOperationNoticeRedirect("Коллекции", "error", "Укажите ID и revision коллекции для обновления.", formData));
  }

  const payload: Record<string, unknown> = {};
  if (title) payload.title = title;
  if (slug) payload.slug = slug;

  try {
    const locationIds = parseFormUuidArray(formData, "collection_location_ids", false);
    const sessionIds = parseFormUuidArray(formData, "collection_session_ids", false);
    if (locationIds !== undefined) payload.location_ids = locationIds;
    if (sessionIds !== undefined) payload.session_ids = sessionIds;
  } catch {
    redirect(buildOperationNoticeRedirect("Коллекции", "error", "Списки location/session IDs должны быть JSON-массивами UUID.", formData));
  }

  const isPublic = parseFormBoolean(formData, "collection_is_public");
  if (typeof isPublic === "boolean") {
    payload.is_public = isPublic;
  }

  if (Object.keys(payload).length === 0) {
    redirect(buildOperationNoticeRedirect("Коллекции", "error", "Укажите хотя бы одно поле для обновления.", formData));
  }

  const result = await executeAdminMutation(
    `/api/v1/admin/collections/${encodeURIComponent(collectionId)}`,
    "PATCH",
    payload,
    revision,
  );
  if (result.ok) {
    redirect(buildOperationNoticeRedirect("Коллекции", "success", `Коллекция ${collectionId} обновлена.`, formData, result.status));
  }
  redirect(buildOperationNoticeRedirect("Коллекции", "error", `${result.message} (HTTP ${result.status}).`, formData, result.status));
}


async function updateUserRoleAction(formData: FormData) {
  'use server';

  if (process.env.ADMIN_ACCOUNT_MANAGEMENT_ENABLED !== "true") {
    redirect(buildOperationNoticeRedirect("Пользователи", "error", "Account-management gate выключен.", formData));
  }
  const userId = parseFormString(formData, "user_id", 80);
  const revision = parseFormString(formData, "revision", 160);
  const role = parseFormString(formData, "user_role", 80);
  const confirmation = parseFormString(formData, "confirmation_user_id", 80);
  if (!userId || !revision || !role || confirmation !== userId) {
    redirect(buildOperationNoticeRedirect("Пользователи", "error", "Подтвердите изменение точным User ID.", formData));
  }
  const result = await executeAdminMutation(
    `/api/v1/admin/users/${encodeURIComponent(userId)}/role`,
    "PATCH",
    { role },
    revision,
  );
  const message = result.ok ? `Роль пользователя ${userId} обновлена.` : `${result.message} (HTTP ${result.status}).`;
  redirect(buildOperationNoticeRedirect("Пользователи", result.ok ? "success" : "error", message, formData, result.status));
}

async function updateMembershipAction(formData: FormData) {
  'use server';

  if (process.env.ADMIN_ACCOUNT_MANAGEMENT_ENABLED !== "true") {
    redirect(buildOperationNoticeRedirect("Пользователи", "error", "Account-management gate выключен.", formData));
  }
  const userId = parseFormString(formData, "user_id", 80);
  const revision = parseFormString(formData, "revision", 160);
  const status = parseFormString(formData, "membership_status", 80);
  const plan = parseFormString(formData, "membership_plan", 80) || "member";
  const expiresAt = parseFormString(formData, "membership_expires_at", 60);
  const confirmation = parseFormString(formData, "confirmation_user_id", 80);
  if (!userId || !revision || !status || confirmation !== userId) {
    redirect(buildOperationNoticeRedirect("Пользователи", "error", "Подтвердите изменение точным User ID.", formData));
  }
  const payload: Record<string, unknown> = { status, plan };
  if (expiresAt) {
    const value = new Date(expiresAt);
    if (Number.isNaN(value.getTime())) {
      redirect(buildOperationNoticeRedirect("Пользователи", "error", "Некорректный expires_at.", formData));
    }
    payload.expires_at = value.toISOString();
  }
  const result = await executeAdminMutation(
    `/api/v1/admin/memberships/${encodeURIComponent(userId)}`,
    "PUT",
    payload,
    revision,
  );
  const message = result.ok ? `Membership пользователя ${userId} обновлён.` : `${result.message} (HTTP ${result.status}).`;
  redirect(buildOperationNoticeRedirect("Пользователи", result.ok ? "success" : "error", message, formData, result.status));
}


function asString(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function asBoolean(value: unknown): boolean | undefined {
  return typeof value === "boolean" ? value : undefined;
}

function parseLimit(value: string, fallback: number, maximum: number): number {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(maximum, Math.max(fallback, parsed));
}

function getFilterFlags(searchParams: SearchParams | undefined) {
  const read = (key: keyof SearchParams, max = 200): string =>
    normalizeSearchValue(searchParams?.[key]).slice(0, max);
  const includeArchivedValue = read("include_archived", 10);

  return {
    includeArchived: includeArchivedValue === "1" || includeArchivedValue === "true",
    locationQ: read("location_q"),
    locationCoordinateVisibility: read("location_coordinate_visibility", 80),
    locationSensitivityLevel: read("location_sensitivity_level", 80),
    sessionQ: read("session_q"),

    sessionPublicationStatus: read("session_publication_status", 80),
    sessionProcessingStatus: read("session_processing_status", 80),
    sessionAccessLevel: read("session_access_level", 80),
    collectionQ: read("collection_q"),
    collectionIsPublic: read("collection_is_public", 10),
    userRole: read("user_role", 80),
    userIsActive: read("user_is_active", 10),
    userMembershipStatus: read("user_membership_status", 80),
    auditEventType: read("audit_event_type", 80),
    auditSubjectType: read("audit_subject_type", 80),
    auditCreatedFrom: read("audit_created_from", 40),
    auditCreatedTo: read("audit_created_to", 40),
    locationsLimit: parseLimit(read("locations_limit", 8), PAGE_STEP, MAX_PAGE_LIMIT),
    sessionsLimit: parseLimit(read("sessions_limit", 8), PAGE_STEP, MAX_PAGE_LIMIT),
    collectionsLimit: parseLimit(read("collections_limit", 8), PAGE_STEP, MAX_PAGE_LIMIT),
    usersLimit: parseLimit(read("users_limit", 8), PAGE_STEP, MAX_PAGE_LIMIT),
    auditsLimit: parseLimit(read("audits_limit", 8), AUDIT_PAGE_STEP, MAX_AUDIT_LIMIT),
    notice: read("notice", 180),
    noticeKind: read("notice_kind", 20) === "error" ? "error" : "success",
    noticeSection: read("notice_section", 60),
  };
}

function formatDate(value?: string): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("ru-RU", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function renderListState<T extends { id: string }>({
  state,
  emptyText,
  children,
}: {
  state: AdminListState<T>;
  emptyText: string;
  children: (item: T) => ReactNode;
}): JSX.Element {
  if (state.kind === "unsupported") {
    return <p className="admin-empty">{state.message}</p>;
  }

  if (state.kind === "error") {
    return <p className="admin-empty">Не удалось загрузить данные ({state.status}). {state.message}</p>;
  }

  if (state.kind === "empty") {
    return <p className="admin-empty">{emptyText}</p>;
  }

  return (
    <ul className="admin-list">
      {state.items.map((item) => (
        <li key={item.id}>{children(item)}</li>
      ))}
    </ul>
  );
}

function countItems<T>(state: AdminListState<T>): number {
  return state.kind === "ok" ? state.items.length : 0;
}

export default async function AdminPage({ searchParams }: { searchParams?: Promise<SearchParams> }) {
  const requestCookies = await cookies();
  const cookieHeader = requestCookies
    .getAll()
    .map((cookie) => `${cookie.name}=${cookie.value}`)
    .join(";");

  const filters = getFilterFlags(searchParams ? await searchParams : undefined);
  const adminState = await readAdminIdentity(cookieHeader);

  if (adminState.status !== "ok") {
    return (
      <div className="shell">
        <main className="admin-shell">
          <section className="admin-card">
            <h1 className="admin-title">Админ-панель</h1>
            <p>{adminState.message}</p>
            {adminState.status === "unauthenticated" ? (
              <p>
                <Link href="/membership?mode=login&returnTo=%2Fadmin">Войти и получить доступ</Link>
              </p>
            ) : null}
            {adminState.status === "unavailable" && adminState.details ? (
              <p className="admin-empty">{adminState.details}</p>
            ) : null}
          </section>
        </main>
      </div>
    );
  }

  if (adminState.identity.is_admin === false && adminState.identity.role !== "admin") {
    return (
      <div className="shell">
        <main className="admin-shell">
          <section className="admin-card">
            <h1 className="admin-title">Доступ запрещён</h1>
            <p>Текущий аккаунт не является администратором.</p>
          </section>
        </main>
      </div>
    );
  }

  const [locations, sessions, collections, users, audits] = await Promise.all([
    readAdminList(
      buildAdminUrl("/api/v1/admin/locations", {
        include_archived: filters.includeArchived ? "true" : undefined,
        q: filters.locationQ || undefined,
        coordinate_visibility: filters.locationCoordinateVisibility || undefined,
        sensitivity_level: filters.locationSensitivityLevel || undefined,
        limit: String(filters.locationsLimit),
        offset: "0",
      }),
      cookieHeader,
      parseLocationRows,
    ),
    readAdminList(
      buildAdminUrl("/api/v1/admin/sessions", {
        include_archived: filters.includeArchived ? "true" : undefined,
        q: filters.sessionQ || undefined,

        publication_status: filters.sessionPublicationStatus || undefined,
        processing_status: filters.sessionProcessingStatus || undefined,
        access_level: filters.sessionAccessLevel || undefined,
        limit: String(filters.sessionsLimit),
        offset: "0",
      }),
      cookieHeader,
      parseSessionRows,
    ),
    readAdminList(
      buildAdminUrl("/api/v1/admin/collections", {
        q: filters.collectionQ || undefined,
        is_public: filters.collectionIsPublic || undefined,
        limit: String(filters.collectionsLimit),
        offset: "0",
      }),
      cookieHeader,
      parseCollectionRows,
    ),
    readAdminList(
      buildAdminUrl("/api/v1/admin/users", {
        role: filters.userRole || undefined,
        is_active: filters.userIsActive || undefined,
        membership_status: filters.userMembershipStatus || undefined,
        limit: String(filters.usersLimit),
        offset: "0",
      }),
      cookieHeader,
      parseAdminUserRows,
    ),
    readAdminList(
      buildAdminUrl("/api/v1/admin/audit-events", {
        event_type: filters.auditEventType || undefined,
        subject_type: filters.auditSubjectType || undefined,
        created_from: filters.auditCreatedFrom || undefined,
        created_to: filters.auditCreatedTo || undefined,
        limit: String(filters.auditsLimit),
        offset: "0",
      }),
      cookieHeader,
      parseAuditRows,
    ),
  ]);

  const adminMode = adminState.identity.mode === "local" ? "локальный" : "cookie-сессия";
  const accountManagementEnabled = process.env.ADMIN_ACCOUNT_MANAGEMENT_ENABLED === "true";
  const operationNotice = filters.notice;
  const operationNoticeKind = filters.noticeKind;
  const operationNoticeSection = filters.noticeSection;
  const filterQuery: Record<string, string | undefined> = {
    include_archived: filters.includeArchived ? "true" : undefined,
    location_q: filters.locationQ || undefined,
    location_coordinate_visibility: filters.locationCoordinateVisibility || undefined,
    location_sensitivity_level: filters.locationSensitivityLevel || undefined,
    session_q: filters.sessionQ || undefined,

    session_publication_status: filters.sessionPublicationStatus || undefined,
    session_processing_status: filters.sessionProcessingStatus || undefined,
    session_access_level: filters.sessionAccessLevel || undefined,
    collection_q: filters.collectionQ || undefined,
    collection_is_public: filters.collectionIsPublic || undefined,
    user_role: filters.userRole || undefined,
    user_is_active: filters.userIsActive || undefined,
    user_membership_status: filters.userMembershipStatus || undefined,
    audit_event_type: filters.auditEventType || undefined,
    audit_subject_type: filters.auditSubjectType || undefined,
    audit_created_from: filters.auditCreatedFrom || undefined,
    audit_created_to: filters.auditCreatedTo || undefined,
    locations_limit: String(filters.locationsLimit),
    sessions_limit: String(filters.sessionsLimit),
    collections_limit: String(filters.collectionsLimit),
    users_limit: String(filters.usersLimit),
    audits_limit: String(filters.auditsLimit),
  };

  return (
    <AdminSessionGuard>
      <div className="shell">
      <main className="admin-shell">
        <header className="admin-header">
          <p className="admin-eyebrow">Админ workspace</p>
          <h1>Управление контентом и операциями</h1>
          <p>
            Сессия: {adminState.identity.role || "admin"} · режим {adminMode} · id {adminState.identity.id || "—"}
          </p>
          {operationNotice ? (
            <p className={`admin-notice ${operationNoticeKind === "error" ? "admin-notice-error" : "admin-notice-success"}`}>
              {operationNoticeSection ? `[${operationNoticeSection}] ` : ""}
              {operationNotice}
            </p>
          ) : null}
        </header>

        <section className="admin-kpis">
          <article className="admin-kpi">
            <span className="admin-label">Локации</span>
            <strong>{countItems(locations)}</strong>
            <span>{filters.includeArchived ? "включая архив" : "активные"}</span>
          </article>
          <article className="admin-kpi">
            <span className="admin-label">Сессии</span>
            <strong>{countItems(sessions)}</strong>
            <span>{filters.includeArchived ? "включая архив" : "активные"}</span>
          </article>
          <article className="admin-kpi">
            <span className="admin-label">Коллекции</span>
            <strong>{countItems(collections)}</strong>
            <span>последние записи</span>
          </article>
          <article className="admin-kpi">
            <span className="admin-label">Пользователи</span>
            <strong>{countItems(users)}</strong>
            <span>по выбранным фильтрам</span>
          </article>
          <article className="admin-kpi">
            <span className="admin-label">Audit</span>
            <strong>{countItems(audits)}</strong>
            <span>последние события</span>
          </article>
        </section>

        <form className="admin-filters" action="/admin" method="get">
          <label>
            <span>Включать архивные записи</span>
            <input
              type="checkbox"
              name="include_archived"
              value="true"
              defaultChecked={filters.includeArchived}
            />
          </label>
          <label>
            <span>Локации: поиск</span>
            <input name="location_q" defaultValue={filters.locationQ} maxLength={200} placeholder="name / slug / region" />
          </label>
          <label>
            <span>Локации: видимость координат</span>
            <select name="location_coordinate_visibility" defaultValue={filters.locationCoordinateVisibility}>
              <option value="">Все</option>
              <option value="exact_public">exact_public</option>
              <option value="approximate_public">approximate_public</option>
              <option value="hidden_public">hidden_public</option>
            </select>
          </label>
          <label>
            <span>Локации: sensitivity</span>
            <input name="location_sensitivity_level" defaultValue={filters.locationSensitivityLevel} maxLength={80} />
          </label>
          <label>
            <span>Сессии: поиск</span>
            <input name="session_q" defaultValue={filters.sessionQ} maxLength={200} placeholder="title / slug" />
          </label>

          <label>
            <span>Сессии: publication</span>
            <select name="session_publication_status" defaultValue={filters.sessionPublicationStatus}>
              <option value="">Все</option>
              <option value="draft">draft</option>
              <option value="published">published</option>
            </select>
          </label>
          <label>
            <span>Сессии: processing</span>
            <input name="session_processing_status" defaultValue={filters.sessionProcessingStatus} maxLength={80} />
          </label>
          <label>
            <span>Сессии: access</span>
            <select name="session_access_level" defaultValue={filters.sessionAccessLevel}>
              <option value="">Все</option>
              <option value="public">public</option>
              <option value="members_only">members_only</option>
              <option value="private">private</option>
            </select>
          </label>
          <label>
            <span>Коллекции: поиск</span>
            <input name="collection_q" defaultValue={filters.collectionQ} maxLength={200} />
          </label>
          <label>
            <span>Коллекции: публичность</span>
            <select name="collection_is_public" defaultValue={filters.collectionIsPublic}>
              <option value="">Все</option>
              <option value="true">Публичные</option>
              <option value="false">Непубличные</option>
            </select>
          </label>
          <label>
            <span>Роль пользователя</span>
            <input name="user_role" defaultValue={filters.userRole} maxLength={80} placeholder="admin / editor / member" />
          </label>
          <label>
            <span>Активность пользователя</span>
            <select name="user_is_active" defaultValue={filters.userIsActive}>
              <option value="">Все</option>
              <option value="true">Активные</option>
              <option value="false">Неактивные</option>
            </select>
          </label>
          <label>
            <span>Membership status</span>
            <input name="user_membership_status" defaultValue={filters.userMembershipStatus} maxLength={80} />
          </label>
          <label>
            <span>Тип audit-события</span>
            <input name="audit_event_type" defaultValue={filters.auditEventType} maxLength={80} placeholder="location.created" />
          </label>

          <label>
            <span>Audit subject type</span>
            <input name="audit_subject_type" defaultValue={filters.auditSubjectType} maxLength={80} />
          </label>

          <label>
            <span>Audit from</span>
            <input name="audit_created_from" defaultValue={filters.auditCreatedFrom} placeholder="2026-07-30T00:00:00Z" />
          </label>
          <label>
            <span>Audit to</span>
            <input name="audit_created_to" defaultValue={filters.auditCreatedTo} placeholder="2026-07-31T00:00:00Z" />
          </label>
          <div className="admin-form-actions">
            <button type="submit">Применить фильтры</button>
            <a href="/admin">Сброс</a>
          </div>
        </form>

        <SensitiveOperationalSearch action={searchSensitiveOperationalDataAction} />

        <section className="admin-card">
          <h2>Операции администратора</h2>

          <div className="admin-action-grid">
            <article className="admin-action-card">
              <h3>Локации</h3>

              <form action={createLocationAction} className="admin-action-form">
                <h4>Создать</h4>
                <label>
                  <span>Название</span>
                  <input name="location_name" type="text" maxLength={180} required />
                </label>
                <label>
                  <span>Slug</span>
                  <input name="location_slug" type="text" maxLength={120} required />
                </label>
                <p className="admin-coordinate-group admin-coordinate-exact">Exact coordinates · только admin</p>
                <label>
                  <span>Exact latitude</span>
                  <input name="location_lat" type="number" step="0.000001" required />
                </label>
                <label>
                  <span>Exact longitude</span>
                  <input name="location_lng" type="number" step="0.000001" required />
                </label>
                <p className="admin-coordinate-group admin-coordinate-public">Public coordinate preview</p>
                <label><span>Public latitude</span><input name="location_public_lat" type="number" step="0.000001" /></label>
                <label><span>Public longitude</span><input name="location_public_lng" type="number" step="0.000001" /></label>
                <label>
                  <span>Coordinate visibility</span>
                  <select name="location_coordinate_visibility" defaultValue="approximate_public">
                    <option value="exact_public">exact_public</option>
                    <option value="approximate_public">approximate_public</option>
                    <option value="hidden_public">hidden_public</option>
                  </select>
                </label>
                <label>
                  <span>Sensitivity level</span>
                  <select name="location_sensitivity_level" defaultValue="none">
                    <option value="none">none</option><option value="low">low</option><option value="medium">medium</option><option value="high">high</option><option value="protected">protected</option>
                  </select>
                </label>
                <label><span>Регион</span><input name="location_region" maxLength={180} /></label>
                <label><span>Timezone (IANA)</span><input name="location_timezone" maxLength={80} placeholder="Europe/Paris" /></label>
                <label><span>Описание</span><textarea name="location_description" rows={3} maxLength={2000} /></label>
                <label>
                  <span>Код страны (опционально)</span>
                  <input name="location_country_code" type="text" maxLength={8} />
                </label>
                <button type="submit">Создать локацию</button>
              </form>

              <form action={updateLocationAction} className="admin-action-form">
                <h4>Редактировать</h4>
                <label>
                  <span>ID</span>
                  <input name="location_id" type="text" maxLength={80} required />
                </label>
                <label>
                  <span>Revision / If-Match</span>
                  <input name="revision" type="text" maxLength={160} required />
                </label>
                <label>
                  <span>Название</span>
                  <input name="location_name" type="text" maxLength={180} />
                </label>
                <label>
                  <span>Slug</span>
                  <input name="location_slug" type="text" maxLength={120} />
                </label>
                <p className="admin-coordinate-group admin-coordinate-exact">Exact coordinates · только admin</p>
                <label>
                  <span>Exact latitude</span>
                  <input name="location_lat" type="number" step="0.000001" />
                </label>
                <label>
                  <span>Exact longitude</span>
                  <input name="location_lng" type="number" step="0.000001" />
                </label>
                <p className="admin-coordinate-group admin-coordinate-public">Public coordinate preview</p>
                <label><span>Public latitude</span><input name="location_public_lat" type="number" step="0.000001" /></label>
                <label><span>Public longitude</span><input name="location_public_lng" type="number" step="0.000001" /></label>
                <label>
                  <span>Coordinate visibility</span>
                  <select name="location_coordinate_visibility" defaultValue="">
                    <option value="">Без изменения</option>
                    <option value="exact_public">exact_public</option>
                    <option value="approximate_public">approximate_public</option>
                    <option value="hidden_public">hidden_public</option>
                  </select>
                </label>
                <label>
                  <span>Sensitivity level</span>
                  <select name="location_sensitivity_level" defaultValue="">
                    <option value="">Без изменения</option>
                    <option value="none">none</option><option value="low">low</option><option value="medium">medium</option><option value="high">high</option><option value="protected">protected</option>
                  </select>
                </label>
                <label><span>Регион</span><input name="location_region" maxLength={180} /></label>
                <label><span>Timezone (IANA)</span><input name="location_timezone" maxLength={80} placeholder="Europe/Paris" /></label>
                <label><span>Описание</span><textarea name="location_description" rows={3} maxLength={2000} /></label>
                <button type="submit">Сохранить</button>
              </form>


            </article>

            <article className="admin-action-card">
              <h3>Сессии</h3>

              <form action={createSessionAction} className="admin-action-form">
                <h4>Создать</h4>
                <label>
                  <span>Название</span>
                  <input name="session_title" type="text" maxLength={180} required />
                </label>
                <label>
                  <span>Slug</span>
                  <input name="session_slug" type="text" maxLength={120} required />
                </label>
                <label>
                  <span>Location ID</span>
                  <input name="session_location_id" type="text" maxLength={80} required />
                </label>
                <label>
                  <span>Recorded at</span>
                  <input name="session_recorded_at" type="text" placeholder="2026-07-30T10:00:00Z" required />
                </label>
                <button type="submit">Создать сессию</button>
              </form>

              <form action={updateSessionAction} className="admin-action-form">
                <h4>Редактировать</h4>
                <label>
                  <span>Session ID</span>
                  <input name="session_id" type="text" maxLength={80} required />
                </label>
                <label>
                  <span>Revision / If-Match</span>
                  <input name="revision" type="text" maxLength={160} required />
                </label>
                <label>
                  <span>Название</span>
                  <input name="session_title" type="text" maxLength={180} />
                </label>
                <label>
                  <span>Slug</span>
                  <input name="session_slug" type="text" maxLength={120} />
                </label>
                <label>
                  <span>Location ID</span>
                  <input name="session_location_id" type="text" maxLength={80} />
                </label>
                <label>
                  <span>Publication status</span>
                  <select name="session_publication_status" defaultValue="">
                    <option value="">Без изменения</option><option value="draft">draft</option><option value="published">published</option>
                  </select>
                </label>
                <label>
                  <span>Access level</span>
                  <select name="session_access_level" defaultValue="">
                    <option value="">Без изменения</option><option value="public">public</option><option value="members_only">members_only</option><option value="private">private</option>
                  </select>
                </label>
                <button type="submit">Сохранить</button>
              </form>

              <form action={deleteSessionAction} className="admin-action-form">
                <h4>Архивировать</h4>
                <label>
                  <span>Session ID</span>
                  <input name="session_id" type="text" maxLength={80} required />
                </label>
                <label>
                  <span>Revision / If-Match</span>
                  <input name="revision" type="text" maxLength={160} required />
                </label>
                <label>
                  <span>Подтверждение: повторите Session ID</span>
                  <input name="archive_confirmation" type="text" maxLength={80} required />
                </label>
                <p className="admin-muted">
                  После архивации связанные assets переходят в существующий retention/cleanup lifecycle. Автоматического undo нет.
                </p>
                <button type="submit">Архивировать сессию</button>
              </form>

              <form action={createSessionAssetAction} className="admin-action-form">
                <h4>Зарегистрировать managed asset</h4>
                <label><span>Session ID</span><input name="session_id" required maxLength={80} /></label>
                <label><span>Storage key</span><input name="asset_storage_key" required maxLength={512} /></label>
                <label><span>Kind</span><input name="asset_kind" defaultValue="source_audio" maxLength={80} /></label>
                <label><span>MIME</span><input name="asset_mime_type" defaultValue="audio/wav" maxLength={120} /></label>
                <label>
                  <span>Поставить обработку в очередь</span>
                  <select name="asset_enqueue_processing" defaultValue="true">
                    <option value="true">Да</option><option value="false">Нет</option>
                  </select>
                </label>
                <button type="submit">Зарегистрировать asset</button>
              </form>

              <form action={registerSessionSegmentsAction} className="admin-action-form">
                <h4>Зарегистрировать сегменты</h4>
                <label><span>Session ID</span><input name="session_id" required maxLength={80} /></label>
                <label>
                  <span>JSON-массив сегментов (1..N)</span>
                  <textarea
                    name="segments_json"
                    rows={5}
                    maxLength={12000}
                    required
                    placeholder={'[{"sequence_number":1,"storage_key":"sessions/.../segment-1.wav"}]'}
                  />
                </label>
                <button type="submit">Зарегистрировать сегменты</button>
              </form>

              <form action={retrySessionProcessingAction} className="admin-action-form">
                <h4>Retry HLS сессии</h4>
                <label><span>Session ID</span><input name="session_id" required maxLength={80} /></label>
                <button type="submit">Поставить retry в очередь</button>
              </form>

              <form action={retryAssetProcessingAction} className="admin-action-form">
                <h4>Retry asset</h4>
                <label><span>Asset ID</span><input name="asset_id" required maxLength={80} /></label>
                <button type="submit">Повторить обработку asset</button>
              </form>
            </article>

            <article className="admin-action-card">
              <h3>Коллекции</h3>

              <form action={createCollectionAction} className="admin-action-form">
                <h4>Создать</h4>
                <label>
                  <span>Название</span>
                  <input name="collection_title" type="text" maxLength={180} required />
                </label>
                <label>
                  <span>Slug</span>
                  <input name="collection_slug" type="text" maxLength={120} required />
                </label>
                <label>
                  <span>Публичная</span>
                  <select name="collection_is_public" defaultValue="">
                    <option value="">—</option>
                    <option value="true">Да</option>
                    <option value="false">Нет</option>
                  </select>
                </label>
                <label>
                  <span>Location IDs · JSON-массив в требуемом порядке</span>
                  <textarea name="collection_location_ids" rows={3} defaultValue="[]" required maxLength={12000} />
                </label>
                <label>
                  <span>Session IDs · JSON-массив в требуемом порядке</span>
                  <textarea name="collection_session_ids" rows={3} defaultValue="[]" required maxLength={12000} />
                </label>
                <button type="submit">Создать коллекцию</button>
              </form>

              <form action={updateCollectionAction} className="admin-action-form">
                <h4>Редактировать</h4>
                <label>
                  <span>ID</span>
                  <input name="collection_id" type="text" maxLength={80} required />
                </label>
                <label>
                  <span>Revision / If-Match</span>
                  <input name="revision" type="text" maxLength={160} required />
                </label>
                <label>
                  <span>Название</span>
                  <input name="collection_title" type="text" maxLength={180} />
                </label>
                <label>
                  <span>Slug</span>
                  <input name="collection_slug" type="text" maxLength={120} />
                </label>
                <label>
                  <span>Публичная</span>
                  <select name="collection_is_public" defaultValue="">
                    <option value="">—</option>
                    <option value="true">Да</option>
                    <option value="false">Нет</option>
                  </select>
                </label>
                <label>
                  <span>Location IDs · JSON-массив; [] очищает список</span>
                  <textarea name="collection_location_ids" rows={3} maxLength={12000} />
                </label>
                <label>
                  <span>Session IDs · JSON-массив; [] очищает список</span>
                  <textarea name="collection_session_ids" rows={3} maxLength={12000} />
                </label>
                <button type="submit">Сохранить</button>
              </form>


            </article>

            <article className="admin-action-card">
              <h3>Пользователи и membership</h3>
              <p className="admin-muted">
                Gate: {accountManagementEnabled ? "включён" : "выключен (ADMIN_ACCOUNT_MANAGEMENT_ENABLED)"}.
              </p>
              {accountManagementEnabled ? (
                <>
                  <form action={updateUserRoleAction} className="admin-action-form">
                    <h4>Изменить роль</h4>
                    <label><span>User ID</span><input name="user_id" required maxLength={80} /></label>
                    <label><span>Aggregate user/membership revision</span><input name="revision" required maxLength={160} /></label>
                    <label>
                      <span>Роль</span>
                      <select name="user_role" required defaultValue="member">
                        <option value="member">member</option><option value="editor">editor</option><option value="admin">admin</option>
                      </select>
                    </label>
                    <label><span>Подтверждение · повторите User ID</span><input name="confirmation_user_id" required maxLength={80} autoComplete="off" /></label>
                    <button type="submit">Обновить роль</button>
                  </form>

                  <form action={updateMembershipAction} className="admin-action-form">
                    <h4>Изменить membership</h4>
                    <label><span>User ID</span><input name="user_id" required maxLength={80} /></label>
                    <label><span>Aggregate user/membership revision</span><input name="revision" required maxLength={160} /></label>
                    <label>
                      <span>Status</span>
                      <select name="membership_status" required defaultValue="active">
                        <option value="inactive">inactive</option><option value="active">active</option><option value="cancelled">cancelled</option><option value="expired">expired</option>
                      </select>
                    </label>
                    <label><span>Plan</span><input name="membership_plan" defaultValue="member" maxLength={80} /></label>
                    <label><span>Expires at</span><input name="membership_expires_at" type="text" placeholder="2026-12-31T23:59:59Z" /></label>
                    <label><span>Подтверждение · повторите User ID</span><input name="confirmation_user_id" required maxLength={80} autoComplete="off" /></label>
                    <button type="submit">Обновить membership</button>
                  </form>
                </>
              ) : (
                <p className="admin-empty">Мутации account-domain скрыты до явного включения production gate.</p>
              )}
            </article>
          </div>
        </section>

        <div className="admin-section-grid">
          <section id="locations" className="admin-card admin-section" aria-labelledby="locations-title">
            <h2 id="locations-title">Локации</h2>
            {renderListState<AdminLocationRow>({
              state: locations,
              emptyText: "Нет локаций для показа.",
              children: (location) => (
                <>
                  <h3>{location.name}</h3>
                  <p>
                    {location.slug ? <strong>{location.slug}</strong> : <span className="admin-muted">без slug</span>}
                    {location.country_code ? ` · ${location.country_code}` : ""}
                    {location.region ? ` · ${location.region}` : ""}
                  </p>
                  <p className="admin-muted">
                    Видимость: {location.coordinate_visibility || "—"} · sensitivity: {location.sensitivity_level || "—"} · Архив: {location.archived_at ? "есть" : "нет"}
                  </p>
                  <p className="admin-coordinate-group admin-coordinate-exact">
                    Exact admin: {location.exact_latitude || "—"}, {location.exact_longitude || "—"}
                  </p>
                  <p className="admin-coordinate-group admin-coordinate-public">
                    {location.coordinate_visibility === "hidden_public"
                      ? "Public preview: скрыт политикой hidden_public"
                      : `Public preview: ${location.public_latitude || "—"}, ${location.public_longitude || "—"}`}
                  </p>
                  <p className="admin-muted admin-resource-id">
                    ID: <code>{location.id}</code> · revision: <code>{location.revision || "—"}</code>
                  </p>
                </>
              ),
            })}
            {locations.kind === "ok" && locations.items.length === filters.locationsLimit && filters.locationsLimit < MAX_PAGE_LIMIT ? (
              <Link className="admin-load-more" href={buildAdminUrl("/admin", { ...filterQuery, locations_limit: String(Math.min(MAX_PAGE_LIMIT, filters.locationsLimit + PAGE_STEP)) })}>
                Загрузить ещё локации
              </Link>
            ) : null}
          </section>

          <section id="sessions" className="admin-card admin-section" aria-labelledby="sessions-title">
            <h2 id="sessions-title">Сессии</h2>
            {renderListState<AdminSessionRow>({
              state: sessions,
              emptyText: "Нет сессий для показа.",
              children: (session) => (
                <>
                  <h3>{session.title}</h3>
                  <p>
                    {session.slug ? <strong>{session.slug}</strong> : <span className="admin-muted">без slug</span>}
                    {session.publication_status ? ` · publication: ${session.publication_status}` : ""}
                    {session.processing_status ? ` · processing: ${session.processing_status}` : ""}
                  </p>
                  <p className="admin-muted">
                    Доступ: {session.access_level || "—"} · {formatDate(session.recorded_at || session.created_at)}
                  </p>
                  <p className="admin-muted admin-resource-id">
                    ID: <code>{session.id}</code> · revision: <code>{session.revision || "—"}</code>
                  </p>
                </>
              ),
            })}
            {sessions.kind === "ok" && sessions.items.length === filters.sessionsLimit && filters.sessionsLimit < MAX_PAGE_LIMIT ? (
              <Link className="admin-load-more" href={buildAdminUrl("/admin", { ...filterQuery, sessions_limit: String(Math.min(MAX_PAGE_LIMIT, filters.sessionsLimit + PAGE_STEP)) })}>
                Загрузить ещё сессии
              </Link>
            ) : null}
          </section>

          <section id="collections" className="admin-card admin-section" aria-labelledby="collections-title">
            <h2 id="collections-title">Коллекции</h2>
            {renderListState<AdminCollectionRow>({
              state: collections,
              emptyText: "Нет коллекций для показа.",
              children: (collection) => (
                <>
                  <h3>{collection.title}</h3>
                  <p>
                    {collection.slug ? <strong>{collection.slug}</strong> : <span className="admin-muted">без slug</span>}
                    {typeof collection.is_public === "boolean" ? ` · публичная: ${collection.is_public ? "да" : "нет"}` : ""}
                  </p>
                  <p className="admin-muted">Создана: {formatDate(collection.created_at)}</p>
                  <p className="admin-muted admin-resource-id">
                    ID: <code>{collection.id}</code> · revision: <code>{collection.revision || "—"}</code>
                  </p>
                </>
              ),
            })}
            {collections.kind === "ok" && collections.items.length === filters.collectionsLimit && filters.collectionsLimit < MAX_PAGE_LIMIT ? (
              <Link className="admin-load-more" href={buildAdminUrl("/admin", { ...filterQuery, collections_limit: String(Math.min(MAX_PAGE_LIMIT, filters.collectionsLimit + PAGE_STEP)) })}>
                Загрузить ещё коллекции
              </Link>
            ) : null}
          </section>

          <section id="users" className="admin-card admin-section" aria-labelledby="users-title">
            <h2 id="users-title">Пользователи</h2>
            <SensitiveUserSearch action={searchAdminUsersByEmailAction} />
            {renderListState<AdminUserRow>({
              state: users,
              emptyText: "Пользователи по фильтру не найдены.",
              children: (user) => (
                <>
                  <h3>{user.email || user.id}</h3>
                  <p>
                    {user.role ? `роль: ${user.role}` : "роль: —"}
                    {typeof user.is_active === "boolean" ? ` · активен: ${user.is_active ? "да" : "нет"}` : ""}
                    {user.membership_status ? ` · membership: ${user.membership_status}` : ""}
                  </p>
                  <p className="admin-muted">Создан: {formatDate(user.created_at)}</p>
                  <p className="admin-muted admin-resource-id">
                    ID: <code>{user.id}</code> · aggregate user/membership revision: <code>{user.revision || "—"}</code>
                  </p>
                </>
              ),
            })}
            {users.kind === "ok" && users.items.length === filters.usersLimit && filters.usersLimit < MAX_PAGE_LIMIT ? (
              <Link className="admin-load-more" href={buildAdminUrl("/admin", { ...filterQuery, users_limit: String(Math.min(MAX_PAGE_LIMIT, filters.usersLimit + PAGE_STEP)) })}>
                Загрузить ещё пользователей
              </Link>
            ) : null}
          </section>

          <section id="audit" className="admin-card admin-section" aria-labelledby="audit-title">
            <h2 id="audit-title">Последние события</h2>
            {renderListState<AdminAuditRow>({
              state: audits,
              emptyText: "События отсутствуют.",
              children: (audit) => (
                <>
                  <h3>{audit.event_type || "unknown"}</h3>
                  <p>
                    {audit.subject_type ? `subject: ${audit.subject_type}` : "subject: —"}
                    {audit.subject_id ? ` (${audit.subject_id})` : ""}
                  </p>
                  <p className="admin-muted">
                    actor: {audit.actor_user_id || "—"} · {formatDate(audit.created_at)}
                  </p>
                  <p className="admin-muted">IP: {audit.ip_address || "—"} · UA: {audit.user_agent || "—"}</p>
                  <details className="admin-audit-metadata">
                    <summary>Metadata JSON</summary>
                    <pre>{JSON.stringify(audit.metadata ?? {}, null, 2)}</pre>
                  </details>
                </>
              ),
            })}
            {audits.kind === "ok" && audits.items.length === filters.auditsLimit && filters.auditsLimit < MAX_AUDIT_LIMIT ? (
              <Link className="admin-load-more" href={buildAdminUrl("/admin", { ...filterQuery, audits_limit: String(Math.min(MAX_AUDIT_LIMIT, filters.auditsLimit + AUDIT_PAGE_STEP)) })}>
                Загрузить ещё audit-события
              </Link>
            ) : null}
          </section>
        </div>
      </main>
      </div>
    </AdminSessionGuard>
  );
}
