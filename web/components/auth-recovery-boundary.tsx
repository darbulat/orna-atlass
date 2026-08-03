"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

import { fetchMembership } from "../lib/api/auth";

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
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [router]);

  return <p role="status">Restoring your membership access…</p>;
}
