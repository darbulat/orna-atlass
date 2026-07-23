export type FavoriteContinuationKind = "load" | "mutation";

export function observeFavoriteContinuation(_kind: FavoriteContinuationKind): void {}

export function observeLibraryMutationContinuation(): void {}

export function observeListeningProgressContinuation(): void {}