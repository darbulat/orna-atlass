const assert = require("node:assert/strict");
const test = require("node:test");

const {
  AccountAuthTransitionInProgressError,
  refreshAuthentication,
  runExplicitAuthentication,
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

test("an explicit auth boundary aborts a hung refresh before sending credentials", async () => {
  let refreshAborted = false;
  const refresh = refreshAuthentication((signal) => new Promise((resolve, reject) => {
    const rejectAbort = () => {
      refreshAborted = true;
      reject(signal.reason ?? new DOMException("The operation was aborted", "AbortError"));
    };
    if (signal.aborted) {
      rejectAbort();
      return;
    }
    signal.addEventListener("abort", rejectAbort, { once: true });
  }));
  let authStarted = false;
  const authRequest = runExplicitAuthentication(async () => {
    authStarted = true;
  });

  const refreshError = await refresh.then(() => null, (error) => error);
  await authRequest;
  assert.equal(refreshAborted, true);
  assert.equal(refreshError?.name, "AbortError");
  assert.equal(authStarted, true);
});

test("a refresh cannot start after an explicit auth boundary", async () => {
  let releaseAuth;
  const authMaySettle = new Promise((resolve) => {
    releaseAuth = resolve;
  });
  const authRequest = runExplicitAuthentication(() => authMaySettle);
  await new Promise((resolve) => setImmediate(resolve));

  let refreshCalls = 0;
  await assert.rejects(
    refreshAuthentication(() => {
      refreshCalls += 1;
      return Promise.resolve();
    }),
    AccountAuthTransitionInProgressError,
  );
  assert.equal(refreshCalls, 0);

  releaseAuth();
  await authRequest;
  await refreshAuthentication(() => {
    refreshCalls += 1;
    return Promise.resolve();
  });
  assert.equal(refreshCalls, 1);
});

test("overlapping explicit auth requests install cookies in invocation order", async () => {
  let releaseFirst;
  const firstMaySettle = new Promise((resolve) => {
    releaseFirst = resolve;
  });
  const order = [];
  const first = runExplicitAuthentication(async () => {
    order.push("first-started");
    await firstMaySettle;
    order.push("first-settled");
  });
  const second = runExplicitAuthentication(async () => {
    order.push("second-started");
  });

  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(order, ["first-started"]);
  releaseFirst();
  await Promise.all([first, second]);
  assert.deepEqual(order, ["first-started", "first-settled", "second-started"]);
});
