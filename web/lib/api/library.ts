import type { components } from "./generated";
import { fetchJson, isApiError } from "./client";
import { markAccountAnonymous, markAccountAuthenticated } from "./account-auth-state";
import { refreshAuthentication } from "./auth-refresh";
import { apiUrl } from "./sessions";

export type Favorite = components["schemas"]["FavoriteRead"];
export type ListeningHistoryItem = components["schemas"]["ListeningHistoryRead"];
export type ListeningProgressUpdate = components["schemas"]["ListeningProgressUpdate"];

function refreshAccessCookie(): Promise<void> {
  return refreshAuthentication(() => fetchJson<unknown>(apiUrl("/api/v1/auth/refresh"), {
      method: "POST",
      credentials: "include",
      cache: "no-store",
      headers: { Accept: "application/json" },
  }));
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
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
    markAccountAuthenticated();
    return response;
  } catch (error) {
    if (!isApiError(error) || error.status !== 401) throw error;
  }

  try {
    await refreshAccessCookie();
    const response = await perform();
    markAccountAuthenticated();
    return response;
  } catch (error) {
    if (isApiError(error) && error.status === 401) markAccountAnonymous();
    throw error;
  }
}

export function fetchFavorites(limit = 100, offset = 0): Promise<Favorite[]> {
  return request(`/api/v1/users/me/favorites?limit=${limit}&offset=${offset}`);
}

export function addFavorite(sessionId: string): Promise<Favorite> {
  return request(`/api/v1/users/me/favorites/${encodeURIComponent(sessionId)}`, { method: "PUT" });
}

export function removeFavorite(sessionId: string): Promise<void> {
  return request(`/api/v1/users/me/favorites/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
}

export function fetchListeningHistory(limit = 50, offset = 0): Promise<ListeningHistoryItem[]> {
  return request(`/api/v1/users/me/listening-history?limit=${limit}&offset=${offset}`);
}

export function updateListeningProgress(sessionId: string, update: ListeningProgressUpdate): Promise<ListeningHistoryItem> {
  return request(`/api/v1/users/me/listening-history/${encodeURIComponent(sessionId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(update),
  });
}

export function removeListeningHistoryItem(sessionId: string): Promise<void> {
  return request(`/api/v1/users/me/listening-history/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
}

export function clearListeningHistory(): Promise<void> {
  return request("/api/v1/users/me/listening-history", { method: "DELETE" });
}
