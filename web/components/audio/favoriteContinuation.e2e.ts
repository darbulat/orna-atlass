type FavoriteContinuationKind = "load" | "mutation";

export function observeFavoriteContinuation(kind: FavoriteContinuationKind): void {
  window.dispatchEvent(new CustomEvent("orna:test:favorite-continuation", { detail: { kind } }));
}

export function observeLibraryMutationContinuation(): void {
  window.dispatchEvent(new CustomEvent("orna:test:library-mutation-continuation"));
}

export function observeListeningProgressContinuation(): void {
  window.dispatchEvent(new CustomEvent("orna:test:listening-progress-continuation"));
}