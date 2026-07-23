const assert = require("node:assert/strict");
const test = require("node:test");

const accountAuth = require("../../.next-codex-unit/lib/api/account-auth-state.js");

test("an overlapping failed auth boundary restores the last stable state", () => {
  accountAuth.markAccountAuthenticated();
  const firstBoundary = accountAuth.beginAccountAuthBoundary();
  const secondBoundary = accountAuth.beginAccountAuthBoundary();

  accountAuth.cancelAccountAuthBoundary(secondBoundary);
  accountAuth.completeAccountAuthBoundary(firstBoundary, "authenticated");

  assert.equal(accountAuth.isAccountAuthenticationTransitioning(), false);
  assert.equal(accountAuth.isAccountAuthenticationUnavailable(), false);
});

test("a failed queued login restores the earlier queued login result", () => {
  accountAuth.markAccountAnonymous();
  const firstBoundary = accountAuth.beginAccountAuthBoundary();
  const secondBoundary = accountAuth.beginAccountAuthBoundary();

  accountAuth.completeAccountAuthBoundary(firstBoundary, "authenticated");
  assert.equal(accountAuth.isAccountAuthenticationTransitioning(), true);
  accountAuth.cancelAccountAuthBoundary(secondBoundary);

  assert.equal(accountAuth.isAccountAuthenticationUnavailable(), false);
});

test("a failed queued writer preserves an earlier queued logout", () => {
  accountAuth.markAccountAuthenticated();
  const firstBoundary = accountAuth.beginAccountAuthBoundary();
  const secondBoundary = accountAuth.beginAccountAuthBoundary();

  accountAuth.completeAccountAuthBoundary(firstBoundary, "anonymous");
  assert.equal(accountAuth.isAccountAuthenticationTransitioning(), true);
  accountAuth.cancelAccountAuthBoundary(secondBoundary);

  assert.equal(accountAuth.isAccountAuthenticationUnavailable(), true);
});
