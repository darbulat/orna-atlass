const assert = require("node:assert/strict");
const test = require("node:test");

const {
  accumulateWheelZoomHeight,
  centeredZoomScale,
  clampZoomScaleToActualBounds,
  normalizeWheelDelta,
  scalePositionFromGlobeCenter,
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

test("centered wheel zoom changes distance without changing the camera ray", () => {
  const position = { x: 12_000_000, y: -8_000_000, z: 16_000_000 };
  const magnitude = Math.hypot(position.x, position.y, position.z);
  const scale = centeredZoomScale(magnitude, 16_000_000, 8_000_000);
  const destination = scalePositionFromGlobeCenter(position, scale);

  assert.ok(scale > 0 && scale < 1);
  assert.equal(destination.x / position.x, scale);
  assert.equal(destination.y / position.y, scale);
  assert.equal(destination.z / position.z, scale);
  assert.equal(centeredZoomScale(Number.NaN, 16_000_000, 8_000_000), 1);
});

test("an accumulated centered zoom clamps the destination's actual height", () => {
  const radius = 6_371_000;
  const currentHeight = 16_000_000;
  const bounds = { minimumHeight: 350_000, maximumHeight: 52_000_000 };
  const cameraMagnitude = radius + currentHeight;
  const actualHeightAtScale = (scale) => cameraMagnitude * scale - radius;
  const targetHeight = Array.from({ length: 20 }, () => -240).reduce(
    (height, delta) => accumulateWheelZoomHeight(height, delta, bounds),
    currentHeight,
  );
  const requestedScale = centeredZoomScale(cameraMagnitude, currentHeight, targetHeight);

  assert.ok(Math.abs(actualHeightAtScale(requestedScale) - bounds.minimumHeight) < 0.001);
  const boundedScale = clampZoomScaleToActualBounds(requestedScale, actualHeightAtScale, bounds);
  assert.ok(actualHeightAtScale(boundedScale) >= bounds.minimumHeight);
  assert.ok(actualHeightAtScale(boundedScale) < bounds.minimumHeight + 1);

  const outwardTargetHeight = Array.from({ length: 20 }, () => 240).reduce(
    (height, delta) => accumulateWheelZoomHeight(height, delta, bounds),
    currentHeight,
  );
  const outwardScale = centeredZoomScale(cameraMagnitude, currentHeight, outwardTargetHeight);
  assert.ok(Math.abs(actualHeightAtScale(outwardScale) - bounds.maximumHeight) < 0.001);
  const boundedOutwardScale = clampZoomScaleToActualBounds(outwardScale, actualHeightAtScale, bounds);
  assert.ok(actualHeightAtScale(boundedOutwardScale) <= bounds.maximumHeight);
  assert.ok(actualHeightAtScale(boundedOutwardScale) > bounds.maximumHeight - 1);
});
