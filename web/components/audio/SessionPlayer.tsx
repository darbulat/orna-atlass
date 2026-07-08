"use client";

import Link from "next/link";
import { Fragment, useCallback, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent } from "react";
import type { BirdVocalPart, SessionDetail } from "../../lib/api/sessions";
import { usePlayer } from "./PlayerProvider";

const TIMELINE_TRACK_START = 34;
const TIMELINE_TRACK_WIDTH = 61;

type BirdTimelineTrack = {
  key: string;
  label: string;
  startsAt: number;
  endsAt: number;
  parts: BirdVocalPart[];
};

export function SessionPlayer({ session }: { session: SessionDetail }) {
  const { currentSession, playbackState, grant, currentTimeSeconds, durationSeconds, play, pause, seek, error } =
    usePlayer();
  const timelineRef = useRef<HTMLDivElement | null>(null);
  const pendingTimelineSeekRef = useRef<number | null>(null);
  const isPreparingTimelineSeekRef = useRef(false);
  const [timelineDraftSeconds, setTimelineDraftSeconds] = useState<number | null>(null);
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
  const waveformPeaks =
    session.waveform.peaks.length > 0
      ? session.waveform.peaks.slice(0, 52)
      : [0.12, 0.22, 0.18, 0.36, 0.2, 0.48, 0.26, 0.16, 0.3, 0.2, 0.42, 0.24];
  const weatherItems = useMemo(() => buildWeatherItems(session), [session]);

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

      if (!isCurrent || isPreparingTimelineSeekRef.current) {
        pendingTimelineSeekRef.current = nextSeconds;
        if (!isPreparingTimelineSeekRef.current) {
          isPreparingTimelineSeekRef.current = true;
          void play(session)
            .then(() => {
              const pendingSeconds = pendingTimelineSeekRef.current;
              if (pendingSeconds != null) {
                seek(pendingSeconds);
              }
            })
            .finally(() => {
              isPreparingTimelineSeekRef.current = false;
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
      if (isCurrent && !isPreparingTimelineSeekRef.current) {
        setTimelineDraftSeconds(null);
      }
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
        <Link href="/atlas" className="session-panel-back" aria-label="Back to atlas">
          ‹
        </Link>
        <LiveBadge />
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
          onClick={isPlaying ? pause : () => void play(session)}
        >
          <span aria-hidden="true" />
          <strong>{isPlaying ? "Listening" : displayedState === "requesting_grant" ? "Connecting" : "Listen"}</strong>
          <time>{formatDurationClock(session.duration_seconds)}</time>
        </button>
      </div>

      <div className="session-dawn-timeline" ref={timelineRef}>
        <div className="session-timeline-heading">
          <h2>Dawn Chorus</h2>
          <p>Timeline</p>
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
            {birdTracks.map((track) => (
              <li key={track.key}>
                <span aria-hidden="true">◢</span>
                <strong>{track.label}</strong>
                {track.parts.map((part) => (
                  <Fragment key={part.id}>
                    <i
                      style={{
                        left: `${timelineLeft(part.starts_at_seconds, timelineDuration)}%`,
                        width: `${timelineWidth(part, timelineDuration)}%`,
                      }}
                      title={`${part.species_common_name}: ${formatOffset(part.starts_at_seconds)}-${formatOffset(
                        part.ends_at_seconds,
                      )}`}
                    />
                    <em style={{ left: `${timelineLeft(part.ends_at_seconds, timelineDuration)}%` }} />
                  </Fragment>
                ))}
              </li>
            ))}
          </ol>
        ) : (
          <p className="session-timeline-empty">Bird vocal parts will appear after analysis writes intervals to the database.</p>
        )}
        <div className="session-timeline-footer">
          <span>{formatOffset(timelinePlayheadSeconds)}</span>
          <strong>{birdTracks.length > 0 ? `${birdTracks.length} detected species` : "Awaiting analysis"}</strong>
          <button type="button" aria-label="Timeline help">
            ?
          </button>
        </div>
      </div>

      <div className="session-orbital-player">
        <button type="button" aria-label="Previous recording">
          ‹
        </button>
        <div className="session-soundline" aria-hidden="true">
          {waveformPeaks.map((peak, index) => (
            <span key={`${peak}-${index}`} style={{ height: `${Math.max(4, peak * 28)}px` }} />
          ))}
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
            onClick={isPlaying ? pause : () => void play(session)}
            aria-label={isPlaying ? "Pause playback" : "Play session"}
          >
            <span className={isPlaying ? "is-playing" : ""} />
          </button>
        </div>
        <div className="session-soundline mirrored" aria-hidden="true">
          {waveformPeaks.map((peak, index) => (
            <span key={`${peak}-${index}`} style={{ height: `${Math.max(4, peak * 28)}px` }} />
          ))}
        </div>
        <button type="button" aria-label="Save recording">
          ♡
        </button>
        <div className="session-player-caption">
          <strong>{session.location.name}</strong>
          <span>
            {formatLocalTime(session.recorded_at, session.location.timezone)} · {isPlaying ? "Live" : displayedState}
          </span>
          {grant && isCurrent ? <small>Grant expires {formatClockTime(grant.expires_at)}</small> : null}
          {error && isCurrent ? <small className="error-text">{error}</small> : null}
        </div>
      </div>
    </section>
  );
}

function LiveBadge() {
  return (
    <span className="session-live-badge">
      Live
      <i aria-hidden="true" />
    </span>
  );
}

function formatCoordinates(session: SessionDetail) {
  const latitude = session.location.latitude;
  const longitude = session.location.longitude;
  if (latitude == null || longitude == null) {
    return session.location.coordinates_protected ? "Protected coordinates" : "Coordinates pending";
  }
  const latitudeSuffix = latitude >= 0 ? "N" : "S";
  const longitudeSuffix = longitude >= 0 ? "E" : "W";
  const coordinates = `${Math.abs(latitude).toFixed(3)}° ${latitudeSuffix}  ${Math.abs(longitude).toFixed(3)}° ${longitudeSuffix}`;
  return session.location.coordinates_protected ? `Approx. ${coordinates}` : coordinates;
}

function formatDurationClock(seconds: number | null) {
  const total = Math.max(seconds ?? 0, 0);
  const hours = Math.floor(total / 3600).toString().padStart(2, "0");
  const minutes = Math.floor((total % 3600) / 60).toString().padStart(2, "0");
  const remaining = Math.floor(total % 60).toString().padStart(2, "0");
  return `${hours}:${minutes}:${remaining}`;
}

function formatOffset(seconds: number) {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, "0");
  const remaining = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${remaining}`;
}

function timeFormatter(timeZone: string) {
  try {
    return new Intl.DateTimeFormat("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      timeZone,
    });
  } catch {
    return clockFormatter();
  }
}

function clockFormatter() {
  return new Intl.DateTimeFormat("en-US", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatLocalTime(value: string, timeZone: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--:--";
  }
  return timeFormatter(timeZone).format(date);
}

function formatClockTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--:--";
  }
  return clockFormatter().format(date);
}

function groupBirdPartsBySpecies(parts: BirdVocalPart[]): BirdTimelineTrack[] {
  const tracks = new Map<string, BirdTimelineTrack>();

  parts.forEach((part) => {
    const key = part.species_code || part.species_common_name;
    const existingTrack = tracks.get(key);
    if (existingTrack) {
      existingTrack.startsAt = Math.min(existingTrack.startsAt, part.starts_at_seconds);
      existingTrack.endsAt = Math.max(existingTrack.endsAt, part.ends_at_seconds);
      existingTrack.parts.push(part);
      return;
    }

    tracks.set(key, {
      key,
      label: part.species_common_name,
      startsAt: part.starts_at_seconds,
      endsAt: part.ends_at_seconds,
      parts: [part],
    });
  });

  return Array.from(tracks.values())
    .map((track) => ({
      ...track,
      parts: [...track.parts].sort((left, right) => left.starts_at_seconds - right.starts_at_seconds),
    }))
    .sort((left, right) => left.startsAt - right.startsAt || left.label.localeCompare(right.label));
}

type WeatherItem = { label: string; value: string };

function buildWeatherItems(session: SessionDetail): WeatherItem[] {
  const fallback = [
    { label: "conditions", value: session.weather?.trim() ? session.weather.trim() : "Unavailable" },
    { label: "habitat", value: session.location.habitat?.trim() ? session.location.habitat.trim() : "—" },
  ];

  return fallback;
}

function timelineTotalSeconds(session: SessionDetail) {
  const latestBirdPartEnd = Math.max(...(session.bird_parts?.parts.map((part) => part.ends_at_seconds) ?? [0]));
  return Math.max(session.duration_seconds ?? 0, latestBirdPartEnd, 1);
}

function timelineTickLabels(recordedAt: string, durationSeconds: number, timeZone: string) {
  const start = new Date(recordedAt);
  const tickCount = 6;
  const formatter = timeFormatter(timeZone);
  return Array.from({ length: tickCount }, (_, index) => {
    const offset = (durationSeconds / Math.max(tickCount - 1, 1)) * index;
    if (Number.isNaN(start.getTime())) {
      return formatOffset(offset);
    }
    return formatter.format(new Date(start.getTime() + offset * 1000));
  });
}

function timelineLeft(seconds: number, totalSeconds: number) {
  const ratio = Math.min(Math.max(seconds / totalSeconds, 0), 1);
  return TIMELINE_TRACK_START + ratio * TIMELINE_TRACK_WIDTH;
}

function timelineWidth(part: BirdVocalPart, totalSeconds: number) {
  return timelineRangeWidth(part.starts_at_seconds, part.ends_at_seconds, totalSeconds);
}

function timelineRangeWidth(startsAtSeconds: number, endsAtSeconds: number, totalSeconds: number) {
  const duration = Math.max(endsAtSeconds - startsAtSeconds, 0);
  return Math.max((duration / totalSeconds) * TIMELINE_TRACK_WIDTH, 1.5);
}
