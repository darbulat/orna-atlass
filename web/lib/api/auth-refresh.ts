let refreshPromise: Promise<void> | null = null;

function abortReason(signal: AbortSignal): unknown {
  return signal.reason ?? new DOMException("The operation was aborted", "AbortError");
}

function waitForRefresh(refresh: Promise<void>, signal?: AbortSignal): Promise<void> {
  if (!signal) return refresh;
  if (signal.aborted) return Promise.reject(abortReason(signal));

  return new Promise<void>((resolve, reject) => {
    const onAbort = () => {
      cleanup();
      reject(abortReason(signal));
    };
    const cleanup = () => signal.removeEventListener("abort", onAbort);

    signal.addEventListener("abort", onAbort, { once: true });
    if (signal.aborted) onAbort();
    refresh.then(
      () => {
        cleanup();
        resolve();
      },
      (error) => {
        cleanup();
        reject(error);
      },
    );
  });
}

export function refreshAuthentication(
  refresh: () => Promise<unknown>,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted) return Promise.reject(abortReason(signal));
  if (!refreshPromise) {
    refreshPromise = Promise.resolve().then(refresh).then(() => undefined).finally(() => {
      refreshPromise = null;
    });
  }
  return waitForRefresh(refreshPromise, signal);
}
