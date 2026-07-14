export type ApiErrorKind =
  | "authentication"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "unavailable"
  | "network"
  | "invalid_response"
  | "request_failed";

type ErrorPayload = {
  detail?: unknown;
};

type NextFetchInit = RequestInit & {
  next?: {
    revalidate?: number | false;
  };
};

function detailMessage(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }

  const detail = (payload as ErrorPayload).detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (!item || typeof item !== "object") return null;
        const message = (item as { msg?: unknown }).msg;
        return typeof message === "string" ? message : null;
      })
      .filter((message): message is string => Boolean(message));
    return messages.length > 0 ? messages.join("; ") : null;
  }
  return null;
}

function kindForStatus(status: number): ApiErrorKind {
  if (status === 401) return "authentication";
  if (status === 403) return "forbidden";
  if (status === 404) return "not_found";
  if (status === 409 || status === 425) return "conflict";
  if (status >= 500) return "unavailable";
  return "request_failed";
}

function defaultMessage(status: number): string {
  if (status === 401) return "Authentication is required";
  if (status === 403) return "You do not have access to this resource";
  if (status === 404) return "The requested resource was not found";
  if (status === 409 || status === 425) return "This resource is not ready yet";
  if (status >= 500) return "The service is temporarily unavailable";
  return `Request failed (${status})`;
}

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly detail: unknown;

  constructor(
    message: string,
    options: { kind: ApiErrorKind; status?: number | null; detail?: unknown; cause?: unknown },
  ) {
    super(message, { cause: options.cause });
    this.name = "ApiError";
    this.kind = options.kind;
    this.status = options.status ?? null;
    this.detail = options.detail;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

export function apiErrorMessage(error: unknown, fallback = "Something went wrong"): string {
  if (error instanceof ApiError) {
    if (error.kind === "network") return "Unable to reach ORNA Atlas. Check your connection and try again.";
    if (error.kind === "unavailable") return "ORNA Atlas is temporarily unavailable. Please try again soon.";
    return error.message;
  }
  return error instanceof Error && error.message ? error.message : fallback;
}

export async function fetchJson<T>(url: string, init: NextFetchInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new ApiError("Network request failed", { kind: "network", cause: error });
  }

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new ApiError(detailMessage(payload) ?? defaultMessage(response.status), {
      kind: kindForStatus(response.status),
      status: response.status,
      detail: payload,
    });
  }

  try {
    return (await response.json()) as T;
  } catch (error) {
    throw new ApiError("The server returned an invalid response", {
      kind: "invalid_response",
      status: response.status,
      cause: error,
    });
  }
}
