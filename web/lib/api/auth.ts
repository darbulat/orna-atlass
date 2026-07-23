import type { components } from "./generated";
import { runExplicitAuthentication } from "./auth-refresh";
import { fetchJson } from "./client";
import { apiUrl } from "./sessions";
import {
  beginAccountAuthBoundary,
  cancelAccountAuthBoundary,
  completeAccountAuthBoundary,
  getAccountAuthEpoch,
  markAccountAuthenticated,
} from "./account-auth-state";

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
  const boundary = beginAccountAuthBoundary();
  return runExplicitAuthentication(async () => {
    try {
      const user = await apiRequest<User>("/api/v1/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      completeAccountAuthBoundary(boundary, "authenticated");
      return user;
    } catch (error) {
      cancelAccountAuthBoundary(boundary);
      throw error;
    }
  });
}

export function login(email: string, password: string): Promise<TokenResponse> {
  const boundary = beginAccountAuthBoundary();
  return runExplicitAuthentication(async () => {
    try {
      const token = await apiRequest<TokenResponse>("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      completeAccountAuthBoundary(boundary, "authenticated");
      return token;
    } catch (error) {
      cancelAccountAuthBoundary(boundary);
      throw error;
    }
  });
}

export function logout(): Promise<components["schemas"]["LogoutResponse"]> {
  const boundary = beginAccountAuthBoundary();
  return runExplicitAuthentication(async () => {
    try {
      const response = await apiRequest<components["schemas"]["LogoutResponse"]>(
        "/api/v1/auth/logout",
        { method: "POST" },
      );
      completeAccountAuthBoundary(boundary, "anonymous");
      return response;
    } catch (error) {
      cancelAccountAuthBoundary(boundary);
      throw error;
    }
  });
}

export async function fetchCurrentUser(): Promise<User> {
  const accountEpoch = getAccountAuthEpoch();
  const user = await apiRequest<User>("/api/v1/users/me");
  if (accountEpoch !== getAccountAuthEpoch()) {
    throw new DOMException("Authentication changed while loading the current user", "AbortError");
  }
  markAccountAuthenticated();
  return user;
}

export async function fetchMembership(): Promise<Membership> {
  const accountEpoch = getAccountAuthEpoch();
  const membership = await apiRequest<Membership>("/api/v1/memberships/me");
  if (accountEpoch !== getAccountAuthEpoch()) {
    throw new DOMException("Authentication changed while loading membership", "AbortError");
  }
  return membership;
}
