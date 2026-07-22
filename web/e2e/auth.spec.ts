import { expect, test } from "@playwright/test";


test("auth screen presents email and all configured social entry points", async ({ page }) => {
  await page.goto("/membership");

  await expect(page.getByRole("heading", {
    level: 1,
    name: "Sign in or create your account",
  })).toBeVisible();
  await expect(page.getByLabel("Email address", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Password", { exact: true })).toBeVisible();
  await expect(page.locator("form").getByRole("button", { name: "Continue" })).toBeVisible();

  const social = page.getByRole("group", { name: "Continue with a social account" });
  await expect(social.getByRole("link", { name: "Continue with Google" })).toHaveAttribute(
    "href",
    /\/api\/v1\/auth\/oauth\/google\/start\?return_to=%2Fmembership/,
  );
  await expect(social.getByRole("link", { name: "Continue with Apple" })).toHaveAttribute(
    "href",
    /\/api\/v1\/auth\/oauth\/apple\/start\?return_to=%2Fmembership/,
  );
  await expect(social.getByRole("link", { name: "Continue with Facebook" })).toHaveAttribute(
    "href",
    /\/api\/v1\/auth\/oauth\/facebook\/start\?return_to=%2Fmembership/,
  );
  const legalNotice = page.locator(".auth-legal");
  await expect(legalNotice.getByRole("link", { name: "Terms of Use" })).toHaveAttribute("href", "/terms");
  await expect(legalNotice.getByRole("link", { name: "Privacy Policy" })).toHaveAttribute("href", "/privacy");
});


test("auth screen only presents OAuth providers reported by the API", async ({ page }) => {
  await page.route("**/api/v1/auth/oauth/providers", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ providers: ["google"] }),
    });
  });
  await page.goto("/membership");

  await expect(page.getByRole("link", { name: "Continue with Google" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Continue with Apple" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Continue with Facebook" })).toHaveCount(0);
});


test("auth screen fails closed for malformed OAuth provider responses", async ({ page }) => {
  await page.route("**/api/v1/auth/oauth/providers", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ providers: "google" }),
    });
  });
  await page.goto("/membership");

  await expect(page.getByRole("link", { name: /Continue with/ })).toHaveCount(0);
  await expect(page.getByText("Social sign-in is temporarily unavailable.")).toBeVisible();
});


test("auth screen keeps the reference layout usable on a narrow phone", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 700 });
  await page.goto("/membership?mode=register");

  await expect(page.getByRole("button", { name: "Create account", pressed: true })).toBeVisible();
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("minlength", "12");
  const metrics = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    cardWidth: document.querySelector<HTMLElement>(".auth-card")?.getBoundingClientRect().width,
  }));
  expect(metrics.scrollWidth).toBe(metrics.viewport);
  expect(metrics.cardWidth).toBeLessThanOrEqual(320);
});


test("OAuth callback outcome is announced without exposing provider data", async ({ page }) => {
  await page.goto("/membership?oauth=error&oauth_provider=google&oauth_error=cancelled");
  await expect(page.locator("main").getByRole("alert")).toContainText("Google sign-in was cancelled");

  await page.goto("/membership?oauth=success&oauth_provider=apple");
  await expect(page.getByRole("alert").filter({ hasText: "Apple sign-in could not be confirmed" })).toBeVisible();
  await expect(page).toHaveURL(/\/membership$/);

  await page.goto("/membership?oauth=error&oauth_provider=google&oauth_error=account_conflict");
  await expect(page.locator("main .auth-notice").filter({ hasText: "original sign-in method" })).toBeVisible();
  await expect(page).toHaveURL(/\/membership$/);
});


test("OAuth success is only announced after the authenticated account is confirmed", async ({ page }) => {
  await page.route("**/api/v1/users/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "50000000-0000-4000-8000-000000000001",
        email: "member@example.com",
        role: "member",
        is_active: true,
        created_at: "2026-07-19T00:00:00Z",
      }),
    });
  });
  await page.route("**/api/v1/memberships/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ plan: "early_access", status: "active", is_entitled: true }),
    });
  });
  await page.goto("/membership?oauth=success&oauth_provider=google");

  await expect(page.getByRole("heading", { name: "Your account" })).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "Signed in with Google" })).toBeVisible();
  await expect(page).toHaveURL(/\/membership$/);
});


test("OAuth success survives a membership status outage", async ({ page }) => {
  await page.route("**/api/v1/auth/logout", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "logged_out" }),
    });
  });
  await page.route("**/api/v1/users/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "50000000-0000-4000-8000-000000000001",
        email: "member@example.com",
        role: "member",
        is_active: true,
        created_at: "2026-07-19T00:00:00Z",
      }),
    });
  });
  await page.route("**/api/v1/memberships/me", async (route) => {
    await route.fulfill({ status: 503, contentType: "application/json", body: "{}" });
  });
  await page.goto("/membership?oauth=success&oauth_provider=google");

  await expect(page.getByRole("heading", { name: "Your account" })).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "Signed in with Google" })).toBeVisible();
  await expect(page.locator("main .auth-notice").filter({ hasText: "temporarily unavailable" })).toBeVisible();
  await expect(page.getByText("Plan", { exact: true }).locator("..")).toContainText("Unavailable");
  await expect(page.getByText("Status", { exact: true }).locator("..")).toContainText("Unavailable");
  await expect(page.getByText("Playback", { exact: true }).locator("..")).toContainText("Unavailable");
  await expect(page.getByText("Plan", { exact: true }).locator("..")).not.toContainText("none");
  await expect(page).toHaveURL(/\/membership$/);
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByText("Signed in with Google.")).toHaveCount(0);
  await expect(page.locator("main .auth-notice").filter({ hasText: "temporarily unavailable" })).toHaveCount(0);
});


test("email login keeps membership fields loading until entitlements arrive", async ({ page }) => {
  let releaseMembership: (() => void) | undefined;
  const membershipGate = new Promise<void>((resolve) => {
    releaseMembership = resolve;
  });
  await page.route("**/api/v1/memberships/me", async (route) => {
    await membershipGate;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        plan: "supporter",
        status: "active",
        is_entitled: true,
        expires_at: null,
      }),
    });
  });
  await page.route("**/api/v1/auth/logout", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "logged_out" }),
    });
  });

  await page.goto("/membership");
  await page.getByLabel("Password account email", { exact: true }).fill("member@example.com");
  await page.getByLabel("Password", { exact: true }).fill("valid-password");
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page.getByRole("heading", { name: "Your account" })).toBeVisible();
  await expect(page.getByText("Plan", { exact: true }).locator("..")).toContainText("Loading…");
  await expect(page.getByText("Status", { exact: true }).locator("..")).toContainText("Loading…");
  releaseMembership?.();
  await expect(page.getByText("Plan", { exact: true }).locator("..")).toContainText("supporter");
  await expect(page.getByText("Playback", { exact: true }).locator("..")).toContainText("Member sessions unlocked");
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByLabel("Password account email", { exact: true })).toHaveValue("");
});


test("a stale membership response cannot cross an auth session boundary", async ({ page }) => {
  let releaseInitialUser: (() => void) | undefined;
  const initialUserGate = new Promise<void>((resolve) => {
    releaseInitialUser = resolve;
  });
  let releaseFirstMembership: (() => void) | undefined;
  const firstMembershipGate = new Promise<void>((resolve) => {
    releaseFirstMembership = resolve;
  });
  let membershipRequestCount = 0;

  await page.route("**/api/v1/users/me", async (route) => {
    await initialUserGate;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "50000000-0000-4000-8000-000000000001",
        email: "first@example.com",
        role: "member",
        is_active: true,
        created_at: "2026-07-19T00:00:00Z",
      }),
    });
  });
  await page.route("**/api/v1/auth/logout", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "logged_out" }) });
  });
  await page.route("**/api/v1/auth/login", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        access_token: "second-session-token",
        token_type: "bearer",
        expires_at: "2026-07-19T19:00:00Z",
        user: {
          id: "50000000-0000-4000-8000-000000000002",
          email: "second@example.com",
          role: "member",
          is_active: true,
          created_at: "2026-07-19T00:00:00Z",
        },
      }),
    });
  });
  await page.route("**/api/v1/memberships/me", async (route) => {
    membershipRequestCount += 1;
    if (membershipRequestCount === 1) {
      await firstMembershipGate;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ plan: "first-plan", status: "active", is_entitled: false }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ plan: "second-plan", status: "active", is_entitled: true }),
    });
  });

  await page.goto("/membership");
  await page.getByLabel("Password account email", { exact: true }).fill("stale@example.com");
  await page.getByLabel("Password", { exact: true }).fill("stale-password");
  releaseInitialUser?.();
  await expect(page.getByRole("heading", { name: "Your account" })).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByText("Loading account…")).toHaveCount(0);
  await expect(page.getByLabel("Password account email", { exact: true })).toHaveValue("");
  await expect(page.getByLabel("Password", { exact: true })).toHaveValue("");
  await page.getByLabel("Password account email", { exact: true }).fill("second@example.com");
  await page.getByLabel("Password", { exact: true }).fill("valid-password");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: "second@example.com" })).toBeVisible();
  await expect(page.getByText("Plan", { exact: true }).locator("..")).toContainText("second-plan");

  releaseFirstMembership?.();
  await page.waitForTimeout(100);
  await expect(page.getByText("Plan", { exact: true }).locator("..")).toContainText("second-plan");
  await expect(page.getByText("Plan", { exact: true }).locator("..")).not.toContainText("first-plan");
});
