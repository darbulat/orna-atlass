const assert = require("node:assert/strict");
const test = require("node:test");

const {
  refreshAuthentication,
} = require("../../.next-codex-unit/lib/api/auth-refresh.js");

test("a pre-aborted caller receives a rejected promise without starting refresh", async () => {
  const controller = new AbortController();
  controller.abort();
  let refreshCalls = 0;
  let result;

  assert.doesNotThrow(() => {
    result = refreshAuthentication(() => {
      refreshCalls += 1;
      return Promise.resolve();
    }, controller.signal);
  });
  assert.ok(result instanceof Promise);
  await assert.rejects(result, { name: "AbortError" });
  assert.equal(refreshCalls, 0);
});

test("a synchronous refresh failure becomes a rejected promise and releases the slot", async () => {
  let result;
  assert.doesNotThrow(() => {
    result = refreshAuthentication(() => {
      throw new Error("sync-refresh-failure");
    });
  });
  assert.ok(result instanceof Promise);
  await assert.rejects(result, { message: "sync-refresh-failure" });

  let recovered = false;
  await refreshAuthentication(() => {
    recovered = true;
    return Promise.resolve();
  });
  assert.equal(recovered, true);
});

test("an aborted caller stops waiting without cancelling the shared refresh", async () => {
  let refreshCalls = 0;
  let releaseRefresh;
  const sharedRefresh = new Promise((resolve) => {
    releaseRefresh = resolve;
  });
  const controller = new AbortController();

  const abortedCaller = refreshAuthentication(() => {
    refreshCalls += 1;
    return sharedRefresh;
  }, controller.signal);
  const activeCaller = refreshAuthentication(() => {
    refreshCalls += 1;
    return Promise.resolve();
  });

  controller.abort();
  const abortOutcome = await Promise.race([
    abortedCaller.then(() => "resolved", (error) => error?.name ?? "rejected"),
    new Promise((resolve) => setTimeout(() => resolve("still-pending"), 100)),
  ]);
  assert.equal(abortOutcome, "AbortError");
  assert.equal(refreshCalls, 1);

  let activeSettled = false;
  void activeCaller.then(() => {
    activeSettled = true;
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(activeSettled, false);

  releaseRefresh();
  await activeCaller;
  assert.equal(activeSettled, true);

  await refreshAuthentication(() => {
    refreshCalls += 1;
    return Promise.resolve();
  });
  assert.equal(refreshCalls, 2);
});
