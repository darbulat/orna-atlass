"use client";

import Hls from "hls.js";
import { usePathname } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef, useState } from "react";
import type { ReactNode } from "react";

import { apiErrorMessage } from "../../lib/api/client";
import {
  ACCOUNT_AUTH_CHANGED_EVENT,
  getAccountAuthEpoch,
  isAccountAuthenticationUnavailable,
} from "../../lib/api/account-auth-state";
import { updateListeningProgress } from "../../lib/api/library";
import { apiUrl, requestPlaybackGrant, type PlaybackGrant, type SessionDetail } from "../../lib/api/sessions";
import { observeListeningProgressContinuation } from "./favoriteContinuation";
import { canDrainListeningProgress } from "./listeningProgress";
import { initialPlayerState, playerReducer, type PlaybackState } from "./playerMachine";
import { detachAudio, disposePlayerResources, isHlsStream } from "./playerResources";

type PlayerAnalyticsPlacement = "global_player" | "session_overlay" | "popular_locations" | "hero_sample";

type PlayerContextValue = {
  currentSession: SessionDetail | null;
  playbackState: PlaybackState;
  grant: PlaybackGrant | null;
  currentTimeSeconds: number;
  durationSeconds: number | null;
  error: string | null;
  play: (session: SessionDetail, placement?: PlayerAnalyticsPlacement) => Promise<boolean>;
  pause: (placement?: PlayerAnalyticsPlacement) => void;
  resume: (placement?: PlayerAnalyticsPlacement) => Promise<boolean>;
  seek: (seconds: number) => void;
};

const PlayerContext = createContext<PlayerContextValue | null>(null);
const GlobalPlayerSuppressionContext = createContext<((isSuppressed: boolean) => void) | null>(null);

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
  const hlsRef = useRef<Hls | null>(null);
  const currentSessionRef = useRef<SessionDetail | null>(null);
  const grantRequestRef = useRef(0);
  const grantAbortRef = useRef<AbortController | null>(null);
  const refreshTimerRef = useRef<number | null>(null);
  const mountedRef = useRef(false);
  const providerGenerationRef = useRef(0);
  const historyAbortRef = useRef<AbortController | null>(null);
  const historyRef = useRef({
    inFlight: false,
    lastSentAt: 0,
    pendingBySession: new Map<string, {
      sessionId: string;
      position: number;
      completed: boolean;
      accountEpoch: number;
    }>(),

  });
  const engagementRef = useRef({
    sessionId: null as string | null,
    previousMediaTime: 0,
    listenedSeconds: 0,
    emitted: new Set<number>(),
  });
  const [player, dispatch] = useReducer(playerReducer, initialPlayerState);
  const [isGlobalPlayerSuppressed, setIsGlobalPlayerSuppressed] = useState(false);

  const writeListeningProgress = useCallback((sessionId: string, position: number, completed: boolean, force = false) => {
    const history = historyRef.current;
    if (!mountedRef.current || isAccountAuthenticationUnavailable()) return;
    const providerGeneration = providerGenerationRef.current;
    const now = Date.now();
    if (!force && now - history.lastSentAt < 15_000) return;
    const next = {
      sessionId,
      position: Number.isFinite(position) ? Math.max(0, position) : 0,
      completed,
      accountEpoch: getAccountAuthEpoch(),
    };
    if (history.inFlight) {
      history.pendingBySession.set(sessionId, next);
      return;
    }
    history.inFlight = true;
    history.lastSentAt = now;
    const controller = new AbortController();
    historyAbortRef.current = controller;
    void updateListeningProgress(next.sessionId, {
      position_seconds: next.position,
      completed: next.completed,
    }, controller.signal).catch(() => undefined).finally(() => {
      if (historyAbortRef.current === controller) historyAbortRef.current = null;
      if (!canDrainListeningProgress(
        providerGeneration,
        providerGenerationRef.current,
        mountedRef.current,
      )) {
        observeListeningProgressContinuation();
        return;
      }
      history.inFlight = false;
      const currentAccountEpoch = getAccountAuthEpoch();
      let pendingEntry = history.pendingBySession.entries().next();
      while (!pendingEntry.done) {
        const [pendingSessionId, pending] = pendingEntry.value;
        history.pendingBySession.delete(pendingSessionId);
        if (pending.accountEpoch === currentAccountEpoch) {
          writeListeningProgress(pending.sessionId, pending.position, pending.completed, true);
          break;
        }
        pendingEntry = history.pendingBySession.entries().next();
      }
      observeListeningProgressContinuation();
    });
  }, []);

  const clearRefreshTimer = useCallback(() => {
    if (refreshTimerRef.current !== null) {
      window.clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
  }, []);

  const attachStream = useCallback((audio: HTMLAudioElement, url: string) => {
    hlsRef.current?.destroy();
    hlsRef.current = null;
    const resolvedUrl = streamUrl(url);
    const hasNativeHls = typeof audio.canPlayType === "function"
      && Boolean(audio.canPlayType("application/vnd.apple.mpegurl"));
    if (isHlsStream(resolvedUrl) && !hasNativeHls && Hls.isSupported()) {
      const hls = new Hls();
      hlsRef.current = hls;
      hls.attachMedia(audio);
      hls.loadSource(resolvedUrl);
      return;
    }
    audio.src = resolvedUrl;
  }, []);

  const updatePlaybackProgress = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) {
      return;
    }
    if (!audio.paused && audio.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
      dispatch({ type: "playing" });
    }
    const session = currentSessionRef.current;
    const engagement = engagementRef.current;
    const mediaTime = Number.isFinite(audio.currentTime) ? audio.currentTime : 0;
    if (session && engagement.sessionId === session.id && !audio.paused) {
      const elapsed = mediaTime - engagement.previousMediaTime;
      // Normal timeupdate deltas are small; cap them so seeking is not counted as listening.
      if (elapsed > 0 && elapsed <= 15) {
        engagement.listenedSeconds += elapsed;
      }
      for (const threshold of [30, 300]) {
        if (engagement.listenedSeconds >= threshold && !engagement.emitted.has(threshold)) {
          engagement.emitted.add(threshold);
          window.dispatchEvent(new CustomEvent("orna:analytics", {
            detail: {
              name: threshold === 30 ? "listening_30_seconds" : "listening_5_minutes",
              session_slug: session.slug,
            },
          }));
        }
      }
    }
    engagement.previousMediaTime = mediaTime;
    if (session && !audio.paused) writeListeningProgress(session.id, mediaTime, false);
    dispatch({
      type: "progress",
      currentTimeSeconds: mediaTime,
      durationSeconds:
        Number.isFinite(audio.duration) && audio.duration > 0
          ? audio.duration
          : currentSessionRef.current?.duration_seconds ?? null,
    });
  }, [writeListeningProgress]);

  const scheduleGrantRefresh = useCallback(
    (session: SessionDetail, nextGrant: PlaybackGrant) => {
      clearRefreshTimer();
      const expiresInMs = new Date(nextGrant.expires_at).getTime() - Date.now();
      const refreshAfterMs = nextGrant.refresh_after_seconds * 1000;
      const delayMs = Math.max(1000, Math.min(refreshAfterMs, expiresInMs - 30_000));

      refreshTimerRef.current = window.setTimeout(() => {
        void (async () => {
          if (currentSessionRef.current?.id !== session.id) {
            return;
          }
          const requestId = ++grantRequestRef.current;
          dispatch({ type: "refresh_started", sessionId: session.id });
          const controller = new AbortController();
          grantAbortRef.current?.abort();
          grantAbortRef.current = controller;
          try {
            const refreshedGrant = await requestPlaybackGrant(session.id, controller.signal);
            if (requestId !== grantRequestRef.current || currentSessionRef.current?.id !== session.id) {
              return;
            }
            const audio = audioRef.current;
            const shouldResume = Boolean(audio && !audio.paused);
            const resumeAt = audio?.currentTime ?? 0;
            if (audio) {
              audio.pause();
              const restorePosition = () => {
                if (requestId !== grantRequestRef.current || currentSessionRef.current?.id !== session.id) {
                  return;
                }
                try {
                  audio.currentTime = resumeAt;
                } catch {
                  // The media element will emit another metadata event if the stream is still loading.
                }
              };
              audio.onloadedmetadata = () => {
                restorePosition();
                updatePlaybackProgress();
                if (requestId === grantRequestRef.current && currentSessionRef.current?.id === session.id) {
                  audio.onloadedmetadata = updatePlaybackProgress;
                }
              };
              attachStream(audio, refreshedGrant.stream_url);
              audio.load();
              restorePosition();
              if (shouldResume) {
                await audio.play();
              }
            }
            if (requestId !== grantRequestRef.current || currentSessionRef.current?.id !== session.id) {
              return;
            }
            scheduleGrantRefresh(session, refreshedGrant);
            dispatch({
              type: "grant_refreshed",
              sessionId: session.id,
              grant: refreshedGrant,
              resumed: Boolean(audio && !audio.paused),
            });
          } catch (error) {
            if (controller.signal.aborted) {
              return;
            }
            if (requestId === grantRequestRef.current) {
              dispatch({
                type: "failed",
                sessionId: session.id,
                message: apiErrorMessage(error, "Unable to refresh playback grant"),
              });
            }
          }
        })();
      }, delayMs);
    },
    [attachStream, clearRefreshTimer, updatePlaybackProgress],
  );

  const play = useCallback(
    async (session: SessionDetail, placement: PlayerAnalyticsPlacement = "session_overlay") => {
      const grantExpiresAt = player.grant ? new Date(player.grant.expires_at).getTime() : 0;
      if (
        currentSessionRef.current?.id === session.id
        && audioRef.current?.src
        && grantExpiresAt > Date.now() + 30_000
      ) {
        const requestId = grantRequestRef.current;
        const accountEpoch = getAccountAuthEpoch();
        const audio = audioRef.current;
        dispatch({ type: "clear_error" });
        try {
          await audio.play();
          if (
            requestId !== grantRequestRef.current
            || accountEpoch !== getAccountAuthEpoch()
            || currentSessionRef.current?.id !== session.id
            || audioRef.current !== audio
          ) {
            return false;
          }
          updatePlaybackProgress();
          dispatch({ type: "playing" });
          window.dispatchEvent(new CustomEvent("orna:analytics", {
            detail: { name: "player_play", placement },
          }));
          return true;
        } catch (error) {
          if (
            requestId !== grantRequestRef.current
            || accountEpoch !== getAccountAuthEpoch()
            || currentSessionRef.current?.id !== session.id
            || audioRef.current !== audio
          ) {
            return false;
          }
          dispatch({
            type: "failed",
            sessionId: session.id,
            message: apiErrorMessage(error, "Playback failed"),
          });
          return false;
        }
      }

      const requestId = ++grantRequestRef.current;
      grantAbortRef.current?.abort();
      const controller = new AbortController();
      grantAbortRef.current = controller;
      clearRefreshTimer();
      const previousSession = currentSessionRef.current;
      const resumeAt = previousSession?.id === session.id && audioRef.current
        ? audioRef.current.currentTime
        : 0;
      if (previousSession && previousSession.id !== session.id && audioRef.current) {
        writeListeningProgress(previousSession.id, audioRef.current.currentTime, false, true);
      }
      if (audioRef.current) {
        hlsRef.current?.destroy();
        hlsRef.current = null;
        detachAudio(audioRef.current);
      }
      currentSessionRef.current = session;
      engagementRef.current = {
        sessionId: session.id,
        previousMediaTime: resumeAt,
        listenedSeconds: 0,
        emitted: new Set<number>(),
      };
      dispatch({ type: "request_grant", session });

      try {
        const nextGrant = await requestPlaybackGrant(session.id, controller.signal);
        if (requestId !== grantRequestRef.current || currentSessionRef.current?.id !== session.id) {
          return false;
        }

        dispatch({ type: "grant_ready", sessionId: session.id, grant: nextGrant });

        if (!audioRef.current) {
          audioRef.current = new Audio();
        }
        const audio = audioRef.current;
        attachStream(audio, nextGrant.stream_url);
        audio.ontimeupdate = updatePlaybackProgress;
        const restorePosition = () => {
          if (requestId !== grantRequestRef.current || currentSessionRef.current?.id !== session.id) {
            return;
          }
          try {
            audio.currentTime = resumeAt;
          } catch {
            // Metadata will provide another opportunity to restore the same-session position.
          }
        };
        audio.onloadedmetadata = () => {
          restorePosition();
          updatePlaybackProgress();
          if (requestId === grantRequestRef.current && currentSessionRef.current?.id === session.id) {
            audio.onloadedmetadata = updatePlaybackProgress;
          }
        };
        audio.ondurationchange = updatePlaybackProgress;
        audio.onended = () => {
          const completedSession = currentSessionRef.current;
          if (completedSession) writeListeningProgress(completedSession.id, audio.currentTime, true, true);
          const sessionDuration = currentSessionRef.current?.duration_seconds;
          const audioDuration = audioRef.current?.duration;
          dispatch({
            type: "ended",
            currentTimeSeconds:
              sessionDuration ?? (Number.isFinite(audioDuration) && audioDuration != null ? audioDuration : 0),
          });
        };
        audio.onerror = () => dispatch({
          type: "failed",
          sessionId: currentSessionRef.current?.id ?? null,
          message: "The audio stream could not be played.",
        });
        audio.onstalled = () => dispatch({ type: "stalled" });
        audio.onplaying = () => dispatch({ type: "playing" });
        scheduleGrantRefresh(session, nextGrant);
        restorePosition();
        await audio.play();
        if (requestId !== grantRequestRef.current || currentSessionRef.current?.id !== session.id) {
          return false;
        }
        writeListeningProgress(session.id, audio.currentTime, false, true);
        updatePlaybackProgress();
        if (requestId === grantRequestRef.current && currentSessionRef.current?.id === session.id) {
          dispatch({ type: "playing" });
          const storedPreviewCount = Number(window.sessionStorage.getItem("orna:preview-count") ?? "0");
          const previewCount = Number.isSafeInteger(storedPreviewCount) && storedPreviewCount >= 0
            ? storedPreviewCount
            : 0;
          window.sessionStorage.setItem("orna:preview-count", String(previewCount + 1));
          const previewMilestones = previewCount === 0
            ? ["session_preview_start"]
            : previewCount === 1
              ? ["session_preview_second"]
              : [];
          const events = [
            ...previewMilestones,
            "player_play",
            ...(session.access_level === "members_only" ? ["member_session_play"] : []),
          ];
          for (const name of events) {
            window.dispatchEvent(new CustomEvent("orna:analytics", {
              detail: { name, placement },
            }));
          }
        }
        return true;
      } catch (error) {
        if (controller.signal.aborted) {
          return false;
        }
        if (requestId === grantRequestRef.current) {
          dispatch({
            type: "failed",
            sessionId: session.id,
            message: apiErrorMessage(error, "Playback failed"),
          });
        }
        return false;
      }
    },
    [attachStream, clearRefreshTimer, player.grant, scheduleGrantRefresh, updatePlaybackProgress, writeListeningProgress],
  );

  const pause = useCallback((placement: PlayerAnalyticsPlacement = "global_player") => {
    const activeSession = currentSessionRef.current;
    if (activeSession && audioRef.current) {
      writeListeningProgress(activeSession.id, audioRef.current.currentTime, false, true);
    }
    audioRef.current?.pause();
    updatePlaybackProgress();
    dispatch({ type: "paused" });
    window.dispatchEvent(new CustomEvent("orna:analytics", {
      detail: { name: "player_pause", placement },
    }));
  }, [updatePlaybackProgress, writeListeningProgress]);

  const resume = useCallback(async (placement: PlayerAnalyticsPlacement = "global_player") => {
    const session = currentSessionRef.current;
    if (!session) {
      return false;
    }
    return play(session, placement);
  }, [play]);

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

    // Reset the listening baseline explicitly so even a short seek cannot be
    // mistaken for elapsed playback by the following timeupdate event.
    engagementRef.current.previousMediaTime = nextTime;

    dispatch({ type: "seek", currentTimeSeconds: nextTime, durationSeconds: resolvedDuration });
    window.dispatchEvent(new CustomEvent("orna:analytics", {
      detail: { name: "player_seek", placement: "global_player" },
    }));
  }, []);

  useEffect(() => {
    const history = historyRef.current;
    const handleAccountBoundary = () => {
      grantRequestRef.current += 1;
      historyAbortRef.current?.abort();
      historyAbortRef.current = null;
      history.inFlight = false;
      history.pendingBySession.clear();
      hlsRef.current?.destroy();
      hlsRef.current = null;
      disposePlayerResources({
        audio: audioRef.current,
        abortController: grantAbortRef.current,
        refreshTimerId: refreshTimerRef.current,
        clearTimer: window.clearTimeout,
      });
      audioRef.current = null;
      grantAbortRef.current = null;
      refreshTimerRef.current = null;
      currentSessionRef.current = null;
      engagementRef.current = {
        sessionId: null,
        previousMediaTime: 0,
        listenedSeconds: 0,
        emitted: new Set<number>(),
      };
      dispatch({ type: "account_boundary" });
    };
    mountedRef.current = true;
    window.addEventListener(ACCOUNT_AUTH_CHANGED_EVENT, handleAccountBoundary);
    return () => {
      window.removeEventListener(ACCOUNT_AUTH_CHANGED_EVENT, handleAccountBoundary);
      mountedRef.current = false;
      providerGenerationRef.current += 1;
      historyAbortRef.current?.abort();
      historyAbortRef.current = null;
      history.inFlight = false;
      history.pendingBySession.clear();
      hlsRef.current?.destroy();
      hlsRef.current = null;
      disposePlayerResources({
        audio: audioRef.current,
        abortController: grantAbortRef.current,
        refreshTimerId: refreshTimerRef.current,
        clearTimer: window.clearTimeout,
      });
      refreshTimerRef.current = null;
      grantRequestRef.current += 1;
    };
  }, []);

  const value = useMemo(
    () => ({ ...player, play, pause, resume, seek }),
    [pause, play, player, resume, seek],
  );

  return (
    <GlobalPlayerSuppressionContext.Provider value={setIsGlobalPlayerSuppressed}>
      <PlayerContext.Provider value={value}>
        {children}
        <GlobalPlayer isSuppressed={isGlobalPlayerSuppressed} />
      </PlayerContext.Provider>
    </GlobalPlayerSuppressionContext.Provider>
  );
}

export function usePlayer() {
  const value = useContext(PlayerContext);
  if (!value) {
    throw new Error("usePlayer must be used inside PlayerProvider");
  }
  return value;
}

export function useGlobalPlayerSuppression(isSuppressed: boolean) {
  const setIsSuppressed = useContext(GlobalPlayerSuppressionContext);
  if (!setIsSuppressed) {
    throw new Error("useGlobalPlayerSuppression must be used inside PlayerProvider");
  }

  useEffect(() => {
    setIsSuppressed(isSuppressed);
    return () => setIsSuppressed(false);
  }, [isSuppressed, setIsSuppressed]);
}

function GlobalPlayer({ isSuppressed }: { isSuppressed: boolean }) {
  const { currentSession, playbackState, grant, error, pause, resume } = usePlayer();
  const pathname = usePathname();
  const [isExpanded, setIsExpanded] = useState(false);

  const isSessionRoute = pathname?.startsWith("/sessions/");

  if (!currentSession || isSessionRoute || isSuppressed) {
    return null;
  }

  const isPlaying = playbackState === "playing";

  return (
    <aside className={`global-player${isExpanded ? " is-expanded" : ""}`} aria-label="Global audio player">
      <button
        className="global-player-toggle"
        type="button"
        aria-label={isExpanded ? "Collapse player" : "Expand player"}
        aria-expanded={isExpanded}
        onClick={() => setIsExpanded((value) => !value)}
      >
        <strong>{currentSession.title}</strong>
        <span aria-hidden="true">{isExpanded ? "⌄" : "⌃"}</span>
      </button>
      <button
        className="global-player-playback"
        type="button"
        aria-label={isPlaying ? "Pause playback" : "Resume playback"}
        onClick={isPlaying ? () => pause("global_player") : () => void resume("global_player")}
      >
        <span aria-hidden="true">{isPlaying ? "Ⅱ" : "▶"}</span>
      </button>
      {isExpanded ? (
        <div className="global-player-details">
          <small>{playbackState}</small>
          {grant ? <small>Grant expires {formatClockTime(grant.expires_at)}</small> : null}
        </div>
      ) : null}
      {error ? <small className="global-player-error error-text" role="alert">{error}</small> : null}
    </aside>
  );
}
