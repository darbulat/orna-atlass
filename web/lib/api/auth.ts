import { apiUrl } from "./sessions";

export type User = {
  id: string;
  email: string;
  role: "member" | "editor" | "admin";
  is_active: boolean;
  created_at: string;
};

export type Membership = {
  id: string | null;
  user_id: string;
  status: "inactive" | "active" | "cancelled" | "expired";
  plan: string;
  starts_at: string | null;
  expires_at: string | null;
  is_entitled: boolean;
};

type TokenResponse = {
  access_token: string;
  token_type: "bearer";
  expires_at: string;
  user: User;
};

async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    credentials: "include",
    headers: { Accept: "application/json", ...init.headers },
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail ?? `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
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

export function logout(): Promise<{ status: string }> {
  return apiRequest<{ status: string }>("/api/v1/auth/logout", { method: "POST" });
}

export function fetchCurrentUser(): Promise<User> {
  return apiRequest<User>("/api/v1/users/me");
}

export function fetchMembership(): Promise<Membership> {
  return apiRequest<Membership>("/api/v1/memberships/me");
}
