"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { apiUrl, refreshAccessCookie } from "../../lib/api/sessions";

const REVALIDATE_INTERVAL_MS = 30_000;

type AdminSessionGuardProps = {
  children: ReactNode;
};

export function AdminSessionGuard({ children }: AdminSessionGuardProps) {
  const [accessRevoked, setAccessRevoked] = useState(false);

  const revalidate = useCallback(async () => {
    try {
      const requestIdentity = () => fetch(apiUrl("/api/v1/admin/me"), {
        cache: "no-store",
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      let response = await requestIdentity();
      if (response.status === 401) {
        await refreshAccessCookie();
        response = await requestIdentity();
      }
      if (!response.ok) {
        setAccessRevoked(true);
        return;
      }
      const payload: unknown = await response.json();
      const authorized = typeof payload === "object"
        && payload !== null
        && "role" in payload
        && "is_admin" in payload
        && payload.role === "admin"
        && payload.is_admin === true;
      setAccessRevoked(!authorized);
    } catch {
      // Privileged data fails closed if current authorization cannot be proven.
      setAccessRevoked(true);
    }
  }, []);

  useEffect(() => {
    const onFocus = () => void revalidate();
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") void revalidate();
    };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisibilityChange);
    const interval = window.setInterval(() => void revalidate(), REVALIDATE_INTERVAL_MS);
    return () => {
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.clearInterval(interval);
    };
  }, [revalidate]);

  if (accessRevoked) {
    return (
      <main className="admin-shell" aria-live="assertive">
        <section className="admin-card">
          <h1 className="admin-title">Доступ администратора отозван</h1>
          <p>Привилегированные данные удалены из текущего представления. Обновите страницу после восстановления доступа.</p>
        </section>
      </main>
    );
  }

  return children;
}
