"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

import { fetchMembership } from "../lib/api/auth";
import { ApiError } from "../lib/api/client";

export function AuthRecoveryBoundary() {
  const router = useRouter();
  const attempted = useRef(false);

  useEffect(() => {
    if (attempted.current) return;
    attempted.current = true;
    let active = true;
    void fetchMembership()
      .then(() => {
        if (active) router.refresh();
      })
      .catch((error: unknown) => {
        if (active && error instanceof ApiError && error.status === 401) {
          // A terminal refresh failure clears the stale root cookie. Re-render
          // the server route once so anonymous-capable catalogs can proceed.
          router.refresh();
        }
      });
    return () => {
      active = false;
    };
  }, [router]);

  return <p role="status">Restoring your membership access…</p>;
}
