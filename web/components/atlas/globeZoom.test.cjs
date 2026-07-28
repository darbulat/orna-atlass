const assert = require("node:assert/strict");
const test = require("node:test");

const {
  accumulateWheelZoomHeight,
  normalizeWheelDelta,
} = require("../../.next-codex-unit/components/atlas/globeZoom.js");

test("trackpad wheel deltas accumulate against the pending target height", () => {
  const options = { minimumHeight: 350_000, maximumHeight: 52_000_000 };
  const afterOneEvent = accumulateWheelZoomHeight(16_000_000, -20, options);
  const afterFourEvents = [-20, -20, -20, -20].reduce(
    (height, delta) => accumulateWheelZoomHeight(height, delta, options),
    16_000_000,
  );

  assert.ok(afterOneEvent < 16_000_000);
  assert.ok(afterFourEvents < afterOneEvent);
});

test("wheel delta modes normalize to CSS pixels", () => {
  assert.equal(normalizeWheelDelta(32, 0, 800), 32);
  assert.equal(normalizeWheelDelta(2, 1, 800), 32);
  assert.equal(normalizeWheelDelta(0.5, 2, 800), 400);
});

test("wheel zoom target stays within the configured camera bounds", () => {
  const options = { minimumHeight: 350_000, maximumHeight: 52_000_000 };

  assert.equal(accumulateWheelZoomHeight(360_000, -10_000, options), options.minimumHeight);
  assert.equal(accumulateWheelZoomHeight(51_000_000, 10_000, options), options.maximumHeight);
});
