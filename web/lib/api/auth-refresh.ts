let refreshPromise: Promise<void> | null = null;
let refreshAbortController: AbortController | null = null;
let explicitAuthenticationTail: Promise<void> = Promise.resolve();
let pendingExplicitAuthentications = 0;

export class AccountAuthTransitionInProgressError extends Error {
  constructor() {
    super("Authentication changed before the refresh could start");
    this.name = "AccountAuthTransitionInProgressError";
  }
}

function abortReason(signal: AbortSignal): unknown {
  return signal.reason ?? new DOMException("The operation was aborted", "AbortError");
}

function settle(refresh: Promise<void>): Promise<void> {
  return refresh.then(
    () => undefined,
    () => undefined,
  );
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
  refresh: (signal: AbortSignal) => Promise<unknown>,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted) return Promise.reject(abortReason(signal));
  if (pendingExplicitAuthentications > 0) {
    return Promise.reject(new AccountAuthTransitionInProgressError());
  }
  if (!refreshPromise) {
    const controller = new AbortController();
    refreshAbortController = controller;
    const operation = Promise.resolve()
      .then(() => refresh(controller.signal))
      .then(() => undefined)
      .finally(() => {
        if (refreshPromise === operation) {
          refreshPromise = null;
          refreshAbortController = null;
        }
      });
    refreshPromise = operation;
  }
  return waitForRefresh(refreshPromise, signal);
}

export function drainAuthenticationRefresh(): Promise<void> {
  const activeRefresh = refreshPromise;
  return activeRefresh ? settle(activeRefresh) : Promise.resolve();
}

export function runExplicitAuthentication<T>(operation: () => Promise<T>): Promise<T> {
  pendingExplicitAuthentications += 1;
  const activeRefresh = refreshPromise;
  if (activeRefresh) refreshAbortController?.abort();
  const predecessor = explicitAuthenticationTail;
  const result = predecessor
    .then(() => (activeRefresh ? settle(activeRefresh) : undefined))
    .then(operation);
  explicitAuthenticationTail = result.then(
    () => undefined,
    () => undefined,
  );
  return result.finally(() => {
    pendingExplicitAuthentications -= 1;
  });
}
