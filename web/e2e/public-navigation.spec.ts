import { expect, test } from "@playwright/test";

test("home page exposes the primary atlas journey", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/ORNA Atlas/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("living map");
  await expect(page.getByRole("link", { name: "Open atlas" })).toHaveAttribute("href", "/atlas");
  await expect(page.getByRole("link", { name: "Skip to main content" })).toHaveAttribute(
    "href",
    "#main-content",
  );
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
});

test("atlas route renders without a browser error", async ({ page }) => {
  await page.goto("/atlas?view=list");
  await expect(page.locator("main#main-content")).toBeVisible();
  await expect(page.getByLabel("Atlas list view")).toBeVisible();
  await expect(page.locator(".dawn-copy")).toHaveCSS("pointer-events", "none");
  await expect(page.locator(".dawn-copy .listen-pill")).toHaveCSS("pointer-events", "auto");
  await expect(page.getByRole("button", { name: "Tune filters" })).toHaveCount(0);
});

test("current-location control selects the nearest public listening site", async ({ context, page }) => {
  await context.grantPermissions(["geolocation"], { origin: "http://127.0.0.1:3100" });
  await context.setGeolocation({ latitude: 59.43, longitude: 24.72 });
  await page.goto("/atlas?view=list");

  const locateButton = page.getByRole("button", { name: "Use current location" });
  await expect(locateButton).toBeEnabled();
  await locateButton.click();

  await expect(page.getByRole("status")).toHaveText("Nearest listening location: Pine Marsh.");
  await expect(page.locator(".dawn-copy strong")).toHaveText("Pine Marsh");
});

test("atlas loads the interactive Cesium globe on a mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const cesiumResponse = page.waitForResponse((response) =>
    response.url().endsWith("/cesium/Cesium.js"),
  );

  await page.goto("/atlas");

  await expect.poll(async () => (await cesiumResponse).status()).toBe(200);
  const canvas = page.locator(".cesium-widget canvas");
  await expect(canvas).toHaveCount(1);
  await expect(canvas).toBeVisible();
  await expect(page.locator(".cesium-credit-logoContainer")).toBeHidden();

  const box = await canvas.boundingBox();
  expect(box?.width).toBeGreaterThan(200);
  expect(box?.height).toBeGreaterThan(200);
});

test("enter recenters the resized globe on the selected location at a closer zoom", async ({ page }) => {
  await page.goto("/atlas");

  const globe = page.getByLabel("Interactive Cesium globe");
  await expect(page.locator(".cesium-widget canvas")).toBeVisible();
  await expect(globe).toHaveAttribute("data-focus-height", "1500000");

  await page.evaluate(() => {
    const cesiumWindow = window as typeof window & {
      Cesium?: { Camera: { prototype: { flyTo: (options: unknown) => unknown } } };
      atlasFocusProbe?: Array<{ sidePanelVisible: boolean; canvasMatchesHost: boolean }>;
    };
    const cameraPrototype = cesiumWindow.Cesium!.Camera.prototype;
    const originalFlyTo = cameraPrototype.flyTo;
    cesiumWindow.atlasFocusProbe = [];
    cameraPrototype.flyTo = function patchedFlyTo(options: unknown) {
      const host = document.querySelector<HTMLElement>(".cesium-host");
      const canvas = host?.querySelector<HTMLCanvasElement>("canvas");
      const pixelRatio = window.devicePixelRatio || 1;
      cesiumWindow.atlasFocusProbe!.push({
        sidePanelVisible: document.querySelector(".atlas-side-panel") !== null,
        canvasMatchesHost: Boolean(
          host
          && canvas
          && Math.abs(canvas.width - host.clientWidth * pixelRatio) <= 1
          && Math.abs(canvas.height - host.clientHeight * pixelRatio) <= 1
        ),
      });
      return originalFlyTo.call(this, options);
    };
  });

  await page.getByRole("button", { name: "Enter", exact: true }).click();

  await expect.poll(() => page.evaluate(() => {
    const probe = (window as typeof window & {
      atlasFocusProbe?: Array<{ sidePanelVisible: boolean; canvasMatchesHost: boolean }>;
    }).atlasFocusProbe;
    return probe?.at(-1) ?? null;
  })).toEqual({ sidePanelVisible: true, canvasMatchesHost: true });
});

test("membership route exposes login and registration controls", async ({ page }) => {
  await page.goto("/membership");
  await expect(page.getByRole("heading", { level: 1, name: "Membership" })).toBeVisible();
  await expect(page.locator("form").getByRole("button", { name: "Sign in" })).toBeVisible();
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByLabel("Email")).toBeVisible();
  await expect(page.getByLabel("Password")).toHaveAttribute("minlength", "12");
});

test("an authenticated member sees the active entitlement state", async ({ page }) => {
  await page.route("**/api/v1/memberships/me", async (route) => {
    await route.fulfill({
      status: 200,
      headers: {
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Origin": "http://127.0.0.1:3100",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        id: "60000000-0000-4000-8000-000000000001",
        user_id: "50000000-0000-4000-8000-000000000001",
        status: "active",
        plan: "member",
        starts_at: "2026-07-01T00:00:00Z",
        expires_at: null,
        is_entitled: true,
      }),
    });
  });

  await page.goto("/membership");
  await page.getByLabel("Email").fill("member@example.com");
  await page.getByLabel("Password").fill("correct horse battery staple");
  await page.locator("form").getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByRole("heading", { name: "member@example.com" })).toBeVisible();
  await expect(page.getByText("Member sessions unlocked")).toBeVisible();
  await expect(page.getByText("active", { exact: true })).toBeVisible();
});
