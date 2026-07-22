import type { components } from "./generated";
import { fetchJson } from "./client";
import { apiUrl } from "./sessions";
import { markAccountAnonymous, markAccountAuthenticated } from "./account-auth-state";

export type User = components["schemas"]["UserRead"];
export type Membership = components["schemas"]["MembershipRead"];
export type TokenResponse = components["schemas"]["TokenResponse"];
export type OAuthProvider = "google" | "apple" | "facebook";
export type OAuthProvidersResponse = components["schemas"]["OAuthProvidersResponse"];

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

export function oauthStartUrl(provider: OAuthProvider, returnTo = "/membership"): string {
  return apiUrl(`/api/v1/auth/oauth/${provider}/start?return_to=${encodeURIComponent(returnTo)}`);
}

export async function fetchOAuthProviders(): Promise<OAuthProvidersResponse> {
  const payload = await apiRequest<unknown>("/api/v1/auth/oauth/providers");
  if (
    typeof payload !== "object"
    || payload === null
    || !("providers" in payload)
    || !Array.isArray(payload.providers)
    || payload.providers.some(
      (provider) => provider !== "google" && provider !== "apple" && provider !== "facebook",
    )
  ) {
    throw new Error("Invalid OAuth provider response");
  }
  return {
    providers: payload.providers.filter(
      (provider, index, providers) => providers.indexOf(provider) === index,
    ) as OAuthProvider[],
  };
}

export function requestMagicLink(email: string, returnTo: string): Promise<{ accepted: true }> {
  return apiRequest<{ accepted: true }>("/api/v1/auth/magic-link/request", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, return_to: returnTo }),
  }).then((payload) => {
    if (payload.accepted !== true) throw new Error("Invalid magic-link response");
    return payload;
  });
}

export function register(email: string, password: string): Promise<User> {
  return apiRequest<User>("/api/v1/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  }).then((user) => {
    markAccountAuthenticated();
    return user;
  });
}

export function login(email: string, password: string): Promise<TokenResponse> {
  return apiRequest<TokenResponse>("/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  }).then((token) => {
    markAccountAuthenticated();
    return token;
  });
}

export function logout(): Promise<components["schemas"]["LogoutResponse"]> {
  return apiRequest<components["schemas"]["LogoutResponse"]>("/api/v1/auth/logout", { method: "POST" })
    .then((response) => {
      markAccountAnonymous();
      return response;
    });
}

export function fetchCurrentUser(): Promise<User> {
  return apiRequest<User>("/api/v1/users/me").then((user) => {
    markAccountAuthenticated();
    return user;
  });
}

export function fetchMembership(): Promise<Membership> {
  return apiRequest<Membership>("/api/v1/memberships/me");
}
