export const ACCOUNT_AUTH_CHANGED_EVENT = "orna:account-auth-changed";

type AccountAuthState = "unknown" | "transitioning" | "anonymous" | "authenticated";
type StableAccountAuthState = Exclude<AccountAuthState, "transitioning">;
export type AccountAuthBoundary = Readonly<{ epoch: number; previousState: StableAccountAuthState }>;

let accountAuthState: AccountAuthState = "unknown";
let lastStableAccountAuthState: StableAccountAuthState = "unknown";
let accountAuthEpoch = 0;

function setAccountAuthState(nextState: AccountAuthState, source?: unknown, forceBoundary = false): void {
  if (!forceBoundary && accountAuthState === nextState) return;
  if (!forceBoundary && accountAuthState === "unknown" && nextState === "authenticated") {
    accountAuthState = nextState;
    lastStableAccountAuthState = nextState;
    return;
  }
  accountAuthState = nextState;
  if (nextState !== "transitioning") lastStableAccountAuthState = nextState;
  accountAuthEpoch += 1;
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(ACCOUNT_AUTH_CHANGED_EVENT, {
      detail: { state: nextState, source, epoch: accountAuthEpoch },
    }));
  }
}

export function isAccountAuthenticationUnavailable(): boolean {
  return accountAuthState === "anonymous" || accountAuthState === "transitioning";
}

export function isAccountAuthenticationTransitioning(): boolean {
  return accountAuthState === "transitioning";
}

export function getAccountAuthEpoch(): number {
  return accountAuthEpoch;
}

export function beginAccountAuthBoundary(): AccountAuthBoundary {
  const previousState = lastStableAccountAuthState;
  setAccountAuthState("transitioning", undefined, true);
  return { epoch: accountAuthEpoch, previousState };
}

export function completeAccountAuthBoundary(
  boundary: AccountAuthBoundary,
  state: "anonymous" | "authenticated",
): void {
  lastStableAccountAuthState = state;
  if (accountAuthEpoch === boundary.epoch) setAccountAuthState(state, undefined, true);
}

export function cancelAccountAuthBoundary(boundary: AccountAuthBoundary): void {
  if (accountAuthEpoch === boundary.epoch) setAccountAuthState(lastStableAccountAuthState, undefined, true);
}

export function markAccountAuthenticated(source?: unknown): void {
  setAccountAuthState("authenticated", source);
}

export function markAccountAnonymous(source?: unknown): void {
  setAccountAuthState("anonymous", source);
}
