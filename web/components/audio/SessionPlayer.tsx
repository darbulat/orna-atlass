"use client";

import Link from "next/link";
import Image from "next/image";
import { Fragment, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent } from "react";
import { isApiError } from "../../lib/api/client";
import {
  ACCOUNT_AUTH_CHANGED_EVENT,
  isAccountAuthenticationUnavailable,
} from "../../lib/api/account-auth-state";
import { addFavorite, fetchFavorites, removeFavorite } from "../../lib/api/library";
import { type SessionDetail } from "../../lib/api/sessions";
import { observeFavoriteContinuation } from "./favoriteContinuation";
import { usePlayer } from "./PlayerProvider";
import {
  TIMELINE_TRACK_START,
  TIMELINE_TRACK_WIDTH,
  buildWeatherItems,
  formatClockTime,
  formatCoordinates,
  formatDurationClock,
  formatOffset,
  formatLocalTime,
  groupBirdPartsBySpecies,
  timelineLeft,
  timelineRangeWidth,
  timelineTickLabels,
  timelineTotalSeconds,
  timelineWidth,
} from "./sessionPlayerUtils";

type SessionPlayerProps = {
  session: SessionDetail;
  onClose?: () => void;
  onPrevious?: () => void;
  onNext?: () => void;
};

function trackPlayerEvent(name: string) {
  window.dispatchEvent(new CustomEvent("orna:analytics", {
    detail: { name, placement: "session_overlay" },
  }));
}

export function SessionPlayer({ session, onClose, onPrevious, onNext }: SessionPlayerProps) {
  const { currentSession, playbackState, grant, currentTimeSeconds, durationSeconds, play, pause, seek, error } =
    usePlayer();
  const timelineRef = useRef<HTMLDivElement | null>(null);
  const pendingTimelineSeekRef = useRef<{ sessionId: string; seconds: number } | null>(null);
  const preparingTimelineSessionIdRef = useRef<string | null>(null);
  const timelineSeekGenerationRef = useRef(0);
  const [timelineDraftSeconds, setTimelineDraftSeconds] = useState<number | null>(null);
  const [isFavorite, setIsFavorite] = useState(false);
  const [favoritePending, setFavoritePending] = useState(true);
  const [favoriteHint, setFavoriteHint] = useState<string | null>(null);
  const [timelineHelpOpen, setTimelineHelpOpen] = useState(false);
  const [accountAuthRevision, setAccountAuthRevision] = useState(0);
  const favoriteLoadGenerationRef = useRef(0);
  const favoriteMutationSourceRef = useRef<object | null>(null);
  const favoriteMutationAbortRef = useRef<AbortController | null>(null);
  const favoriteAuthFailureRef = useRef<{ source: object; sessionId: string } | null>(null);
  const mountedRef = useRef(false);
  const displayedSessionIdRef = useRef(session.id);
  useLayoutEffect(() => {
    favoriteMutationAbortRef.current?.abort();
    displayedSessionIdRef.current = session.id;
  }, [session.id]);
  useLayoutEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      favoriteMutationAbortRef.current?.abort();
      favoriteMutationAbortRef.current = null;
    };
  }, []);
  const isCurrent = currentSession?.id === session.id;
  const isPlaying = isCurrent && playbackState === "playing";
  const displayedState = isCurrent ? playbackState : "idle";
  const birdParts = session.bird_parts?.parts ?? [];
  const birdTracks = groupBirdPartsBySpecies(birdParts);
  const timelineDuration = timelineTotalSeconds(session);
  const timelineTicks = timelineTickLabels(session.recorded_at, timelineDuration, session.location.timezone);
  const playbackDurationSeconds = Math.max(session.duration_seconds ?? 0, isCurrent ? (durationSeconds ?? 0) : 0, 1);
  const playbackCurrentSeconds = isCurrent
    ? Math.min(playbackState === "ended" ? playbackDurationSeconds : currentTimeSeconds, playbackDurationSeconds)
    : 0;
  const timelinePlayheadSeconds = timelineDraftSeconds ?? playbackCurrentSeconds;
  const timelinePlayheadLeft = timelineLeft(timelinePlayheadSeconds, timelineDuration);
  const playbackProgressPercent = (playbackCurrentSeconds / playbackDurationSeconds) * 100;
  const playbackProgressStyle = {
    "--playback-angle": `${playbackProgressPercent * 3.6}deg`,
  } as CSSProperties;
  const waveformPeaks = session.waveform?.peaks ?? [];
  const displayedWaveformPeaks =
    waveformPeaks.length > 0
      ? waveformPeaks.slice(0, 52)
      : [0.12, 0.22, 0.18, 0.36, 0.2, 0.48, 0.26, 0.16, 0.3, 0.2, 0.42, 0.24];
  const weatherItems = useMemo(() => buildWeatherItems(session), [session]);

  useEffect(() => {
    const handleAuthChange = (event: Event) => {
      const detail = (event as CustomEvent<{ state?: string; source?: unknown }>).detail;
      const source = detail?.source;
      favoriteMutationAbortRef.current?.abort();
      favoriteMutationAbortRef.current = null;
      favoriteAuthFailureRef.current = detail?.state === "anonymous"
        && source != null
        && source === favoriteMutationSourceRef.current
        ? { source: source as object, sessionId: displayedSessionIdRef.current }
        : null;
      favoriteLoadGenerationRef.current += 1;
      setFavoritePending(true);
      setAccountAuthRevision((revision) => revision + 1);
    };
    window.addEventListener(ACCOUNT_AUTH_CHANGED_EVENT, handleAuthChange);
    return () => window.removeEventListener(ACCOUNT_AUTH_CHANGED_EVENT, handleAuthChange);
  }, []);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const generation = favoriteLoadGenerationRef.current + 1;
    favoriteLoadGenerationRef.current = generation;
    const isCurrentLoad = () => active && favoriteLoadGenerationRef.current === generation;
    setIsFavorite(false);
    setFavoritePending(true);
    const preserveSignInRecovery = isAccountAuthenticationUnavailable()
      && favoriteAuthFailureRef.current?.sessionId === session.id;
    if (!preserveSignInRecovery) setFavoriteHint(null);
    if (isAccountAuthenticationUnavailable()) {
      setFavoritePending(false);
      return () => {
        active = false;
        controller.abort();
      };
    }
    void fetchFavorites(100, 0, controller.signal).then((favorites) => {
      if (isCurrentLoad()) setIsFavorite(favorites.some((favorite) => favorite.session.id === session.id));
    }).catch((error: unknown) => {
      if (isCurrentLoad() && !isApiError(error)) setFavoriteHint("Favorites are temporarily unavailable.");
    }).finally(() => {
      observeFavoriteContinuation("load");
      if (isCurrentLoad()) setFavoritePending(false);
    });
    return () => {
      active = false;
      controller.abort();
    };
  }, [accountAuthRevision, session.id]);

  const toggleFavorite = useCallback(async () => {
    const targetSessionId = session.id;
    const accountGeneration = favoriteLoadGenerationRef.current;
    const isCurrentMutation = () => (
      mountedRef.current
      && favoriteLoadGenerationRef.current === accountGeneration
      && displayedSessionIdRef.current === targetSessionId
    );
    const nextFavorite = !isFavorite;
    if (isAccountAuthenticationUnavailable()) {
      trackPlayerEvent("favorite_requires_login");
      setFavoriteHint("Sign in or create a free account to save favorites.");
      return;
    }
    const mutationSource = {};
    const controller = new AbortController();
    favoriteMutationAbortRef.current?.abort();
    favoriteMutationAbortRef.current = controller;
    favoriteAuthFailureRef.current = null;
    favoriteMutationSourceRef.current = mutationSource;
    setFavoritePending(true);
    try {
      if (nextFavorite) await addFavorite(targetSessionId, mutationSource, controller.signal);
      else await removeFavorite(targetSessionId, mutationSource, controller.signal);
      if (!isCurrentMutation()) return;
      if (nextFavorite) trackPlayerEvent("favorite_add");
      setIsFavorite(nextFavorite);
      setFavoriteHint(nextFavorite ? "Saved to your account." : "Removed from your account.");
    } catch (error) {
      const authFailure = favoriteAuthFailureRef.current as { source: object; sessionId: string } | null;
      const isOwnedAuthFailure = isApiError(error)
        && error.status === 401
        && authFailure?.source === mutationSource
        && authFailure.sessionId === targetSessionId;
      if (isCurrentMutation() || isOwnedAuthFailure) {
        if (isApiError(error) && error.status === 401) {
          trackPlayerEvent("favorite_requires_login");
          setFavoriteHint("Sign in or create a free account to save favorites.");
        } else {
          setFavoriteHint("Favorites are temporarily unavailable.");
        }
      }
    } finally {
      observeFavoriteContinuation("mutation");
      if (favoriteMutationAbortRef.current === controller) favoriteMutationAbortRef.current = null;
      if (isCurrentMutation()) setFavoritePending(false);
      if (favoriteMutationSourceRef.current === mutationSource) favoriteMutationSourceRef.current = null;
    }
  }, [isFavorite, session.id]);

  const secondsFromTimelineClientX = useCallback(
    (clientX: number) => {
      const timeline = timelineRef.current;
      if (!timeline) {
        return 0;
      }
      const rect = timeline.getBoundingClientRect();
      const trackStart = rect.left + (TIMELINE_TRACK_START / 100) * rect.width;
      const trackWidth = (TIMELINE_TRACK_WIDTH / 100) * rect.width;
      const ratio = Math.min(Math.max((clientX - trackStart) / trackWidth, 0), 1);
      return ratio * timelineDuration;
    },
    [timelineDuration],
  );

  const seekTimeline = useCallback(
    (seconds: number) => {
      const nextSeconds = Math.min(Math.max(seconds, 0), playbackDurationSeconds);
      setTimelineDraftSeconds(nextSeconds);

      if (!isCurrent || preparingTimelineSessionIdRef.current != null) {
        pendingTimelineSeekRef.current = { sessionId: session.id, seconds: nextSeconds };
        if (preparingTimelineSessionIdRef.current !== session.id) {
          const generation = timelineSeekGenerationRef.current + 1;
          timelineSeekGenerationRef.current = generation;
          preparingTimelineSessionIdRef.current = session.id;
          const targetSessionId = session.id;
          void play(session)
            .then(() => {
              const pending = pendingTimelineSeekRef.current;
              if (
                timelineSeekGenerationRef.current === generation
                && displayedSessionIdRef.current === targetSessionId
                && pending?.sessionId === targetSessionId
              ) {
                seek(pending.seconds);
              }
            })
            .finally(() => {
              if (timelineSeekGenerationRef.current !== generation) return;
              preparingTimelineSessionIdRef.current = null;
              pendingTimelineSeekRef.current = null;
              setTimelineDraftSeconds(null);
            });
        }
        return;
      }

      seek(nextSeconds);
    },
    [isCurrent, playbackDurationSeconds, play, seek, session],
  );

  const handleTimelinePointerDown = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      event.preventDefault();
      event.currentTarget.setPointerCapture(event.pointerId);
      seekTimeline(secondsFromTimelineClientX(event.clientX));
    },
    [secondsFromTimelineClientX, seekTimeline],
  );

  const handleTimelinePointerMove = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      if (!event.currentTarget.hasPointerCapture(event.pointerId)) {
        return;
      }
      seekTimeline(secondsFromTimelineClientX(event.clientX));
    },
    [secondsFromTimelineClientX, seekTimeline],
  );

  const handleTimelinePointerUp = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
      if (isCurrent && preparingTimelineSessionIdRef.current == null) {
        setTimelineDraftSeconds(null);
      }
      trackPlayerEvent("player_seek");
    },
    [isCurrent],
  );

  const handleTimelineKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      const stepSeconds = event.shiftKey ? 30 : 5;
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        seekTimeline(timelinePlayheadSeconds - stepSeconds);
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        seekTimeline(timelinePlayheadSeconds + stepSeconds);
      }
      if (event.key === "Home") {
        event.preventDefault();
        seekTimeline(0);
      }
      if (event.key === "End") {
        event.preventDefault();
        seekTimeline(playbackDurationSeconds);
      }
    },
    [playbackDurationSeconds, seekTimeline, timelinePlayheadSeconds],
  );

  return (
    <section className="session-listening-console" aria-label="Session player">
      <div className="session-scenic-listener">
        {session.photo_url ? (
          <Image
            className="session-field-photo"
            src={session.photo_url}
            alt={`Field view at ${session.location.name}`}
            width={1200}
            height={675}
            unoptimized
          />
        ) : (
          <div className="session-field-photo-placeholder" role="img" aria-label="No field photo available">
            No field photo available
          </div>
        )}
        {onClose ? (
          <button type="button" className="session-panel-back" aria-label="Hide player" onClick={() => { trackPlayerEvent("session_close"); onClose(); }}>
            ‹
          </button>
        ) : (
          <Link href="/atlas" className="session-panel-back" aria-label="Back to atlas">
            Back to atlas
          </Link>
        )}
        <span className="session-live-badge">Recording</span>
        <div className="session-scenic-copy">
          <h2>{session.location.name}</h2>
          <p>{formatCoordinates(session)}</p>
          <small>{session.location.habitat ?? session.weather ?? "field recording"}</small>
        </div>
        <dl className="session-weather-grid">
          {weatherItems.map((item) => (
            <div key={item.label}>
              <dt>{item.value}</dt>
              <dd>{item.label}</dd>
            </div>
          ))}
        </dl>
        <button
          type="button"
          className="session-listening-bar"
          onClick={isPlaying ? () => pause("session_overlay") : () => void play(session)}
        >
          <span aria-hidden="true" />
          <strong>{isPlaying ? "Listening" : displayedState === "requesting_grant" ? "Connecting" : "Listen"}</strong>
          <time>{formatDurationClock(session.duration_seconds ?? null)}</time>
        </button>
      </div>

      <div className="session-dawn-timeline" ref={timelineRef}>
        <div className="session-timeline-heading">
          <h2>Dawn Chorus</h2>
          <p>Timeline</p>
          <div className="session-timeline-help">
            <button
              type="button"
              aria-label="Timeline help"
              aria-expanded={timelineHelpOpen}
              aria-controls="timeline-help-copy"
              aria-describedby={timelineHelpOpen ? "timeline-help-copy" : undefined}
              onClick={() => setTimelineHelpOpen((open) => !open)}
            >?</button>
            {timelineHelpOpen ? (
              <p id="timeline-help-copy" role="tooltip">
                Each line marks a model-assisted candidate interval of detected bird activity.
                Select a line to seek; detections may require editorial review.
              </p>
            ) : null}
          </div>
        </div>
        <div className="session-timeline-ruler" aria-hidden="true">
          {timelineTicks.map((tick, index) => (
            <span key={`${tick}-${index}`}>{tick}</span>
          ))}
        </div>
        <div
          className="session-timeline-playhead"
          role="slider"
          tabIndex={0}
          aria-label="Playback position"
          aria-valuemin={0}
          aria-valuemax={Math.round(playbackDurationSeconds)}
          aria-valuenow={Math.round(timelinePlayheadSeconds)}
          aria-valuetext={formatDurationClock(timelinePlayheadSeconds)}
          style={{ left: `${timelinePlayheadLeft}%` }}
          onPointerDown={handleTimelinePointerDown}
          onPointerMove={handleTimelinePointerMove}
          onPointerUp={handleTimelinePointerUp}
          onPointerCancel={handleTimelinePointerUp}
          onKeyDown={handleTimelineKeyDown}
        />
        {birdTracks.length > 0 ? (
          <ol className="session-bird-timeline">
            {birdTracks.map((track) => {
              const isActiveTrack = isCurrent && track.parts.some((part) => (
                playbackCurrentSeconds >= part.starts_at_seconds
                && playbackCurrentSeconds <= part.ends_at_seconds
              ));
              return (
                <li key={track.key} className={isActiveTrack ? "is-active" : undefined}>
                  <span className="session-species-dot" aria-hidden="true" />
                  <strong>{track.label}</strong>
                  {track.parts.map((part) => (
                    <Fragment key={part.id}>
                      <button
                        type="button"
                        className="session-species-interval"
                        style={{
                          left: `${timelineLeft(part.starts_at_seconds, timelineDuration)}%`,
                          width: `${timelineWidth(part, timelineDuration)}%`,
                        }}
                        aria-label={`Seek to ${part.species_common_name} at ${formatOffset(part.starts_at_seconds)}`}
                        title={`${part.species_common_name}: ${formatOffset(part.starts_at_seconds)}-${formatOffset(
                          part.ends_at_seconds,
                        )}`}
                        onClick={() => {
                          trackPlayerEvent("timeline_species_click");
                          seekTimeline(part.starts_at_seconds);
                        }}
                      />
                      <em style={{ left: `${timelineLeft(part.ends_at_seconds, timelineDuration)}%` }} />
                    </Fragment>
                  ))}
                </li>
              );
            })}
          </ol>
        ) : (
          <p className="session-timeline-empty">Bird vocal parts will appear after analysis writes intervals to the database.</p>
        )}
        <div className="session-timeline-footer">
          <span>{formatOffset(timelinePlayheadSeconds)}</span>
          <strong>{birdTracks.length > 0 ? `${birdTracks.length} detected species` : "Awaiting analysis"}</strong>

        </div>
      </div>

      <div className="session-orbital-player">
        <button className="session-previous-button" type="button" aria-label="Previous recording" disabled={!onPrevious} onClick={() => { trackPlayerEvent("player_prev"); onPrevious?.(); }}>
          ‹
        </button>
        <div className="session-soundline" aria-hidden="true">
          {displayedWaveformPeaks.map((peak, index) => (
            <span key={`${peak}-${index}`} style={{ height: `${Math.max(4, peak * 28)}px` }} />
          ))}
        </div>
        <div className="session-seek-controls">
          <button type="button" aria-label="Back 30 seconds" disabled={!isCurrent} onClick={() => seek(Math.max(playbackCurrentSeconds - 30, 0))}>−30</button>
          <button type="button" aria-label="Forward 30 seconds" disabled={!isCurrent} onClick={() => seek(Math.min(playbackCurrentSeconds + 30, playbackDurationSeconds))}>+30</button>
        </div>
        <div className="session-core-shell" style={playbackProgressStyle}>
          <div
            className="session-orbit-progress"
            role="progressbar"
            aria-label="Playback progress"
            aria-valuemin={0}
            aria-valuemax={Math.round(playbackDurationSeconds)}
            aria-valuenow={Math.round(playbackCurrentSeconds)}
          >
            <i aria-hidden="true" />
          </div>
          <button
            type="button"
            className="session-player-core"
            onClick={isPlaying ? () => pause("session_overlay") : () => void play(session)}
            aria-label={isPlaying ? "Pause playback" : "Play session"}
          >
            <span className={isPlaying ? "is-playing" : ""} />
          </button>
        </div>
        <div className="session-soundline mirrored" aria-hidden="true">
          {displayedWaveformPeaks.map((peak, index) => (
            <span key={`${peak}-${index}`} style={{ height: `${Math.max(4, peak * 28)}px` }} />
          ))}
        </div>
        <button
          className="session-favorite-button"
          type="button"
          aria-label={isFavorite ? "Remove from favorites" : "Save recording"}
          aria-pressed={isFavorite}
          disabled={favoritePending}
          onClick={() => void toggleFavorite()}
        >
          {isFavorite ? "♥" : "♡"}
        </button>
        <div className="session-player-caption">
          <strong>{session.location.name}</strong>
          <span>
            {formatLocalTime(session.recorded_at, session.location.timezone)} · {isPlaying ? "Playing" : displayedState}
          </span>
          {grant && isCurrent ? <small>Grant expires {formatClockTime(grant.expires_at)}</small> : null}
          {error && isCurrent ? <small className="error-text" role="alert">{error}</small> : null}
          {favoriteHint ? (
            <small role="status">
              {favoriteHint}{" "}
              {favoriteHint.startsWith("Sign in") ? <Link href={`/membership?mode=login&returnTo=${encodeURIComponent(`/sessions/${session.slug}`)}`}>Sign in</Link> : null}
              {favoriteHint.startsWith("Saved") ? <Link href="/library">View your library</Link> : null}
            </small>
          ) : null}
        </div>
        <button className="session-next-button" type="button" aria-label="Next recording" disabled={!onNext} onClick={() => { trackPlayerEvent("player_next"); onNext?.(); }}>›</button>
      </div>
    </section>
  );
}
