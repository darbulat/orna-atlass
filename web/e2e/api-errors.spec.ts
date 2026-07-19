import { expect, test } from "@playwright/test";

const corsHeaders = {
  "Access-Control-Allow-Credentials": "true",
  "Access-Control-Allow-Origin": "http://127.0.0.1:3100",
  "Content-Type": "application/json",
};

test("a missing session is distinct from a backend outage", async ({ page }) => {
  await page.goto("/sessions/missing-session");

  await expect(page.getByRole("heading", { name: "Session not found" })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("does not exist");
});

test("membership reports an account API outage instead of treating it as signed out", async ({ page }) => {
  await page.route("**/api/v1/users/me", async (route) => {
    await route.fulfill({
      status: 503,
      headers: corsHeaders,
      body: JSON.stringify({ detail: "Identity service is unavailable" }),
    });
  });

  await page.goto("/membership");

  await expect(page.getByText(/ORNA Atlas is temporarily unavailable/)).toBeVisible();
  await expect(page.locator("form").getByRole("button", { name: "Continue" })).toBeVisible();
});

test("atlas search results open inside the visible viewport", async ({ page }) => {
  await page.goto("/atlas?view=list");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.getByLabel("Search location").fill("pine");

  const results = page.locator(".search-results");
  await expect(results.getByText("Pine Marsh", { exact: true })).toBeVisible();
  const box = await results.boundingBox();
  const viewport = page.viewportSize();
  expect(box).not.toBeNull();
  expect(viewport).not.toBeNull();
  expect(box!.height).toBeGreaterThan(40);
  expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(box!.y + box!.height).toBeLessThanOrEqual(viewport!.height);
});

test("atlas search exposes an unavailable state instead of an empty result", async ({ page }) => {
  await page.route("**/api/v1/search?**", async (route) => {
    await route.fulfill({
      status: 503,
      headers: corsHeaders,
      body: JSON.stringify({ detail: "Search service is unavailable" }),
    });
  });

  await page.goto("/atlas?view=list");
  await page.getByLabel("Search location").fill("pine");

  await expect(page.getByText(/ORNA Atlas is temporarily unavailable/)).toBeVisible();
  await expect(page.getByText("No public results found.")).toHaveCount(0);
});

test("a not-ready playback grant is announced to the listener", async ({ page }) => {
  await page.route("**/playback-grants", async (route) => {
    await route.fulfill({
      status: 409,
      headers: corsHeaders,
      body: JSON.stringify({ detail: "Streaming rendition is not ready" }),
    });
  });

  await page.goto("/sessions/first-session");
  await page.getByRole("button", { name: "Play session" }).click();

  await expect(page.getByText("Streaming rendition is not ready")).toBeVisible();
  await expect(page.locator(".session-player-caption")).toContainText("error");
});

test("a membership-protected playback grant exposes the forbidden state", async ({ page }) => {
  await page.route("**/playback-grants", async (route) => {
    await route.fulfill({
      status: 403,
      headers: corsHeaders,
      body: JSON.stringify({ detail: "An active membership is required" }),
    });
  });

  await page.goto("/sessions/first-session");
  await page.getByRole("button", { name: "Play session" }).click();

  await expect(page.getByRole("alert").filter({ hasText: "active membership" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Play session" })).toBeVisible();
});
