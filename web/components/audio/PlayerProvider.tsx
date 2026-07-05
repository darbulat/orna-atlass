"use client";

import { createContext, useContext, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import { apiUrl, requestPlaybackGrant, type PlaybackGrant, type SessionDetail } from "../../lib/api/sessions";

type PlaybackState =
  | "idle"
  | "requesting_grant"
  | "ready"
  | "playing"
  | "paused"
  | "refreshing_grant"
  | "stalled"
  | "ended"
  | "error";

type PlayerContextValue = {
  currentSession: SessionDetail | null;
  playbackState: PlaybackState;
  grant: PlaybackGrant | null;
  error: string | null;
  play: (session: SessionDetail) => Promise<void>;
  pause: () => void;
};

const PlayerContext = createContext<PlayerContextValue | null>(null);

export function PlayerProvider({ children }: { children: ReactNode }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [currentSession, setCurrentSession] = useState<SessionDetail | null>(null);
  const [playbackState, setPlaybackState] = useState<PlaybackState>("idle");
  const [grant, setGrant] = useState<PlaybackGrant | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function play(session: SessionDetail) {
    setCurrentSession(session);
    setPlaybackState("requesting_grant");
    setError(null);
    try {
      const nextGrant = await requestPlaybackGrant(session.id);
      setGrant(nextGrant);
      setPlaybackState("ready");

      if (!audioRef.current) {
        audioRef.current = new Audio();
      }
      audioRef.current.src = nextGrant.stream_url.startsWith("/")
        ? apiUrl(nextGrant.stream_url)
        : nextGrant.stream_url;
      audioRef.current.onended = () => setPlaybackState("ended");
      audioRef.current.onerror = () => setPlaybackState("error");
      audioRef.current.onstalled = () => setPlaybackState("stalled");
      await audioRef.current.play();
      setPlaybackState("playing");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Playback failed");
      setPlaybackState("error");
    }
  }

  function pause() {
    audioRef.current?.pause();
    setPlaybackState("paused");
  }

  const value = useMemo(
    () => ({ currentSession, playbackState, grant, error, play, pause }),
    [currentSession, playbackState, grant, error],
  );

  return (
    <PlayerContext.Provider value={value}>
      {children}
      <GlobalPlayer />
    </PlayerContext.Provider>
  );
}

export function usePlayer() {
  const value = useContext(PlayerContext);
  if (!value) {
    throw new Error("usePlayer must be used inside PlayerProvider");
  }
  return value;
}

function GlobalPlayer() {
  const { currentSession, playbackState, grant, error, pause } = usePlayer();
  if (!currentSession) {
    return null;
  }

  return (
    <aside className="global-player" aria-label="Global audio player">
      <div>
        <span className="eyebrow">Global player</span>
        <strong>{currentSession.title}</strong>
        <small>{playbackState}</small>
      </div>
      {grant ? <small>Grant expires {new Date(grant.expires_at).toLocaleTimeString()}</small> : null}
      {error ? <small className="error-text">{error}</small> : null}
      <button type="button" onClick={pause}>Pause</button>
    </aside>
  );
}
