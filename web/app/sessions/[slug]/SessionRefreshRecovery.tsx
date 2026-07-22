"use client";

import type { ReactNode } from "react";
import { useEffect, useState } from "react";

import { SiteHeader } from "../../../components/site-header";
import { recoverBrowserSessionDetail, type SessionDetail } from "../../../lib/api/sessions";
import { SessionDetailContent } from "./SessionDetailContent";

export function SessionRefreshRecovery({
  slug,
  fallback,
}: {
  slug: string;
  fallback: ReactNode;
}) {
  const [failed, setFailed] = useState(false);
  const [session, setSession] = useState<SessionDetail | null>(null);

  useEffect(() => {
    let active = true;
    void recoverBrowserSessionDetail(slug).then(
      (detail) => {
        if (active) setSession(detail);
      },
      () => {
        if (active) setFailed(true);
      },
    );
    return () => {
      active = false;
    };
  }, [slug]);

  if (session) return <SessionDetailContent session={session} />;
  if (failed) return fallback;
  return (
    <main className="shell session-shell" id="main-content">
      <SiteHeader />
      <section className="panel unavailable-panel" role="status">
        <p className="eyebrow">Session</p>
        <h1>Checking session access</h1>
        <p>Checking whether this recording is available to your browser.</p>
      </section>
    </main>
  );
}
