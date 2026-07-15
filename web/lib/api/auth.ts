import type { components } from "./generated";
import { fetchJson } from "./client";
import { apiUrl } from "./sessions";

export type User = components["schemas"]["UserRead"];
export type Membership = components["schemas"]["MembershipRead"];
export type TokenResponse = components["schemas"]["TokenResponse"];

function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }
  return fetchJson<T>(apiUrl(path), {
    ...init,
    credentials: "include",
    headers,
  });
}

export function register(email: string, password: string): Promise<User> {
  return apiRequest<User>("/api/v1/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

export function login(email: string, password: string): Promise<TokenResponse> {
  return apiRequest<TokenResponse>("/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

export function logout(): Promise<components["schemas"]["LogoutResponse"]> {
  return apiRequest<components["schemas"]["LogoutResponse"]>("/api/v1/auth/logout", { method: "POST" });
}

export function fetchCurrentUser(): Promise<User> {
  return apiRequest<User>("/api/v1/users/me");
}

export function fetchMembership(): Promise<Membership> {
  return apiRequest<Membership>("/api/v1/memberships/me");
}
