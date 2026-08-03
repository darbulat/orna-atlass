"use client";

import { useEffect, useRef, useState } from "react";

import type { components } from "../lib/api/generated";
import { fetchSessionDetail } from "../lib/api/sessions";
import { fetchMembership } from "../lib/api/auth";
import { ApiError } from "../lib/api/client";
import { usePlayer } from "./audio/PlayerProvider";
import { LocationCardPhoto } from "./location-card-photo";

type AtlasPoint = components["schemas"]["AtlasPoint"];
type EntitlementState = "loading" | "entitled" | "not_entitled" | "unavailable";

function formatDuration(seconds: number | null | undefined) {
  if (seconds == null) return "Duration pending";
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}:${String(remainder).padStart(2, "0")}`;
}

export function PopularLocations({ locations }: { locations: AtlasPoint[] }) {
  const { currentSession, pause, play, playbackState } = usePlayer();
  const [loadingSlug, setLoadingSlug] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [entitlementState, setEntitlementState] = useState<EntitlementState>("loading");
  const canAttemptMemberPlayback = entitlementState === "entitled"
    || entitlementState === "unavailable";
  const previewRequestRef = useRef(0);

  useEffect(() => {
    if (!locations.some((location) => location.latest_session?.access_level === "members_only")) {
      setEntitlementState("not_entitled");
      return;
    }
    let active = true;
    void fetchMembership()
      .then((membership) => {
        if (active) {
          setEntitlementState(membership.is_entitled ? "entitled" : "not_entitled");
        }
      })
      .catch((error) => {
        if (active) {
          setEntitlementState(
            error instanceof ApiError && error.status === 401
              ? "not_entitled"
              : "unavailable",
          );
        }
      });
    return () => { active = false; };
  }, [locations]);

  async function togglePreview(location: AtlasPoint) {
    const slug = location.latest_session?.slug;
    if (!slug) return;
    if (currentSession?.slug === slug && playbackState === "playing") {
      pause("popular_locations");
      return;
    }
    setLoadingSlug(slug);
    setPreviewError(null);
    const requestId = ++previewRequestRef.current;
    window.dispatchEvent(new CustomEvent("orna:analytics", {
      detail: { name: "card_inline_play", placement: "popular_locations" },
    }));
    try {
      const session = await fetchSessionDetail(slug);
      if (requestId !== previewRequestRef.current) return;
      await play(session, "popular_locations");
    } catch {
      if (requestId === previewRequestRef.current) {
        setPreviewError("Preview unavailable. Try opening the location in the atlas.");
      }
    } finally {
      if (requestId === previewRequestRef.current) setLoadingSlug(null);
    }
  }

  return (
    <>
      <div className="popular-location-grid">
        {locations.map((location) => {
          const session = location.latest_session;
          const isCurrent = currentSession?.slug === session?.slug;
          const isPlaying = isCurrent && playbackState === "playing";
          const isLoading = loadingSlug === session?.slug;
          const isCheckingAccess = session?.access_level === "members_only"
            && entitlementState === "loading";
          return (
            <article className="popular-location-card" key={location.id}>
              <LocationCardPhoto
                name={location.name}
                photoUrl={location.photo_url}
                variant="popular"
              />
              <span className="popular-location-eyebrow">
                {location.habitat ?? location.region ?? "Field location"}
              </span>
              <h3>
                <button
                  type="button"
                  className="popular-location-open"
                  onClick={() => {
                    window.dispatchEvent(new CustomEvent("orna:analytics", {
                      detail: { name: "card_open", placement: "popular_locations" },
                    }));
                    window.dispatchEvent(new CustomEvent("orna:open-session", {
                      detail: { locationSlug: location.slug },
                    }));
                  }}
                >
                  {location.name}
                </button>
              </h3>
              <p>{[location.region, location.country_code].filter(Boolean).join(" · ")}</p>
              {session ? <small>{formatDuration(session.duration_seconds)}{isCurrent ? ` · ${isPlaying ? "Now playing" : "Paused"}` : ""}</small> : null}
              {session?.access_level === "public" || canAttemptMemberPlayback || isCheckingAccess ? (
                <button
                  type="button"
                  aria-label={isCheckingAccess
                    ? `Checking access for ${location.name}`
                    : `${isPlaying ? "Pause" : "Play"} preview for ${location.name}`}
                  aria-pressed={isPlaying}
                  disabled={isLoading || isCheckingAccess}
                  onClick={() => void togglePreview(location)}
                >
                  {isCheckingAccess ? "Checking access…" : isLoading ? "Loading…" : isPlaying ? "Pause" : "Preview"}
                </button>
              ) : <span className="atlas-members-label">🔒 Members only</span>}
            </article>
          );
        })}
      </div>
      {previewError ? <p className="error-text" role="alert">{previewError}</p> : null}
    </>
  );
}
