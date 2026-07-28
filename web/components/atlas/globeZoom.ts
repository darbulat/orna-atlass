const wheelLineHeightPixels = 16;
const maximumWheelDeltaPixels = 240;
const wheelZoomSensitivity = 0.0025;

type WheelZoomBounds = {
  minimumHeight: number;
  maximumHeight: number;
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
