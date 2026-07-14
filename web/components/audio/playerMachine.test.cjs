const assert = require("node:assert/strict");
const test = require("node:test");

const {
  initialPlayerState,
  playerReducer,
} = require("../../.next-codex-unit/components/audio/playerMachine.js");
const {
  disposePlayerResources,
} = require("../../.next-codex-unit/components/audio/playerResources.js");

const firstSession = {
  id: "session-1",
  slug: "first",
  title: "First",
  duration_seconds: 120,
};
const secondSession = {
  id: "session-2",
  slug: "second",
  title: "Second",
  duration_seconds: 240,
};
const firstGrant = {
  session_id: firstSession.id,
  status: "ready",
  stream_url: "/first.mp3",
  expires_at: "2030-01-01T00:00:00Z",
  refresh_after_seconds: 60,
};

test("grant transitions are scoped to the selected session", () => {
  const requesting = playerReducer(initialPlayerState, { type: "request_grant", session: firstSession });
  assert.equal(requesting.playbackState, "requesting_grant");
  assert.equal(requesting.durationSeconds, 120);

  const stale = playerReducer(requesting, {
    type: "grant_ready",
    sessionId: secondSession.id,
    grant: { ...firstGrant, session_id: secondSession.id },
  });
  assert.strictEqual(stale, requesting);

  const ready = playerReducer(requesting, {
    type: "grant_ready",
    sessionId: firstSession.id,
    grant: firstGrant,
  });
  assert.equal(ready.playbackState, "ready");
  assert.equal(ready.grant?.stream_url, "/first.mp3");
  assert.equal(playerReducer(ready, { type: "playing" }).playbackState, "playing");
});

test("grant refresh preserves progress and records whether playback resumed", () => {
  let state = playerReducer(initialPlayerState, { type: "request_grant", session: firstSession });
  state = playerReducer(state, { type: "grant_ready", sessionId: firstSession.id, grant: firstGrant });
  state = playerReducer(state, { type: "progress", currentTimeSeconds: 37, durationSeconds: 120 });
  state = playerReducer(state, { type: "refresh_started", sessionId: firstSession.id });
  assert.equal(state.playbackState, "refreshing_grant");

  state = playerReducer(state, {
    type: "grant_refreshed",
    sessionId: firstSession.id,
    grant: { ...firstGrant, stream_url: "/refreshed.mp3" },
    resumed: true,
  });
  assert.equal(state.playbackState, "playing");
  assert.equal(state.currentTimeSeconds, 37);
  assert.equal(state.grant?.stream_url, "/refreshed.mp3");
});

test("seeking from ended moves to paused and stale errors are ignored", () => {
  let state = playerReducer(initialPlayerState, { type: "request_grant", session: firstSession });
  state = playerReducer(state, { type: "ended", currentTimeSeconds: 120 });
  state = playerReducer(state, { type: "seek", currentTimeSeconds: 15, durationSeconds: 120 });
  assert.equal(state.playbackState, "paused");
  assert.equal(state.currentTimeSeconds, 15);

  const stale = playerReducer(state, { type: "failed", sessionId: secondSession.id, message: "stale" });
  assert.strictEqual(stale, state);
  const failed = playerReducer(state, { type: "failed", sessionId: firstSession.id, message: "unavailable" });
  assert.equal(failed.playbackState, "error");
  assert.equal(failed.error, "unavailable");
});

test("disposing the player clears its timer, aborts its request, and detaches audio", () => {
  const controller = new AbortController();
  const cleared = [];
  const calls = [];
  const audio = {
    ontimeupdate: () => undefined,
    onloadedmetadata: () => undefined,
    ondurationchange: () => undefined,
    onended: () => undefined,
    onerror: () => undefined,
    onstalled: () => undefined,
    pause: () => calls.push("pause"),
    removeAttribute: (name) => calls.push(`remove:${name}`),
    load: () => calls.push("load"),
  };

  disposePlayerResources({
    audio,
    abortController: controller,
    refreshTimerId: 42,
    clearTimer: (timerId) => cleared.push(timerId),
  });

  assert.deepEqual(cleared, [42]);
  assert.equal(controller.signal.aborted, true);
  assert.deepEqual(calls, ["pause", "remove:src", "load"]);
  assert.equal(audio.onerror, null);
  assert.equal(audio.ontimeupdate, null);
});
