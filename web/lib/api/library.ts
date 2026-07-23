import type { components } from "./generated";
import { fetchJson, isApiError } from "./client";
import {
  getAccountAuthEpoch,
  markAccountAnonymous,
  markAccountAuthenticated,
} from "./account-auth-state";
import { refreshAuthentication } from "./auth-refresh";
import { apiUrl } from "./sessions";

export type Favorite = components["schemas"]["FavoriteRead"];
export type ListeningHistoryItem = components["schemas"]["ListeningHistoryRead"];
export type ListeningProgressUpdate = components["schemas"]["ListeningProgressUpdate"];

class AccountAuthEpochChangedError extends Error {
  constructor() {
    super("Account authentication changed while the request was in flight");
    this.name = "AccountAuthEpochChangedError";
  }
}

function assertAccountAuthEpoch(expectedEpoch: number): void {
  if (getAccountAuthEpoch() !== expectedEpoch) throw new AccountAuthEpochChangedError();
}

function refreshAccessCookie(signal?: AbortSignal): Promise<void> {
  return refreshAuthentication((refreshSignal) => fetchJson<unknown>(apiUrl("/api/v1/auth/refresh"), {
      method: "POST",
      credentials: "include",
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal: refreshSignal,
    }), signal);
}

async function request<T>(path: string, init: RequestInit = {}, authEventSource: unknown = Symbol("account-request")): Promise<T> {
  const authEpoch = getAccountAuthEpoch();
  let unauthorizedError: unknown;
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  const perform = () => fetchJson<T>(apiUrl(path), {
    ...init,
    credentials: "include",
    cache: "no-store",
    headers,
  });

  try {
    const response = await perform();
    assertAccountAuthEpoch(authEpoch);
    markAccountAuthenticated(authEventSource);
    return response;
  } catch (error) {
    if (!isApiError(error) || error.status !== 401) throw error;
    if (getAccountAuthEpoch() !== authEpoch) throw error;
    unauthorizedError = error;
  }

  try {
    await refreshAccessCookie(init.signal ?? undefined);
    if (getAccountAuthEpoch() !== authEpoch) {
      throw unauthorizedError;
    }
    const response = await perform();
    assertAccountAuthEpoch(authEpoch);
    markAccountAuthenticated(authEventSource);
    return response;
  } catch (error) {
    if (getAccountAuthEpoch() === authEpoch && isApiError(error) && error.status === 401) {
      markAccountAnonymous(authEventSource);
    }
    throw error;
  }
}

export function fetchFavorites(limit = 100, offset = 0, signal?: AbortSignal): Promise<Favorite[]> {
  return request(`/api/v1/users/me/favorites?limit=${limit}&offset=${offset}`, { signal });
}

export function addFavorite(sessionId: string, authEventSource?: unknown, signal?: AbortSignal): Promise<Favorite> {
  return request(`/api/v1/users/me/favorites/${encodeURIComponent(sessionId)}`, { method: "PUT", signal }, authEventSource);
}

export function removeFavorite(sessionId: string, authEventSource?: unknown, signal?: AbortSignal): Promise<void> {
  return request(`/api/v1/users/me/favorites/${encodeURIComponent(sessionId)}`, { method: "DELETE", signal }, authEventSource);
}

export function fetchListeningHistory(limit = 50, offset = 0, signal?: AbortSignal): Promise<ListeningHistoryItem[]> {
  return request(`/api/v1/users/me/listening-history?limit=${limit}&offset=${offset}`, { signal });
}

export function updateListeningProgress(
  sessionId: string,
  update: ListeningProgressUpdate,
  signal?: AbortSignal,
): Promise<ListeningHistoryItem> {
  return request(`/api/v1/users/me/listening-history/${encodeURIComponent(sessionId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(update),
    signal,
  });
}

export function removeListeningHistoryItem(sessionId: string, signal?: AbortSignal): Promise<void> {
  return request(`/api/v1/users/me/listening-history/${encodeURIComponent(sessionId)}`, { method: "DELETE", signal });
}

export function clearListeningHistory(signal?: AbortSignal): Promise<void> {
  return request("/api/v1/users/me/listening-history", { method: "DELETE", signal });
}
