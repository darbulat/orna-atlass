const assert = require("node:assert/strict");
const test = require("node:test");

const accountAuth = require("../../.next-codex-unit/lib/api/account-auth-state.js");
const auth = require("../../.next-codex-unit/lib/api/auth.js");

test("a stale current-user success cannot interrupt an explicit auth boundary", async () => {
  let releaseCurrentUser;
  const originalFetch = global.fetch;
  global.fetch = () => new Promise((resolve) => {
    releaseCurrentUser = resolve;
  });

  try {
    const currentUser = auth.fetchCurrentUser();
    await Promise.resolve();
    const boundary = accountAuth.beginAccountAuthBoundary();
    releaseCurrentUser(new Response(JSON.stringify({
      id: "old-account",
      email: "old@example.com",
      role: "member",
    }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));

    await assert.rejects(currentUser, (error) => error?.name === "AbortError");
    assert.equal(accountAuth.isAccountAuthenticationTransitioning(), true);
    assert.equal(accountAuth.getAccountAuthEpoch(), boundary.epoch);

    accountAuth.completeAccountAuthBoundary(boundary, "authenticated");
    assert.equal(accountAuth.isAccountAuthenticationTransitioning(), false);
    assert.equal(accountAuth.getAccountAuthEpoch(), boundary.epoch + 1);
  } finally {
    global.fetch = originalFetch;
  }
});
