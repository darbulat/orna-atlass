"use client";

import { usePathname } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
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
  currentTimeSeconds: number;
  durationSeconds: number | null;
  error: string | null;
  play: (session: SessionDetail) => Promise<void>;
  pause: () => void;
  seek: (seconds: number) => void;
};

const PlayerContext = createContext<PlayerContextValue | null>(null);

function streamUrl(url: string): string {
  return url.startsWith("/") ? apiUrl(url) : url;
}

function formatClockTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--:--";
  }
  return new Intl.DateTimeFormat("en-US", { hour: "2-digit", minute: "2-digit" }).format(date);
}

export function PlayerProvider({ children }: { children: ReactNode }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const currentSessionRef = useRef<SessionDetail | null>(null);
  const grantRequestRef = useRef(0);
  const refreshTimerRef = useRef<number | null>(null);
  const [currentSession, setCurrentSession] = useState<SessionDetail | null>(null);
  const [playbackState, setPlaybackState] = useState<PlaybackState>("idle");
  const [grant, setGrant] = useState<PlaybackGrant | null>(null);
  const [currentTimeSeconds, setCurrentTimeSeconds] = useState(0);
  const [durationSeconds, setDurationSeconds] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const clearRefreshTimer = useCallback(() => {
    if (refreshTimerRef.current !== null) {
      window.clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
  }, []);

  const updatePlaybackProgress = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) {
      return;
    }
    setCurrentTimeSeconds(Number.isFinite(audio.currentTime) ? audio.currentTime : 0);
    setDurationSeconds(
      Number.isFinite(audio.duration) && audio.duration > 0
        ? audio.duration
        : currentSessionRef.current?.duration_seconds ?? null,
    );
  }, []);

  const scheduleGrantRefresh = useCallback(
    (session: SessionDetail, nextGrant: PlaybackGrant) => {
      clearRefreshTimer();
      const expiresInMs = new Date(nextGrant.expires_at).getTime() - Date.now();
      const refreshAfterMs = nextGrant.refresh_after_seconds * 1000;
      const delayMs = Math.max(1000, Math.min(refreshAfterMs, expiresInMs - 30_000));

      refreshTimerRef.current = window.setTimeout(() => {
        void (async () => {
          const requestId = ++grantRequestRef.current;
          if (currentSessionRef.current?.id !== session.id) {
            return;
          }
          setPlaybackState("refreshing_grant");
          try {
            const refreshedGrant = await requestPlaybackGrant(session.id);
            if (requestId !== grantRequestRef.current || currentSessionRef.current?.id !== session.id) {
              return;
            }
            setGrant(refreshedGrant);
            scheduleGrantRefresh(session, refreshedGrant);
            setPlaybackState(audioRef.current?.paused ? "paused" : "playing");
          } catch (err) {
            if (requestId === grantRequestRef.current) {
              setError(err instanceof Error ? err.message : "Unable to refresh playback grant");
              setPlaybackState("error");
            }
          }
        })();
      }, delayMs);
    },
    [clearRefreshTimer],
  );

  const play = useCallback(
    async (session: SessionDetail) => {
      if (currentSessionRef.current?.id === session.id && audioRef.current?.src) {
        setError(null);
        await audioRef.current.play();
        updatePlaybackProgress();
        setPlaybackState("playing");
        return;
      }

      const requestId = ++grantRequestRef.current;
      currentSessionRef.current = session;
      setCurrentSession(session);
      setPlaybackState("requesting_grant");
      setCurrentTimeSeconds(0);
      setDurationSeconds(session.duration_seconds);
      setError(null);

      try {
        const nextGrant = await requestPlaybackGrant(session.id);
        if (requestId !== grantRequestRef.current || currentSessionRef.current?.id !== session.id) {
          return;
        }

        setGrant(nextGrant);
        setPlaybackState("ready");

        if (!audioRef.current) {
          audioRef.current = new Audio();
        }
        audioRef.current.src = streamUrl(nextGrant.stream_url);
        audioRef.current.ontimeupdate = updatePlaybackProgress;
        audioRef.current.onloadedmetadata = updatePlaybackProgress;
        audioRef.current.ondurationchange = updatePlaybackProgress;
        audioRef.current.onended = () => {
          const sessionDuration = currentSessionRef.current?.duration_seconds;
          const audioDuration = audioRef.current?.duration;
          setCurrentTimeSeconds(
            sessionDuration ?? (Number.isFinite(audioDuration) && audioDuration != null ? audioDuration : 0),
          );
          setPlaybackState("ended");
        };
        audioRef.current.onerror = () => setPlaybackState("error");
        audioRef.current.onstalled = () => setPlaybackState("stalled");
        scheduleGrantRefresh(session, nextGrant);
        await audioRef.current.play();
        updatePlaybackProgress();
        if (requestId === grantRequestRef.current && currentSessionRef.current?.id === session.id) {
          setPlaybackState("playing");
        }
      } catch (err) {
        if (requestId === grantRequestRef.current) {
          setError(err instanceof Error ? err.message : "Playback failed");
          setPlaybackState("error");
        }
      }
    },
    [scheduleGrantRefresh, updatePlaybackProgress],
  );

  const pause = useCallback(() => {
    audioRef.current?.pause();
    updatePlaybackProgress();
    setPlaybackState("paused");
  }, [updatePlaybackProgress]);

  const seek = useCallback((seconds: number) => {
    const audio = audioRef.current;
    const fallbackDuration = currentSessionRef.current?.duration_seconds ?? null;
    const resolvedDuration =
      audio && Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : fallbackDuration;
    const nextTime = Math.min(Math.max(seconds, 0), resolvedDuration ?? Math.max(seconds, 0));

    if (audio) {
      try {
        audio.currentTime = nextTime;
      } catch {
        // Some streams reject seeking before metadata is ready; keep UI state in sync anyway.
      }
    }

    setCurrentTimeSeconds(nextTime);
    setDurationSeconds(resolvedDuration);
    setPlaybackState((state) => (state === "ended" ? "paused" : state));
  }, []);

  useEffect(() => clearRefreshTimer, [clearRefreshTimer]);

  const value = useMemo(
    () => ({ currentSession, playbackState, grant, currentTimeSeconds, durationSeconds, error, play, pause, seek }),
    [currentSession, playbackState, grant, currentTimeSeconds, durationSeconds, error, play, pause, seek],
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
  const pathname = usePathname();

  const isSessionOrAtlasRoute = pathname?.startsWith("/sessions/") || pathname?.startsWith("/atlas");

  if (!currentSession || isSessionOrAtlasRoute) {
    return null;
  }

  return (
    <aside className="global-player" aria-label="Global audio player">
      <div>
        <span className="eyebrow">Global player</span>
        <strong>{currentSession.title}</strong>
        <small>{playbackState}</small>
      </div>
      {grant ? <small>Grant expires {formatClockTime(grant.expires_at)}</small> : null}
      {error ? <small className="error-text">{error}</small> : null}
      <button type="button" onClick={pause}>Pause</button>
    </aside>
  );
}
