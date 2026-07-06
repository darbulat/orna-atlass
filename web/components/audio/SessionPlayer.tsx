"use client";

import type { SessionDetail } from "../../lib/api/sessions";
import { usePlayer } from "./PlayerProvider";

export function SessionPlayer({ session }: { session: SessionDetail }) {
  const { currentSession, playbackState, play, pause, error } = usePlayer();
  const isCurrent = currentSession?.id === session.id;
  const isPlaying = isCurrent && playbackState === "playing";

  return (
    <section className="player-card" aria-label="Session player">
      <div>
        <p className="eyebrow">Player shell</p>
        <h2>Playback lifecycle</h2>
        <p>
          Metadata renders first. A protected playback grant is requested only when the listener presses play.
        </p>
      </div>
      <div className="player-actions">
        {isPlaying ? (
          <button type="button" onClick={pause}>Pause session</button>
        ) : (
          <button type="button" onClick={() => void play(session)}>Request grant & play</button>
        )}
        <span>{isCurrent ? playbackState : "idle"}</span>
      </div>
      {error && isCurrent ? <p className="error-text">{error}</p> : null}
    </section>
  );
}
