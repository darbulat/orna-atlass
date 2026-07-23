const assert = require("node:assert/strict");
const test = require("node:test");

const {
  canDrainListeningProgress,
} = require("../../.next-codex-unit/components/audio/listeningProgress.js");

test("an unmounted provider cannot drain queued listening progress", () => {
  assert.equal(canDrainListeningProgress(4, 5, false), false);
});

test("only the currently mounted provider generation can drain progress", () => {
  assert.equal(canDrainListeningProgress(4, 5, true), false);
  assert.equal(canDrainListeningProgress(5, 5, true), true);
});
