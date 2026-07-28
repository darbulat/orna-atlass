const wheelLineHeightPixels = 16;
const maximumWheelDeltaPixels = 240;
const wheelZoomSensitivity = 0.0025;

type WheelZoomBounds = {
  minimumHeight: number;
  maximumHeight: number;
};

type CartesianPosition = {
  x: number;
  y: number;
  z: number;
};

type CartographicPosition = {
  longitude: number;
  latitude: number;
  height: number;
};

export function normalizeWheelDelta(deltaY: number, deltaMode: number, pageHeight: number): number {
  if (deltaMode === 1) return deltaY * wheelLineHeightPixels;
  if (deltaMode === 2) return deltaY * pageHeight;
  return deltaY;
}

export function accumulateWheelZoomHeight(
  targetHeight: number,
  deltaPixels: number,
  bounds: WheelZoomBounds,
): number {
  const boundedDelta = Math.max(-maximumWheelDeltaPixels, Math.min(maximumWheelDeltaPixels, deltaPixels));
  const nextHeight = targetHeight * Math.exp(boundedDelta * wheelZoomSensitivity);
  return Math.max(bounds.minimumHeight, Math.min(bounds.maximumHeight, nextHeight));
}

export function centeredZoomScale(
  cameraMagnitude: number,
  currentHeight: number,
  targetHeight: number,
): number {
  if (!Number.isFinite(cameraMagnitude) || cameraMagnitude <= 0) return 1;
  const surfaceDistance = cameraMagnitude - currentHeight;
  return (surfaceDistance + targetHeight) / cameraMagnitude;
}

export function scalePositionFromGlobeCenter(
  position: CartesianPosition,
  scale: number,
): CartesianPosition {
  return {
    x: position.x * scale,
    y: position.y * scale,
    z: position.z * scale,
  };
}

export function clampPositionToHeightBounds(
  position: CartesianPosition,
  bounds: WheelZoomBounds,
  toCartographic: (position: CartesianPosition) => CartographicPosition | null | undefined,
  toCartesian: (position: CartographicPosition) => CartesianPosition,
): CartesianPosition {
  const cartographic = toCartographic(position);
  if (
    !cartographic
    || !Number.isFinite(cartographic.longitude)
    || !Number.isFinite(cartographic.latitude)
    || !Number.isFinite(cartographic.height)
  ) return { ...position };

  const boundedHeight = Math.max(
    bounds.minimumHeight,
    Math.min(bounds.maximumHeight, cartographic.height),
  );
  if (boundedHeight === cartographic.height) return { ...position };
  return toCartesian({ ...cartographic, height: boundedHeight });
}

export function cursorAnchoredRotationFraction(
  cameraDistance: number,
  targetDistance: number,
  targetAngle: number,
  nextCameraDistance: number,
): number {
  if (
    !Number.isFinite(cameraDistance)
    || !Number.isFinite(targetDistance)
    || !Number.isFinite(targetAngle)
    || !Number.isFinite(nextCameraDistance)
    || cameraDistance <= targetDistance
    || nextCameraDistance <= targetDistance
    || nextCameraDistance >= cameraDistance
    || targetAngle <= 0
  ) return 0;

  const currentProjection = targetDistance * Math.sin(targetAngle)
    / (cameraDistance - targetDistance * Math.cos(targetAngle));
  if (!Number.isFinite(currentProjection) || currentProjection <= 0) return 0;

  let lowerAngle = 0;
  let upperAngle = targetAngle;
  for (let iteration = 0; iteration < 32; iteration += 1) {
    const candidateAngle = (lowerAngle + upperAngle) / 2;
    const candidateProjection = targetDistance * Math.sin(candidateAngle)
      / (nextCameraDistance - targetDistance * Math.cos(candidateAngle));
    if (!Number.isFinite(candidateProjection) || candidateProjection > currentProjection) {
      upperAngle = candidateAngle;
    } else {
      lowerAngle = candidateAngle;
    }
  }

  const nextAngle = (lowerAngle + upperAngle) / 2;
  return Math.max(0, Math.min(1, 1 - nextAngle / targetAngle));
}

export function rotatePositionTowardTarget(
  position: CartesianPosition,
  target: CartesianPosition,
  fraction: number,
): CartesianPosition {
  const positionMagnitude = Math.hypot(position.x, position.y, position.z);
  const targetMagnitude = Math.hypot(target.x, target.y, target.z);
  if (
    !Number.isFinite(positionMagnitude)
    || !Number.isFinite(targetMagnitude)
    || positionMagnitude <= 0
    || targetMagnitude <= 0
    || fraction <= 0
  ) return { ...position };

  const boundedFraction = Math.min(1, fraction);
  const positionDirection = {
    x: position.x / positionMagnitude,
    y: position.y / positionMagnitude,
    z: position.z / positionMagnitude,
  };
  const targetDirection = {
    x: target.x / targetMagnitude,
    y: target.y / targetMagnitude,
    z: target.z / targetMagnitude,
  };
  const dot = Math.min(1, Math.max(-1,
    positionDirection.x * targetDirection.x
    + positionDirection.y * targetDirection.y
    + positionDirection.z * targetDirection.z,
  ));
  const angle = Math.acos(dot);
  const sine = Math.sin(angle);
  if (angle < 1e-12 || Math.abs(sine) < 1e-12) return { ...position };

  const positionWeight = Math.sin((1 - boundedFraction) * angle) / sine;
  const targetWeight = Math.sin(boundedFraction * angle) / sine;
  return {
    x: (positionDirection.x * positionWeight + targetDirection.x * targetWeight) * positionMagnitude,
    y: (positionDirection.y * positionWeight + targetDirection.y * targetWeight) * positionMagnitude,
    z: (positionDirection.z * positionWeight + targetDirection.z * targetWeight) * positionMagnitude,
  };
}

export function clampZoomScaleToActualBounds(
  requestedScale: number,
  actualHeightAtScale: (scale: number) => number,
  bounds: WheelZoomBounds,
): number {
  const requestedHeight = actualHeightAtScale(requestedScale);
  if (!Number.isFinite(requestedHeight)) return 1;
  if (requestedHeight >= bounds.minimumHeight && requestedHeight <= bounds.maximumHeight) {
    return requestedScale;
  }

  const isBelowMinimum = requestedHeight < bounds.minimumHeight;
  let safeScale = 1;
  let unsafeScale = requestedScale;
  for (let iteration = 0; iteration < 32; iteration += 1) {
    const candidateScale = (safeScale + unsafeScale) / 2;
    const candidateHeight = actualHeightAtScale(candidateScale);
    const violatesBound = !Number.isFinite(candidateHeight)
      || (isBelowMinimum
        ? candidateHeight < bounds.minimumHeight
        : candidateHeight > bounds.maximumHeight);
    if (violatesBound) unsafeScale = candidateScale;
    else safeScale = candidateScale;
  }
  return safeScale;
}
