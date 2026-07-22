"use client";

import type { FeaturedSession } from "../lib/api/sessions";

function formatDuration(seconds: number | null | undefined) {
  if (seconds == null) return "Duration pending";
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}:${String(remainder).padStart(2, "0")}`;
}

export function FeaturedSessions({ sessions }: { sessions: FeaturedSession[] }) {
  return (
    <div className="panel featured-grid">
      {sessions.map((session) => (
        <article key={session.id}>
          <span>{formatDuration(session.duration_seconds)}</span>
          <h3>
            <a
              href={`/sessions/${encodeURIComponent(session.slug)}`}
              className="popular-location-open"
              onClick={(event) => {
                if (!document.querySelector("#atlas-entry")) return;
                event.preventDefault();
                window.dispatchEvent(new CustomEvent("orna:open-session", {
                  detail: { locationSlug: session.location.slug, sessionSlug: session.slug },
                }));
              }}
            >
              {session.title}
            </a>
          </h3>
          <p>{session.description ?? "Published field recording"}</p>
          <small>Public recording</small>
        </article>
      ))}
    </div>
  );
}
