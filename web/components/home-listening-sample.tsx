"use client";

import { useState } from "react";

import type { FeaturedSession } from "../lib/api/sessions";
import { fetchSessionDetail } from "../lib/api/sessions";
import { usePlayer } from "./audio/PlayerProvider";

type HomeListeningSampleProps = {
  session: FeaturedSession;
};

export function HomeListeningSample({ session }: HomeListeningSampleProps) {
  const { currentSession, playbackState, play, pause } = usePlayer();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isCurrent = currentSession?.id === session.id;
  const isPlaying = isCurrent && playbackState === "playing";

  async function togglePlayback() {
    if (isPlaying) {
      pause();
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const detail = await fetchSessionDetail(session.slug);
      window.dispatchEvent(new CustomEvent("orna:analytics", {
        detail: { name: "sample_play_started", placement: "hero_sample", session: session.slug },
      }));
      await play(detail);
    } catch {
      setError("This recording is temporarily unavailable. Explore the atlas to choose another place.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="hero-sample" aria-label="Free listening sample">
      <button type="button" onClick={() => void togglePlayback()} disabled={isLoading}>
        <span aria-hidden="true">{isPlaying ? "Ⅱ" : "▶"}</span>
        {isLoading ? "Connecting…" : isPlaying ? "Pause" : "Listen free"}
      </button>
      <div>
        <strong>{session.title}</strong>
        <span>{session.location.name} · continuous field recording</span>
      </div>
      {error ? <p role="alert">{error}</p> : null}
    </div>
  );
}
