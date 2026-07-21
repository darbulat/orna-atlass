import { expect, test } from "@playwright/test";

const mockApiUrl = "http://127.0.0.1:4010";

test("home page opens on a selected interactive globe before marketing content", async ({ page }) => {
  let grantRequests = 0;
  let authRequests = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().includes("/playback-grants")) grantRequests += 1;
    if (request.url().includes("/api/v1/auth/")) authRequests += 1;
  });

  await page.goto("/");

  const atlas = page.getByRole("region", { name: "ORNA Atlas" });
  await expect(atlas).toBeVisible();
  await expect(atlas.getByLabel("Interactive Cesium globe")).toBeVisible();
  const selectedLocation = atlas.locator(".dawn-copy");
  await expect(selectedLocation.getByText("Pine Marsh", { exact: true })).toBeVisible();
  await expect(selectedLocation.getByText("local time", { exact: true })).toBeVisible();

  const viewport = page.viewportSize();
  const atlasBox = await atlas.boundingBox();
  const marketingBox = await page.locator(".hero").boundingBox();
  expect(viewport).not.toBeNull();
  expect(atlasBox).not.toBeNull();
  expect(marketingBox).not.toBeNull();
  expect(atlasBox!.y).toBeLessThan(viewport!.height);
  expect(marketingBox!.y).toBeGreaterThanOrEqual(viewport!.height);

  await atlas.getByRole("button", { name: "Listen", exact: true }).click();
  const player = atlas.getByRole("region", { name: "Session player" });
  await expect(player).toBeVisible();
  await player.getByRole("button", { name: "Play session" }).click();
  await expect.poll(() => grantRequests).toBe(1);
  expect(authRequests).toBe(0);
  await expect(page).toHaveURL(/\/$/);
});

test("home globe header keeps exploration public and sign-in optional", async ({ page }) => {
  await page.goto("/");

  const navigation = page.getByRole("navigation", { name: "Primary navigation" });
  await expect(navigation.getByRole("link", { name: "Map", exact: true })).toHaveAttribute("href", "#atlas-entry");
  await expect(navigation.getByRole("link", { name: "Collections", exact: true })).toHaveAttribute("href", "#collections");
  await expect(navigation.getByRole("link", { name: "About", exact: true })).toHaveAttribute("href", "/about");
  await expect(navigation.getByRole("link", { name: "Search", exact: true })).toHaveAttribute("href", "#atlas-search");
  await expect(navigation.getByRole("link", { name: "Sign in", exact: true })).toHaveAttribute(
    "href",
    "/membership?mode=login",
  );
  await expect(navigation.getByRole("link", { name: "Subscribe", exact: true })).toHaveAttribute(
    "href",
    "/membership?mode=register",
  );
  await expect(page.getByRole("region", { name: "ORNA Atlas" }).getByRole("button", { name: "Listen", exact: true })).toBeEnabled();
});

test("home globe header stays reachable on a 320px viewport", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto("/");

  const navigation = page.getByRole("navigation", { name: "Primary navigation" });
  const links = navigation.getByRole("link");
  await expect(links).toHaveCount(7);
  for (const link of await links.all()) {
    const box = await link.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(320);
    expect(box!.width).toBeGreaterThanOrEqual(44);
    expect(box!.height).toBeGreaterThanOrEqual(44);
  }
  const badge = page.locator(".atlas-live-left");
  const badgeBox = await badge.boundingBox();
  const navigationBox = await navigation.boundingBox();
  expect(badgeBox).not.toBeNull();
  expect(navigationBox).not.toBeNull();
  expect(badgeBox!.y).toBeGreaterThanOrEqual(navigationBox!.y + navigationBox!.height);
  await expect(page.getByRole("region", { name: "ORNA Atlas" }).getByRole("button", { name: "Listen", exact: true })).toBeVisible();
  await expect(page.locator("html")).toHaveJSProperty("scrollWidth", 320);
});

test("home globe fails closed for unavailable or malformed atlas responses", async ({ page, request }) => {
  test.skip(Boolean(process.env.E2E_API_URL), "requires the deterministic mock API control endpoint");

  for (const mode of ["unavailable", "malformed-atlas", "malformed-point", "invalid-date", "malformed-dawn"]) {
    const control = await request.post(`${mockApiUrl}/__e2e/atlas-response?mode=${mode}`);
    expect(control.ok()).toBe(true);
    await page.goto("/");
    await expect(page.getByRole("alert").filter({ hasText: "Atlas unavailable" })).toBeVisible();
    await expect(page.getByRole("region", { name: "ORNA Atlas" })).toHaveCount(0);
  }
});

test("home globe keeps the last valid dawn state after a malformed refresh", async ({ page, request }) => {
  test.skip(Boolean(process.env.E2E_API_URL), "requires the deterministic mock API control endpoint");
  await page.clock.install();
  await page.goto("/");
  const atlas = page.getByRole("region", { name: "ORNA Atlas" });
  await expect(atlas).toBeVisible();
  const search = atlas.locator("#atlas-search");
  await search.fill("Pi");
  await search.clear();

  const control = await request.post(`${mockApiUrl}/__e2e/atlas-response?mode=malformed-dawn-refresh`);
  expect(control.ok()).toBe(true);
  await page.clock.runFor(60_000);

  await expect(atlas).toBeVisible();
  await expect(atlas.getByRole("status")).toContainText("Showing the last successful dawn update.");
  await expect(atlas.getByRole("button", { name: "Listen", exact: true })).toBeEnabled();
});

test("home globe accepts nullable and omitted optional Atlas point fields", async ({ page, request }) => {
  test.skip(Boolean(process.env.E2E_API_URL), "requires the deterministic mock API control endpoint");
  const control = await request.post(`${mockApiUrl}/__e2e/atlas-response?mode=valid-optional-point`);
  expect(control.ok()).toBe(true);
  await page.goto("/");

  const atlas = page.getByRole("region", { name: "ORNA Atlas" });
  await expect(atlas).toBeVisible();
  await expect(atlas.getByText("Pine Marsh", { exact: true }).first()).toBeVisible();
  await expect(atlas.getByRole("button", { name: "Listen", exact: true })).toBeDisabled();
});

test("home globe accepts UUID and date-time boundaries allowed by the API contract", async ({ page, request }) => {
  test.skip(Boolean(process.env.E2E_API_URL), "requires the deterministic mock API control endpoint");
  const control = await request.post(`${mockApiUrl}/__e2e/atlas-response?mode=valid-boundary-fields`);
  expect(control.ok()).toBe(true);
  await page.goto("/");

  const atlas = page.getByRole("region", { name: "ORNA Atlas" });
  await expect(atlas).toBeVisible();
  await expect(atlas.getByRole("button", { name: "Listen", exact: true })).toBeEnabled();
});

test("home search rejects hidden coordinates before they can enter the globe", async ({ page, request }) => {
  test.skip(Boolean(process.env.E2E_API_URL), "requires the deterministic mock API control endpoint");
  await page.goto("/");
  const control = await request.post(`${mockApiUrl}/__e2e/search-response?mode=hidden-public`);
  expect(control.ok()).toBe(true);

  await page.locator("#atlas-search").fill("hidden");
  await expect(page.getByText("The server returned an invalid response", { exact: true })).toBeVisible();
  await expect(page.getByText("Hidden Roost", { exact: true })).toHaveCount(0);
});

test("public pages use a consistent ORNA Atlas home wordmark", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("navigation", { name: "Primary navigation" })
    .getByRole("link", { name: "ORNA Atlas", exact: true })).toHaveAttribute("href", "/");

  await page.goto("/about");
  await expect(page.getByRole("navigation", { name: "About navigation" })
    .getByRole("link", { name: "ORNA Atlas", exact: true })).toHaveAttribute("href", "/");

  await page.goto("/atlas?view=list");
  await expect(page.locator(".atlas-brand")).toHaveAttribute("href", "/");
});

test("public legal pages disclose the operator and are linked from the home page", async ({ page }) => {
  await page.goto("/");

  const legalNavigation = page.getByRole("navigation", { name: "Legal" });
  await expect(legalNavigation.getByRole("link", { name: "Privacy Policy" })).toHaveAttribute(
    "href",
    "/privacy",
  );
  await expect(legalNavigation.getByRole("link", { name: "Terms" })).toHaveAttribute(
    "href",
    "/terms",
  );

  await page.goto("/privacy");
  await expect(page).toHaveTitle(/Privacy Policy/);
  await expect(page.getByRole("heading", { level: 1, name: "Privacy Policy" })).toBeVisible();
  await expect(page.getByText("Kale Ltd.", { exact: true })).toBeVisible();
  await expect(page.getByText("221040900084", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your privacy rights" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Map imagery provider" })).toBeVisible();
  await expect(page.getByText(/ArcGIS World Imagery/)).toBeVisible();

  await page.goto("/terms");
  await expect(page).toHaveTitle(/Terms of Use/);
  await expect(page.getByRole("heading", { level: 1, name: "Terms of Use" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Our rights and third-party content" })).toBeVisible();
  await expect(page.getByText("Rim Safiullin", { exact: true })).toBeVisible();
  await expect(page.getByText("Software development", { exact: true })).toBeVisible();
  await expect(page.getByText("Software maintenance", { exact: true })).toBeVisible();
  await expect(page.getByText("Other IT services", { exact: true })).toBeVisible();
});

test("legal pages remain contained and navigable on a narrow phone", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });

  for (const path of ["/privacy", "/terms"]) {
    await page.goto(path);
    const metrics = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
    }));
    expect(metrics.scrollWidth).toBe(metrics.viewport);

    const navigationLinks = page.locator(".legal-nav a, .site-footer nav a");
    for (const link of await navigationLinks.all()) {
      const box = await link.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(320);
      expect(box!.height).toBeGreaterThanOrEqual(44);
    }
  }
});

test("home skip link bypasses the primary navigation", async ({ page }) => {
  await page.goto("/");

  const navigation = page.getByRole("navigation", { name: "Primary navigation" });
  const main = page.locator("main#main-content");
  await expect(main.getByRole("navigation", { name: "Primary navigation" })).toHaveCount(0);

  const navigationPrecedesMain = await navigation.evaluate((nav, mainElement) => (
    Boolean(nav.compareDocumentPosition(mainElement as Node) & Node.DOCUMENT_POSITION_FOLLOWING)
  ), await main.elementHandle());
  expect(navigationPrecedesMain).toBe(true);
});

test("home and manifesto share editorial display typography", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveCSS("font-family", /Georgia/);

  await page.goto("/about");
  await expect(page.getByRole("heading", { level: 1 })).toHaveCSS("font-family", /Georgia/);
});

test("about mobile calls to action provide 44px touch targets", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/about");

  const callsToAction = page.locator(".about-nav a, .about-enter");
  await expect(callsToAction).toHaveCount(3);

  for (const link of await callsToAction.all()) {
    const box = await link.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.height).toBeGreaterThanOrEqual(44);
  }
});

test("home sample analytics is emitted only after playback starts", async ({ page }) => {
  const events: Array<{ name: string }> = [];
  await page.route("**/playback-grants", async (route) => {
    await route.fulfill({ status: 503, headers: { "Content-Type": "application/json" }, body: "{}" });
  });
  await page.exposeFunction("captureSampleAnalytics", (detail: { name: string }) => events.push(detail));
  await page.addInitScript(() => {
    window.addEventListener("orna:analytics", (event) => {
      void (window as typeof window & {
        captureSampleAnalytics: (detail: unknown) => Promise<void>;
      }).captureSampleAnalytics((event as CustomEvent).detail);
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Listen free" }).click();
  await expect(page.locator(".hero-sample").getByRole("alert")).toBeVisible();
  expect(events.filter((event) => event.name === "sample_play_started")).toEqual([]);
});

test("missing curated intent collections fall back to the atlas", async ({ page }) => {
  await page.route("**/api/v1/collections**", async (route) => {
    await route.fulfill({ status: 200, headers: { "Content-Type": "application/json" }, body: "[]" });
  });

  await page.goto("/");
  const paths = page.getByRole("region", { name: "Choose your listening path" });
  await expect(paths.getByRole("link", { name: /Focus/ })).toHaveAttribute("href", "/atlas");
  await expect(paths.getByRole("link", { name: /Restore/ })).toHaveAttribute("href", "/atlas");
  await expect(paths.getByRole("link", { name: /Unwind/ })).toHaveAttribute("href", "/atlas");
});

test("home page explains listening paths, proof, membership value, and common questions", async ({ page }) => {
  await page.goto("/");

  const listeningPaths = page.getByRole("region", { name: "Choose your listening path" });
  await expect(listeningPaths.getByRole("link", { name: /Focus/ })).toHaveAttribute(
    "href",
    "/atlas",
  );
  await expect(listeningPaths.getByRole("link", { name: /Explore/ })).toHaveAttribute(
    "href",
    "/atlas",
  );

  await expect(page.getByRole("region", { name: "Atlas in numbers" })).toContainText(
    "continuous field recordings",
  );
  await expect(page.getByRole("region", { name: "Listener stories" })).toBeVisible();

  const membership = page.getByRole("region", { name: "Membership comparison" });
  await expect(membership.getByRole("columnheader", { name: "Free" })).toBeVisible();
  await expect(membership.getByRole("columnheader", { name: "Member" })).toBeVisible();
  await expect(membership.getByText("Complete long-form sessions")).toBeVisible();

  const pricing = page.getByRole("region", { name: "One membership. The complete atlas." });
  await expect(pricing.getByRole("heading", { name: "One membership. The complete atlas." })).toBeVisible();
  await expect(pricing.getByText("Pricing is announced before payment")).toBeVisible();
  await expect(pricing.getByRole("link", { name: "Join early access" })).toHaveAttribute(
    "href",
    "/membership?mode=register",
  );

  const faq = page.getByRole("region", { name: "Frequently asked questions" });
  await expect(faq.getByText("Are these sounds generated by AI?")).toBeVisible();
  await expect(faq.getByText("Why are some coordinates hidden?")).toBeVisible();
});

test("home mobile carousel cards fit fully inside the 320px viewport", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/");

  const cards = page.locator(".intent-grid > a, .featured-grid > article");
  expect(await cards.count()).toBeGreaterThanOrEqual(5);

  const widths = await cards.evaluateAll((items) => items.map((item) => item.getBoundingClientRect().width));
  for (const width of widths) {
    expect(width).toBeLessThanOrEqual(320 - 44);
  }

  const firstCard = await cards.first().boundingBox();
  expect(firstCard).not.toBeNull();
  expect(firstCard!.x).toBeGreaterThanOrEqual(0);
  expect(firstCard!.x + firstCard!.width).toBeLessThanOrEqual(320);
});

test("home mobile carousel keeps every listening path horizontally reachable", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/");

  const carousel = page.locator(".intent-grid");
  const lastCard = carousel.locator(":scope > a").last();
  const dimensions = await carousel.evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
  }));
  expect(dimensions.scrollWidth).toBeGreaterThan(dimensions.clientWidth);

  await carousel.evaluate((element) => element.scrollTo({ left: element.scrollWidth, behavior: "instant" }));
  await expect.poll(async () => carousel.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);

  const lastCardBox = await lastCard.boundingBox();
  expect(lastCardBox).not.toBeNull();
  expect(lastCardBox!.x).toBeGreaterThanOrEqual(0);
  expect(lastCardBox!.x + lastCardBox!.width).toBeLessThanOrEqual(320);
});

test("home conversion links emit bounded analytics events", async ({ page }) => {
  const events: Array<{ name: string; placement: string; destination: string }> = [];
  const persistedEvents: unknown[] = [];
  await page.route("**/api/v1/analytics/events", async (route) => {
    persistedEvents.push(route.request().postDataJSON());
    await route.fulfill({
      status: 202,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ accepted: true }),
    });
  });
  await page.exposeFunction(
    "captureOrnaAnalytics",
    (detail: { name: string; placement: string; destination: string }) => {
      events.push(detail);
    },
  );
  await page.addInitScript(() => {
    window.addEventListener("orna:analytics", (event) => {
      const detail = (event as CustomEvent).detail;
      void (window as typeof window & {
        captureOrnaAnalytics: (value: unknown) => Promise<void>;
      }).captureOrnaAnalytics(detail);
    });
  });

  await page.goto("/");
  await page.getByRole("region", { name: "Choose your listening path" })
    .getByRole("link", { name: /Focus/ })
    .click();

  await expect.poll(() => events).toContainEqual({
    name: "listening_path_selected",
    placement: "intent_focus",
    destination: "/atlas",
  });
  await expect.poll(() => persistedEvents).toContainEqual({
    name: "listening_path_selected",
    placement: "intent_focus",
  });
});

test("analytics delivery failure never blocks conversion navigation", async ({ page }) => {
  await page.route("**/api/v1/analytics/events", async (route) => route.abort("failed"));
  await page.goto("/");

  await page.locator(".hero").getByRole("link", { name: "Explore the atlas" }).click();

  await expect(page).toHaveURL(/\/atlas$/);
  await expect(page.locator("main#main-content")).toBeVisible();
});

test("atlas route renders without a browser error", async ({ page }) => {
  await page.goto("/atlas?view=list");
  await expect(page.locator("main#main-content")).toBeVisible();
  await expect(page.getByLabel("Atlas list view")).toBeVisible();
  await expect(page.locator(".dawn-copy")).toHaveCSS("pointer-events", "none");
  await expect(page.locator(".dawn-copy .listen-pill")).toHaveCSS("pointer-events", "auto");
  await expect(page.getByRole("link", { name: "About" })).toHaveText("About");
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

test("atlas discovery controls stay inside a 320px mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/atlas?view=list");

  const viewport = page.viewportSize();
  expect(viewport).not.toBeNull();

  const controls = page.locator(
    ".atlas-discovery-panel [role='tab'], .atlas-discovery-panel .location-card, .atlas-discovery-panel .carousel-arrow",
  );
  expect(await controls.count()).toBeGreaterThanOrEqual(6);

  for (const control of await controls.all()) {
    const box = await control.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(viewport!.width);
  }
});

test("atlas mobile navigation controls provide 44px touch targets", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/atlas?view=list");

  const controls = page.locator(
    ".globe-tools button, .about-link, .time-tabs button, .carousel-arrow",
  );
  expect(await controls.count()).toBeGreaterThanOrEqual(9);

  for (const control of await controls.all()) {
    const box = await control.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeGreaterThanOrEqual(44);
    expect(box!.height).toBeGreaterThanOrEqual(44);
  }
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

  await page.getByRole("button", { name: "Listen", exact: true }).click();

  await expect.poll(() => page.evaluate(() => {
    const probe = (window as typeof window & {
      atlasFocusProbe?: Array<{ sidePanelVisible: boolean; canvasMatchesHost: boolean }>;
    }).atlasFocusProbe;
    return probe?.at(-1) ?? null;
  })).toEqual({ sidePanelVisible: true, canvasMatchesHost: true });
});

test("membership route exposes login and registration controls", async ({ page }) => {
  await page.goto("/membership");
  await expect(
    page.getByRole("heading", { level: 1, name: "Sign in or create your account" }),
  ).toBeVisible();
  await expect(page.locator("form").getByRole("button", { name: "Continue" })).toBeVisible();
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByLabel("Email")).toBeVisible();
  await expect(page.getByLabel("Password")).toHaveAttribute("minlength", "12");
});

test("membership registration link opens the registration form", async ({ page }) => {
  await page.goto("/membership?mode=register");

  await expect(page.getByRole("button", { name: "Create account", pressed: true })).toBeVisible();
  await expect(page.locator("form").getByRole("button", { name: "Continue" })).toBeVisible();
  await expect(page.getByLabel("Password")).toHaveAttribute("minlength", "12");
});

test("membership registration emits a completion event without personal data", async ({ page }) => {
  await page.route("**/api/v1/auth/register", async (route) => {
    await route.fulfill({
      status: 201,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: "50000000-0000-4000-8000-000000000002",
        email: "new-listener@example.com",
        role: "member",
        is_active: true,
        created_at: "2026-07-17T00:00:00Z",
      }),
    });
  });
  await page.addInitScript(() => {
    (window as typeof window & { __analytics?: unknown[] }).__analytics = [];
    window.addEventListener("orna:analytics", (event) => {
      (window as typeof window & { __analytics?: unknown[] }).__analytics?.push((event as CustomEvent).detail);
    });
  });
  await page.goto("/membership?mode=register");
  await page.getByLabel("Email").fill("new-listener@example.com");
  await page.getByLabel("Password").fill("correct horse battery staple");
  await page.locator("form").getByRole("button", { name: "Continue" }).click();

  await expect.poll(() => page.evaluate(() => (
    window as typeof window & { __analytics?: unknown[] }
  ).__analytics ?? [])).toEqual([{
    name: "registration_completed",
    placement: "membership_form",
  }]);
  await expect(page.getByRole("status")).toContainText("You’re on the early access list");
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
  await page.locator("form").getByRole("button", { name: "Continue" }).click();

  await expect(page.getByRole("heading", { name: "member@example.com" })).toBeVisible();
  await expect(page.getByText("Member sessions unlocked")).toBeVisible();
  await expect(page.getByText("active", { exact: true })).toBeVisible();
});
