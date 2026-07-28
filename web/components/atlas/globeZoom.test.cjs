const assert = require("node:assert/strict");
const test = require("node:test");

const {
  accumulateWheelZoomHeight,
  clampZoomScaleToActualBounds,
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

test("an accumulated edge-of-globe zoom clamps the destination's actual height", () => {
  const radius = 6_371_000;
  const currentHeight = 16_000_000;
  const bounds = { minimumHeight: 350_000, maximumHeight: 52_000_000 };
  const camera = { x: radius + currentHeight, y: 0 };
  const tangentAngle = Math.acos(radius / (radius + currentHeight));
  const cursorTarget = {
    x: radius * Math.cos(tangentAngle),
    y: radius * Math.sin(tangentAngle),
  };
  const fromTarget = {
    x: camera.x - cursorTarget.x,
    y: camera.y - cursorTarget.y,
  };
  const actualHeightAtScale = (scale) => Math.hypot(
    cursorTarget.x + fromTarget.x * scale,
    cursorTarget.y + fromTarget.y * scale,
  ) - radius;
  const targetHeight = Array.from({ length: 20 }, () => -240).reduce(
    (height, delta) => accumulateWheelZoomHeight(height, delta, bounds),
    currentHeight,
  );
  const requestedScale = targetHeight / currentHeight;

  assert.ok(actualHeightAtScale(requestedScale) < bounds.minimumHeight);
  const boundedScale = clampZoomScaleToActualBounds(requestedScale, actualHeightAtScale, bounds);
  assert.ok(actualHeightAtScale(boundedScale) >= bounds.minimumHeight);
  assert.ok(actualHeightAtScale(boundedScale) < bounds.minimumHeight + 1);

  const outwardTargetHeight = Array.from({ length: 20 }, () => 240).reduce(
    (height, delta) => accumulateWheelZoomHeight(height, delta, bounds),
    currentHeight,
  );
  const outwardScale = outwardTargetHeight / currentHeight;
  assert.ok(actualHeightAtScale(outwardScale) > bounds.maximumHeight);
  const boundedOutwardScale = clampZoomScaleToActualBounds(outwardScale, actualHeightAtScale, bounds);
  assert.ok(actualHeightAtScale(boundedOutwardScale) <= bounds.maximumHeight);
  assert.ok(actualHeightAtScale(boundedOutwardScale) > bounds.maximumHeight - 1);
});
