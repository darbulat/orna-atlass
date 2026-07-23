export function canDrainListeningProgress(
  ownerGeneration: number,
  currentGeneration: number,
  mounted: boolean,
): boolean {
  return mounted && ownerGeneration === currentGeneration;
}
