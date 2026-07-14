import type { PlaybackGrant, SessionDetail } from "../../lib/api/sessions";

export type PlaybackState =
  | "idle"
  | "requesting_grant"
  | "ready"
  | "playing"
  | "paused"
  | "refreshing_grant"
  | "stalled"
  | "ended"
  | "error";

export type PlayerState = {
  currentSession: SessionDetail | null;
  playbackState: PlaybackState;
  grant: PlaybackGrant | null;
  currentTimeSeconds: number;
  durationSeconds: number | null;
  error: string | null;
};

export type PlayerAction =
  | { type: "request_grant"; session: SessionDetail }
  | { type: "grant_ready"; sessionId: string; grant: PlaybackGrant }
  | { type: "refresh_started"; sessionId: string }
  | { type: "grant_refreshed"; sessionId: string; grant: PlaybackGrant; resumed: boolean }
  | { type: "playing" }
  | { type: "paused" }
  | { type: "stalled" }
  | { type: "ended"; currentTimeSeconds: number }
  | { type: "progress"; currentTimeSeconds: number; durationSeconds: number | null }
  | { type: "seek"; currentTimeSeconds: number; durationSeconds: number | null }
  | { type: "failed"; sessionId: string | null; message: string }
  | { type: "clear_error" };

export const initialPlayerState: PlayerState = {
  currentSession: null,
  playbackState: "idle",
  grant: null,
  currentTimeSeconds: 0,
  durationSeconds: null,
  error: null,
};

function isCurrentSession(state: PlayerState, sessionId: string): boolean {
  return state.currentSession?.id === sessionId;
}

export function playerReducer(state: PlayerState, action: PlayerAction): PlayerState {
  switch (action.type) {
    case "request_grant":
      return {
        currentSession: action.session,
        playbackState: "requesting_grant",
        grant: null,
        currentTimeSeconds: 0,
        durationSeconds: action.session.duration_seconds ?? null,
        error: null,
      };
    case "grant_ready":
      return isCurrentSession(state, action.sessionId)
        ? { ...state, grant: action.grant, playbackState: "ready", error: null }
        : state;
    case "refresh_started":
      return isCurrentSession(state, action.sessionId)
        ? { ...state, playbackState: "refreshing_grant", error: null }
        : state;
    case "grant_refreshed":
      return isCurrentSession(state, action.sessionId)
        ? {
            ...state,
            grant: action.grant,
            playbackState: action.resumed ? "playing" : "paused",
            error: null,
          }
        : state;
    case "playing":
      return { ...state, playbackState: "playing", error: null };
    case "paused":
      return { ...state, playbackState: "paused" };
    case "stalled":
      return { ...state, playbackState: "stalled" };
    case "ended":
      return { ...state, playbackState: "ended", currentTimeSeconds: action.currentTimeSeconds };
    case "progress":
      return {
        ...state,
        currentTimeSeconds: action.currentTimeSeconds,
        durationSeconds: action.durationSeconds,
      };
    case "seek":
      return {
        ...state,
        currentTimeSeconds: action.currentTimeSeconds,
        durationSeconds: action.durationSeconds,
        playbackState: state.playbackState === "ended" ? "paused" : state.playbackState,
      };
    case "failed":
      return action.sessionId === null || isCurrentSession(state, action.sessionId)
        ? { ...state, playbackState: "error", error: action.message }
        : state;
    case "clear_error":
      return { ...state, error: null };
    default:
      return state;
  }
}
