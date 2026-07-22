export const ACCOUNT_AUTH_CHANGED_EVENT = "orna:account-auth-changed";

type AccountAuthState = "unknown" | "anonymous" | "authenticated";

let accountAuthState: AccountAuthState = "unknown";

function setAccountAuthState(next: AccountAuthState) {
  if (accountAuthState === next) return;
  accountAuthState = next;
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(ACCOUNT_AUTH_CHANGED_EVENT, { detail: { state: next } }));
  }
}

export function isAccountAuthenticationUnavailable(): boolean {
  return accountAuthState === "anonymous";
}

export function markAccountAuthenticated(): void {
  setAccountAuthState("authenticated");
}

export function markAccountAnonymous(): void {
  setAccountAuthState("anonymous");
}
