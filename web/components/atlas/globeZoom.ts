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
