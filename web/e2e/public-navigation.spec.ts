import { expect, test } from "@playwright/test";

const mockApiUrl = "http://127.0.0.1:4010";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const continuations = { load: 0, mutation: 0 };
    Object.assign(window, { __favoriteContinuations: continuations });
    window.addEventListener("orna:test:favorite-continuation", ((event: CustomEvent<{ kind?: "load" | "mutation" }>) => {
      const kind = event.detail.kind;
      if (kind) continuations[kind] += 1;
    }) as EventListener);
  });
});

type BoundingBox = { x: number; y: number; width: number; height: number };

function boxesOverlap(first: BoundingBox, second: BoundingBox) {
  return first.x < second.x + second.width
    && first.x + first.width > second.x
    && first.y < second.y + second.height
    && first.y + first.height > second.y;
}

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
  const discoveryBox = await page.getByRole("region", { name: "Popular locations" }).boundingBox();
  expect(viewport).not.toBeNull();
  expect(atlasBox).not.toBeNull();
  expect(discoveryBox).not.toBeNull();
  expect(atlasBox!.y).toBeLessThan(viewport!.height);
  expect(discoveryBox!.y).toBeGreaterThanOrEqual(viewport!.height);

  const grantRequest = page.waitForRequest((request) => request.url().includes("/playback-grants"));
  await atlas.getByRole("button", { name: "Listen", exact: true }).click();
  await grantRequest;
  const player = atlas.getByRole("region", { name: "Session player" });
  await expect(player).toBeVisible();
  expect(grantRequests).toBe(1);
  expect(authRequests).toBe(0);
  await expect(page).toHaveURL(/\/$/);
});

test("atlas globe tools remain disjoint and clickable above Cesium controls", async ({ page }) => {
  for (const viewport of [
    { width: 1280, height: 800 },
    { width: 390, height: 844 },
    { width: 320, height: 800 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto("/atlas");

    const search = page.getByRole("button", { name: "Search", exact: true });
    const reset = page.getByRole("button", { name: "Reset globe" });
    const [searchBox, resetBox] = await Promise.all([search.boundingBox(), reset.boundingBox()]);
    expect(searchBox).not.toBeNull();
    expect(resetBox).not.toBeNull();
    expect(boxesOverlap(searchBox!, resetBox!)).toBe(false);

    await search.click();
    await expect(page.locator("#atlas-search")).toBeFocused();
    await reset.click();
  }
});

test("atlas starts the selected public preview with one click and no auth gate", async ({ page }) => {
  const authRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/auth/me") || request.url().includes("/memberships/me")) authRequests.push(request.url());
  });
  await page.goto("/atlas");
  const grantRequest = page.waitForRequest((request) => request.url().includes("/playback-grants"));
  await page.getByRole("button", { name: "Listen", exact: true }).click();
  await grantRequest;
  await expect(page.locator("#atlas-session-player")).toBeVisible();
  expect(authRequests).toEqual([]);
});

test("home globe includes a current dawn location outside the capped Atlas window", async ({ page, request }) => {
  test.skip(Boolean(process.env.E2E_API_URL), "requires the deterministic mock API control endpoint");
  const control = await request.post(`${mockApiUrl}/__e2e/atlas-response?mode=dawn-only-location`);
  expect(control.ok()).toBe(true);
  await page.goto("/");

  const atlas = page.getByRole("region", { name: "ORNA Atlas" });
  await expect(atlas.getByText("Pine Marsh", { exact: true }).first()).toBeVisible();
  await expect(atlas.getByRole("button", { name: "Listen", exact: true })).toBeEnabled();
});

test("home globe selects the first active dawn location instead of an earlier Dawn-mode point", async ({ page, request }) => {
  test.skip(Boolean(process.env.E2E_API_URL), "requires the deterministic mock API control endpoint");
  const control = await request.post("http://127.0.0.1:4010/__e2e/atlas-response?mode=multiple-dawn");
  expect(control.ok()).toBeTruthy();

  await page.goto("/");
  const atlas = page.getByRole("region", { name: "ORNA Atlas" });
  await expect(atlas.locator(".dawn-copy strong")).toHaveText("Pine Marsh");
});

test("home globe selects the next dawn location when no location is active", async ({ page, request }) => {
  test.skip(Boolean(process.env.E2E_API_URL), "requires the deterministic mock API control endpoint");
  const control = await request.post("http://127.0.0.1:4010/__e2e/atlas-response?mode=next-only-dawn");
  expect(control.ok()).toBeTruthy();

  await page.goto("/");
  const atlas = page.getByRole("region", { name: "ORNA Atlas" });
  await expect(atlas.locator(".dawn-copy strong")).toHaveText("Ridge Dawn");
});

test("home globe merges newly active dawn locations after a client refresh", async ({ page, request }) => {
  test.skip(Boolean(process.env.E2E_API_URL), "requires the deterministic mock API control endpoint");
  await page.clock.install();
  const control = await request.post("http://127.0.0.1:4010/__e2e/atlas-response?mode=dawn-refresh-location");
  expect(control.ok()).toBeTruthy();

  await page.goto("/");
  const atlas = page.getByRole("region", { name: "ORNA Atlas" });
  await expect(atlas.locator(".dawn-copy strong")).toHaveText("Pine Marsh");
  await expect(atlas.getByText("Ridge Dawn", { exact: true })).toHaveCount(0);
  await page.clock.runFor(1_100);
  await expect(atlas.getByText("Ridge Dawn", { exact: true }).first()).toBeVisible();
});

test("home navigation leaves the inline player controls clickable", async ({ page }) => {
  await page.goto("/");
  const atlas = page.getByRole("region", { name: "ORNA Atlas" });
  await atlas.getByRole("button", { name: "Listen", exact: true }).click();
  await expect(page.getByRole("region", { name: "Session player" })).toBeVisible();

  await expect(page.locator(".home-nav")).toHaveCSS("pointer-events", "none");
  await expect(page.locator(".home-nav a").first()).toHaveCSS("pointer-events", "auto");
  await page.getByRole("button", { name: "Hide player" }).click();
  await expect(page.getByRole("region", { name: "Session player" })).toHaveCount(0);
});

test("mobile home navigation leaves the inline player controls clickable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  const atlas = page.getByRole("region", { name: "ORNA Atlas" });
  await atlas.getByRole("button", { name: "Listen", exact: true }).click();
  await expect(page.getByRole("region", { name: "Session player" })).toBeVisible();
  await page.getByRole("button", { name: "Hide player" }).click();
  await expect(page.getByRole("region", { name: "Session player" })).toHaveCount(0);
});

test("home globe header keeps exploration public and sign-in optional", async ({ page }) => {
  await page.goto("/");

  const navigation = page.getByRole("navigation", { name: "Primary navigation" });
  await expect(navigation.getByRole("link", { name: "Map", exact: true })).toHaveAttribute("href", "/#atlas-entry");
  await expect(navigation.getByRole("link", { name: "Collections", exact: true })).toHaveAttribute("href", "/collections");
  await expect(navigation.getByRole("link", { name: "About", exact: true })).toHaveAttribute("href", "/about");
  await expect(navigation.getByRole("button", { name: "Open search", exact: true })).toBeEnabled();
  await expect(page.getByRole("contentinfo")).toHaveCount(1);
  await expect(navigation.getByRole("button", { name: "Sign in", exact: true })).toBeEnabled();
  await expect(navigation.getByRole("link", { name: "Subscribe", exact: true })).toHaveAttribute(
    "href",
    "/membership?mode=register",
  );
  await expect(page.getByRole("region", { name: "ORNA Atlas" }).getByRole("button", { name: "Listen", exact: true })).toBeEnabled();
});

test("header search and sign-in open accessible overlays without replacing the atlas", async ({ page }) => {
  await page.goto("/");
  const navigation = page.getByRole("navigation", { name: "Primary navigation" });
  const atlas = page.locator(".atlas-reference-ui");
  const searchTrigger = navigation.getByRole("button", { name: "Open search" });
  await searchTrigger.click();
  const searchDialog = page.getByRole("dialog", { name: "Search locations and recordings" });
  await expect(searchDialog).toBeVisible();
  await expect(page.locator("nav.site-nav")).toHaveAttribute("aria-hidden", "true");
  await expect(page.locator("main#main-content")).toHaveAttribute("aria-hidden", "true");
  await expect(atlas).toBeVisible();
  await searchDialog.getByLabel("Search", { exact: true }).fill("Pine");
  await searchDialog.getByRole("button", { name: "Show results" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.locator("#atlas-search")).toHaveValue("Pine");
  await expect(searchTrigger).toBeFocused();
  await expect(page.locator("nav.site-nav")).not.toHaveAttribute("aria-hidden", "true");
  await expect(page.locator("main#main-content")).not.toHaveAttribute("aria-hidden", "true");

  const loginTrigger = navigation.getByRole("button", { name: "Sign in", exact: true });
  await loginTrigger.click();
  const loginDialog = page.getByRole("dialog", { name: "Sign in without leaving the atlas" });
  await expect(loginDialog).toBeVisible();
  await expect(atlas).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(loginDialog).toHaveCount(0);
  await expect(loginTrigger).toBeFocused();
  await expect(page).toHaveURL(/\/$/);
});

test("header search carries its query from editorial pages into the atlas", async ({ page }) => {
  await page.goto("/about");
  await page.getByRole("button", { name: "Open search" }).click();
  const dialog = page.getByRole("dialog", { name: "Search locations and recordings" });
  await dialog.getByLabel("Search", { exact: true }).fill("Pine");
  await dialog.getByRole("button", { name: "Show results" }).click();

  await expect(page).toHaveURL(/\/?search=Pine#atlas-search$/);
  const atlasSearch = page.locator("#atlas-search");
  await expect(atlasSearch).toHaveValue("Pine");
  await atlasSearch.fill("Pin");
  await atlasSearch.fill("Pine");
  await expect(atlasSearch).toHaveValue("Pine");
  await expect(page.getByRole("button", { name: /Pine Marsh Harju \/ Wetland/ })).toBeVisible();
});

test("home globe header stays reachable on a 320px viewport", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto("/");

  const navigation = page.getByRole("navigation", { name: "Primary navigation" });
  const controls = navigation.getByRole("link").or(navigation.getByRole("button"));
  await expect(controls).toHaveCount(7);
  for (const control of await controls.all()) {
    const box = await control.boundingBox();
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

test("featured session keeps a direct route when the atlas is unavailable", async ({ page, request }) => {
  test.skip(Boolean(process.env.E2E_API_URL), "requires the deterministic mock API control endpoint");
  const control = await request.post(`${mockApiUrl}/__e2e/atlas-response?mode=unavailable`);
  expect(control.ok()).toBe(true);
  await page.goto("/");
  await expect(page.getByRole("alert").filter({ hasText: "Atlas unavailable" })).toBeVisible();

  const featured = page.getByRole("link", { name: "First Session", exact: true });
  await expect(featured).toHaveAttribute("href", "/sessions/first-session");
  await featured.click();
  await expect(page).toHaveURL(/\/sessions\/first-session$/);
  await expect(page.getByRole("heading", { name: "First Session" })).toBeVisible();
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

test("home search keeps an upcoming dawn location in Dawn mode", async ({ page, request }) => {
  test.skip(Boolean(process.env.E2E_API_URL), "requires the deterministic mock API control endpoint");
  const atlasControl = await request.post(`${mockApiUrl}/__e2e/atlas-response?mode=next-only-dawn`);
  expect(atlasControl.ok()).toBe(true);
  await page.goto("/");
  const searchControl = await request.post(`${mockApiUrl}/__e2e/search-response?mode=next-only-dawn`);
  expect(searchControl.ok()).toBe(true);

  await page.locator("#atlas-search").fill("ridge");
  await page.locator(".search-results").getByRole("button", { name: /Ridge Dawn/ }).click();
  await expect(page.getByRole("tab", { name: "Dawn" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByText(/Dawn Now/i)).toHaveCount(0);
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
  await expect(page.getByRole("navigation", { name: "Primary navigation" })
    .getByRole("link", { name: "ORNA Atlas", exact: true })).toHaveAttribute("href", "/");

  await page.goto("/atlas?view=list");
  await expect(page.getByRole("navigation", { name: "Primary navigation" })
    .getByRole("link", { name: "ORNA Atlas", exact: true })).toHaveAttribute("href", "/");
});

test("public legal pages disclose the operator and are linked from the home page", async ({ page }) => {
  await page.goto("/");

  const legalNavigation = page.locator(".site-footer").first().getByRole("navigation", { name: "Legal" });
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
  await expect(page.getByRole("heading", { level: 2, name: "Popular locations" })).toHaveCSS("font-family", /Georgia/);

  await page.goto("/about");
  await expect(page.getByRole("heading", { level: 1 })).toHaveCSS("font-family", /Georgia/);
});

test("about mobile calls to action provide 44px touch targets", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/about");

  const callsToAction = page.locator(".about-nav a, .about-nav button, .about-enter");
  expect(await callsToAction.count()).toBeGreaterThanOrEqual(8);

  for (const link of await callsToAction.all()) {
    const box = await link.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.height).toBeGreaterThanOrEqual(44);
  }
});

test("home preview does not report playback start when the grant fails", async ({ page }) => {
  const events: Array<{ name: string }> = [];
  await page.route("**/playback-grants", async (route) => {
    await route.fulfill({ status: 503, headers: { "Content-Type": "application/json" }, body: "{}" });
  });
  await page.exposeFunction("capturePreviewAnalytics", (detail: { name: string }) => events.push(detail));
  await page.addInitScript(() => {
    window.addEventListener("orna:analytics", (event) => {
      void (window as typeof window & {
        capturePreviewAnalytics: (detail: unknown) => Promise<void>;
      }).capturePreviewAnalytics((event as CustomEvent).detail);
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: /Play preview for/ }).first().click();
  await expect(page.getByRole("complementary", { name: "Global audio player" }).getByRole("alert")).toBeVisible();
  expect(events.filter((event) => ["session_preview_start", "player_play"].includes(event.name))).toEqual([]);
});

test("featured collections keep a truthful dedicated entry point", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Featured collections" })).toBeVisible();
  await expect(page.getByRole("link", { name: "See all collections" })).toHaveAttribute("href", "/collections");
});

test("home discovery cards fit inside a 320px viewport", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/");
  const cards = page.locator(".popular-location, .featured-grid > article");
  expect(await cards.count()).toBeGreaterThanOrEqual(1);
  for (const card of await cards.all()) {
    const box = await card.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeLessThanOrEqual(320);
  }
  await expect(page.locator("html")).toHaveJSProperty("scrollWidth", 320);
});

test("analytics delivery failure never blocks collections navigation", async ({ page }) => {
  await page.route("**/api/v1/analytics/events", async (route) => route.abort("failed"));
  await page.goto("/");
  await page.getByRole("link", { name: "See all collections" }).click();
  await expect(page).toHaveURL(/\/collections$/);
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

test("atlas route includes a current dawn location outside the capped Atlas window", async ({ page, request }) => {
  test.skip(Boolean(process.env.E2E_API_URL), "requires the deterministic mock API control endpoint");
  const control = await request.post(`${mockApiUrl}/__e2e/atlas-response?mode=dawn-only-location`);
  expect(control.ok()).toBe(true);
  await page.route("**/api/v1/atlas/dawn/current**", (route) => route.abort());

  await page.goto("/atlas");
  const atlas = page.getByRole("region", { name: "ORNA Atlas" });
  await expect(atlas.locator(".dawn-copy strong")).toHaveText("Pine Marsh");
  await expect(atlas.getByRole("button", { name: "Listen", exact: true })).toBeEnabled();
});

test("atlas list view selects an active dawn location during SSR", async ({ page, request }) => {
  test.skip(Boolean(process.env.E2E_API_URL), "requires the deterministic mock API control endpoint");
  const control = await request.post(`${mockApiUrl}/__e2e/atlas-response?mode=dawn-only-location`);
  expect(control.ok()).toBe(true);
  await page.route("**/api/v1/atlas/dawn/current**", (route) => route.abort());

  await page.goto("/atlas?view=list");
  await expect(page.getByRole("region", { name: "ORNA Atlas" }).locator(".dawn-copy strong"))
    .toHaveText("Pine Marsh");
});

test("atlas list view selects a next dawn location during SSR", async ({ page, request }) => {
  test.skip(Boolean(process.env.E2E_API_URL), "requires the deterministic mock API control endpoint");
  const control = await request.post(`${mockApiUrl}/__e2e/atlas-response?mode=next-only-dawn-list`);
  expect(control.ok()).toBe(true);
  await page.route("**/api/v1/atlas/dawn/current**", (route) => route.abort());

  await page.goto("/atlas?view=list");
  const atlas = page.getByRole("region", { name: "ORNA Atlas" });
  await expect(atlas.locator(".dawn-copy strong")).toHaveText("Ridge Dawn");
  await expect(atlas.getByRole("tab", { name: "Dawn" })).toHaveAttribute("aria-selected", "true");
});

test("current-location control selects the nearest public listening site without overflowing the carousel", async ({ context, page, request }) => {
  if (!process.env.E2E_API_URL) {
    const control = await request.post(`${mockApiUrl}/__e2e/atlas-response?mode=carousel-boundaries`);
    expect(control.ok()).toBeTruthy();
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await context.grantPermissions(["geolocation"], { origin: "http://127.0.0.1:3100" });
  await context.setGeolocation({ latitude: 57.42, longitude: 22.71 });
  await page.goto("/atlas?location=first-wetland");

  const locateButton = page.getByRole("button", { name: "Use current location" });
  await expect(locateButton).toBeEnabled();
  await locateButton.press("Enter");

  const status = page.getByRole("status");
  await expect(status).toHaveText("Nearest listening location: Third Reedbed.");
  await expect(page.locator(".dawn-copy strong")).toHaveText("Third Reedbed");
  await expect(page.locator(".location-carousel").getByRole("button", { name: "Next location" })).toBeDisabled();

  const statusBox = await status.boundingBox();
  const listenBox = await page.locator(".dawn-copy").getByRole("button", { name: "Listen" }).boundingBox();
  expect(statusBox).not.toBeNull();
  expect(listenBox).not.toBeNull();
  for (const tool of await page.locator(".globe-tools button").all()) {
    const toolBox = await tool.boundingBox();
    expect(toolBox).not.toBeNull();
    expect(boxesOverlap(toolBox!, statusBox!)).toBe(false);
    expect(boxesOverlap(toolBox!, listenBox!)).toBe(false);
  }
});

test("a denied location request stays clear of the mobile Listen control", async ({ page, context }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await context.clearPermissions();
  await page.goto("/atlas");

  await page.getByRole("button", { name: "Use current location" }).click();
  const status = page.getByRole("status");
  await expect(status).toContainText("denied location access");

  const listen = page.locator(".dawn-copy").getByRole("button", { name: "Listen" });
  const [statusBox, listenBox] = await Promise.all([status.boundingBox(), listen.boundingBox()]);
  expect(statusBox).not.toBeNull();
  expect(listenBox).not.toBeNull();
  expect(boxesOverlap(statusBox!, listenBox!)).toBe(false);
  await listen.click();
  await expect(page.locator("#atlas-session-player")).toBeVisible();
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
  expect(await controls.count()).toBeGreaterThanOrEqual(8);

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

test("an empty time filter clears the unrelated selected location", async ({ page }) => {
  await page.goto("/atlas");
  await page.getByRole("tab", { name: "Day", exact: true }).click();

  await expect(page.getByText("No locations in this time window.")).toBeVisible();
  await expect(page.locator(".dawn-copy").getByText("No location selected", { exact: true })).toBeVisible();
  await expect(page.locator(".dawn-copy").getByRole("button", { name: "Listen", exact: true })).toBeDisabled();
  await expect(page.locator(".dawn-copy").getByText("Pine Marsh", { exact: true })).toHaveCount(0);
});

test("session search synchronizes the atlas to the result location", async ({ page, request }) => {
  test.skip(Boolean(process.env.E2E_API_URL), "requires the deterministic mock API control endpoint");
  expect((await request.post(`${mockApiUrl}/__e2e/atlas-response?mode=multiple-dawn`)).ok()).toBeTruthy();
  expect((await request.post(`${mockApiUrl}/__e2e/search-response?mode=session-pine-marsh`)).ok()).toBeTruthy();
  await page.goto("/atlas?location=ridge-dawn");
  await expect(page.locator(".dawn-copy").getByText("Ridge Dawn", { exact: true })).toBeVisible();
  await page.waitForLoadState("networkidle");

  const search = page.locator("#atlas-search");
  await search.fill("Second");
  await expect(search).toHaveValue("Second");
  await page.getByRole("button", { name: /Second Session/ }).click();

  await expect(page.locator(".dawn-copy").getByText("Pine Marsh", { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Session player" })).toBeVisible();
});

test("requested atlas location selects its actual listening mode", async ({ page, request }) => {
  test.skip(Boolean(process.env.E2E_API_URL), "requires the deterministic mock API control endpoint");
  expect((await request.post(`${mockApiUrl}/__e2e/atlas-response?mode=carousel-boundaries`)).ok()).toBeTruthy();
  await page.goto("/atlas?location=ridge-dawn");

  await expect(page.getByRole("tab", { name: "Night", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(page.locator(".dawn-copy").getByText("Ridge Dawn", { exact: true })).toBeVisible();
});

test("membership route exposes login and registration controls", async ({ page }) => {
  await page.goto("/membership");
  await expect(
    page.getByRole("heading", { level: 1, name: "Sign in or create your account" }),
  ).toBeVisible();
  await expect(page.locator("form").getByRole("button", { name: "Continue" })).toBeVisible();
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByLabel("Email address", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Password account email", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("minlength", "12");
  await expect(page.getByRole("heading", { name: "Free atlas and future membership" })).toBeVisible();
  await expect(page.getByText("Pricing has not been announced.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Frequently asked questions" })).toBeVisible();
});

test("membership registration link opens the registration form", async ({ page }) => {
  await page.goto("/membership?mode=register");

  await expect(page.getByRole("button", { name: "Create account", pressed: true })).toBeVisible();
  await expect(page.locator("form").getByRole("button", { name: "Continue" })).toBeVisible();
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("minlength", "12");
});

test("early membership intent leads to registration without claiming a reservation", async ({ page }) => {
  await page.addInitScript(() => {
    (window as typeof window & { __analytics?: unknown[] }).__analytics = [];
    window.addEventListener("orna:analytics", (event) => {
      (window as typeof window & { __analytics?: unknown[] }).__analytics?.push((event as CustomEvent).detail);
    });
  });
  await page.goto("/membership");
  await page.getByRole("button", { name: "Create an account for future membership updates" }).click();
  await expect(page.getByLabel("Password account email", { exact: true })).toBeFocused();
  await expect(page.getByText(/Interest recorded/)).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => (
    window as typeof window & { __analytics?: unknown[] }
  ).__analytics ?? [])).toEqual([
    { name: "membership_reserve_click", placement: "membership_form" },
    { name: "subscription_intent", placement: "membership_form" },
  ]);
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
  await page.getByLabel("Password account email", { exact: true }).fill("new-listener@example.com");
  await page.getByLabel("Password", { exact: true }).fill("correct horse battery staple");
  await page.locator("form").getByRole("button", { name: "Continue" }).click();

  await expect.poll(() => page.evaluate(() => (
    window as typeof window & { __analytics?: unknown[] }
  ).__analytics ?? [])).toEqual([
    {
      name: "signup_completed",
      placement: "membership_form",
    },
  ]);
  await expect(page.getByText("Membership enrollment is not open yet.")).toBeVisible();
  await expect(page.getByText(/Interest recorded/)).toHaveCount(0);
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
  await page.getByLabel("Password account email", { exact: true }).fill("member@example.com");
  await page.getByLabel("Password", { exact: true }).fill("correct horse battery staple");
  await page.locator("form").getByRole("button", { name: "Continue" }).click();

  await expect(page.getByRole("heading", { name: "member@example.com" })).toBeVisible();
  await expect(page.getByText("Member sessions unlocked")).toBeVisible();
  await expect(page.getByText("active", { exact: true })).toBeVisible();
});

test("members-only atlas point is visibly locked and opens a truthful soft paywall on selection", async ({ page, request }) => {
  test.skip(Boolean(process.env.E2E_API_URL), "requires the deterministic mock API control endpoint");
  const control = await request.post(`${mockApiUrl}/__e2e/atlas-response?mode=locked-point`);
  expect(control.ok()).toBeTruthy();
  await page.addInitScript(() => {
    (window as typeof window & { __analytics?: unknown[] }).__analytics = [];
    window.addEventListener("orna:analytics", (event) => {
      (window as typeof window & { __analytics?: unknown[] }).__analytics?.push((event as CustomEvent).detail);
    });
  });

  await page.goto("/");
  await page.getByRole("tab", { name: "Night" }).click();
  const lockedPoint = page.locator(".location-card", { hasText: "Members Cove" });
  await expect(lockedPoint).toContainText("🔒");
  await lockedPoint.click();

  const dialog = page.getByRole("dialog", { name: /Members-only soundscape/i });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText(/a free ORNA account does not unlock this recording/i);
  await expect(dialog.getByRole("link", { name: "Create a free account" })).toHaveAttribute(
    "href",
    "/membership?mode=register",
  );
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(lockedPoint).toBeFocused();
  await expect.poll(() => page.evaluate(() => (
    (window as typeof window & { __analytics?: Array<{ name?: string }> }).__analytics?.map((event) => event.name) ?? []
  ))).toContain("paywall_dismissed");
});

test("free signup from a locked recording stays on the membership explanation", async ({ page, request }) => {
  test.skip(Boolean(process.env.E2E_API_URL), "requires the deterministic mock API control endpoint");
  const control = await request.post(`${mockApiUrl}/__e2e/atlas-response?mode=locked-point`);
  expect(control.ok()).toBeTruthy();
  await page.route("**/api/v1/auth/register", async (route) => {
    await route.fulfill({
      status: 201,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: "50000000-0000-4000-8000-000000000003",
        email: "free-listener@example.com",
        role: "member",
        is_active: true,
        created_at: "2026-07-22T00:00:00Z",
      }),
    });
  });

  await page.goto("/");
  await page.getByRole("tab", { name: "Night" }).click();
  await page.locator(".location-card", { hasText: "Members Cove" }).click();
  const signupLink = page.getByRole("dialog", { name: /Members-only soundscape/i })
    .getByRole("link", { name: "Create a free account" });
  await expect(signupLink).toHaveAttribute("href", "/membership?mode=register");
  await page.goto("/membership?mode=register");
  await expect(page).toHaveURL(/\/membership\?mode=register$/);

  await page.getByLabel("Password account email", { exact: true }).fill("free-listener@example.com");
  await page.getByLabel("Password", { exact: true }).fill("correct horse battery staple");
  await page.locator("form").getByRole("button", { name: "Continue" }).click();

  await expect(page).toHaveURL(/\/membership\?mode=register$/);
  await expect(page.getByText("Membership enrollment is not open yet.")).toBeVisible();
});

test("entitled atlas listener can open a members-only session", async ({ page, request }) => {
  test.skip(Boolean(process.env.E2E_API_URL), "requires the deterministic mock API control endpoint");
  const control = await request.post(`${mockApiUrl}/__e2e/atlas-response?mode=locked-point`);
  expect(control.ok()).toBeTruthy();
  const publicSession = await (await request.get(`${mockApiUrl}/api/v1/sessions/first-session`)).json();
  await page.route("**/api/v1/sessions/members-cove-long-form", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      ...publicSession,
      id: "20000000-0000-4000-8000-000000000011",
      slug: "members-cove-long-form",
      title: "Members Cove Long Form",
      access_level: "members_only",
      location: { ...publicSession.location, name: "Members Cove", slug: "members-cove" },
    }),
  }));

  await page.goto("/");
  await page.getByRole("tab", { name: "Night" }).click();
  await page.locator(".location-card", { hasText: "Members Cove" }).click();

  await expect(
    page.getByRole("region", { name: "Session player" }).getByRole("heading", { name: "Members Cove" }),
  ).toBeVisible();
  await expect(page.getByRole("dialog", { name: /Members-only soundscape/i })).toHaveCount(0);
});

test("members-only detail refreshes an expired access cookie before authorization", async ({ page, request }) => {
  test.skip(Boolean(process.env.E2E_API_URL), "requires the deterministic mock API control endpoint");
  const control = await request.post(`${mockApiUrl}/__e2e/atlas-response?mode=locked-point`);
  expect(control.ok()).toBeTruthy();
  const publicSession = await (await request.get(`${mockApiUrl}/api/v1/sessions/first-session`)).json();
  let details = 0;
  let refreshes = 0;
  await page.route("**/api/v1/auth/refresh", async (route) => {
    refreshes += 1;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ access_token: "renewed" }) });
  });
  await page.route("**/api/v1/sessions/members-cove-long-form", (route) => {
    details += 1;
    return route.fulfill({
      status: details === 1 ? 401 : 200,
      contentType: "application/json",
      body: JSON.stringify(details === 1 ? { detail: "Access token expired" } : {
        ...publicSession,
        id: "20000000-0000-4000-8000-000000000011",
        slug: "members-cove-long-form",
        title: "Members Cove Long Form",
        access_level: "members_only",
        location: { ...publicSession.location, name: "Members Cove", slug: "members-cove" },
      }),
    });
  });

  await page.goto("/");
  await page.getByRole("tab", { name: "Night" }).click();
  await page.locator(".location-card", { hasText: "Members Cove" }).click();

  await expect.poll(() => refreshes).toBe(1);
  await expect.poll(() => details).toBe(2);
  await expect(
    page.getByRole("region", { name: "Session player" }).getByRole("heading", { name: "Members Cove" }),
  ).toBeVisible();
});

test("direct session route refreshes expired access before rendering detail", async ({ page, request }) => {
  test.skip(Boolean(process.env.E2E_API_URL), "requires the deterministic mock API control endpoint");
  const control = await request.post("http://127.0.0.1:4010/__e2e/session-detail-auth?mode=expired-until-refresh");
  expect(control.ok()).toBeTruthy();

  await page.goto("/sessions/first-session");
  await expect(page.getByRole("heading", { name: "First Session", level: 1 })).toBeVisible();
  await expect(page.getByText("Session unavailable")).toHaveCount(0);
});

test("direct hidden member route retries a privacy-preserving SSR 404 after refresh", async ({ page, request }) => {
  test.skip(Boolean(process.env.E2E_API_URL), "requires the deterministic mock API control endpoint");
  const control = await request.post(`${mockApiUrl}/__e2e/session-detail-auth?mode=hidden-until-refresh`);
  expect(control.ok()).toBeTruthy();

  await page.goto("/sessions/first-session");

  await expect(page.getByRole("heading", { name: "First Session" })).toBeVisible();
  await expect(page.getByText("Session not found")).toHaveCount(0);
  const stateResponse = await request.get(`${mockApiUrl}/__e2e/session-detail-auth`);
  expect(stateResponse.ok()).toBeTruthy();
  expect(await stateResponse.json()).toEqual({
    detail_reads: 3,
    refresh_calls: 1,
    state: "ok",
  });
});

test("globe exposes accessible bounded zoom and reset controls", async ({ page, request }) => {
  if (!process.env.E2E_API_URL) {
    const control = await request.post(`${mockApiUrl}/__e2e/atlas-response?mode=valid-optional-point`);
    expect(control.ok()).toBeTruthy();
  }
  await page.goto("/atlas");
  const controls = page.getByRole("group", { name: "Globe zoom controls" });
  const stage = page.getByLabel("Interactive Cesium globe");
  await expect(stage).toHaveAttribute("data-inertia-spin", "0.9");
  await expect(stage).toHaveAttribute("data-inertia-zoom", "0.8");
  await expect(stage).toHaveAttribute("data-marker-drag-threshold", "8");
  await expect(stage).toHaveAttribute("data-pole-clamp", "z-axis");
  await expect(stage).toHaveAttribute("data-touch-controls", "native");
  await expect(stage).toHaveAttribute("data-zoom-to-cursor", "native");
  await expect(page.locator(".cesium-host")).toHaveCSS("cursor", "grab");
  await expect(page.locator(".globe-stage")).toHaveCSS("touch-action", "none");
  await expect(controls.getByRole("button", { name: "Zoom in" })).toBeVisible();
  await expect(controls.getByRole("button", { name: "Zoom out" })).toBeVisible();
  await expect(controls.getByRole("button", { name: "Reset globe" })).toBeVisible();
  for (const name of ["Zoom in", "Zoom out", "Reset globe"]) {
    const box = await controls.getByRole("button", { name }).boundingBox();
    expect(box?.width).toBeGreaterThanOrEqual(44);
    expect(box?.height).toBeGreaterThanOrEqual(44);
  }
  await controls.getByRole("button", { name: "Zoom in" }).click();
  await controls.getByRole("button", { name: "Zoom out" }).click();
  await controls.getByRole("button", { name: "Reset globe" }).click();
  await expect(page.locator(".cesium-widget canvas")).toBeVisible();
});

test("mobile location carousel stops at both finite boundaries", async ({ page, request }) => {
  test.skip(Boolean(process.env.E2E_API_URL), "requires the deterministic mock API control endpoint");
  const control = await request.post(`${mockApiUrl}/__e2e/atlas-response?mode=carousel-boundaries`);
  expect(control.ok()).toBeTruthy();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/atlas?location=first-wetland");
  const carousel = page.locator(".location-carousel");
  const previous = carousel.getByRole("button", { name: "Previous locations" });
  const next = carousel.getByRole("button", { name: "Next locations" });
  for (const mode of ["Dawn", "Day", "Dusk", "Night"]) {
    await page.getByRole("tab", { name: mode, exact: true }).click();
    await page.waitForTimeout(150);
    if (await next.isEnabled()) break;
  }
  await expect(previous).toBeDisabled();
  await expect(next).toBeEnabled();
  await expect(carousel.getByText("First Wetland", { exact: true })).toBeVisible();
  await next.click();
  await expect(carousel.getByText("Ridge Dawn", { exact: true })).toBeVisible();
  await expect(next).toBeDisabled();
  await previous.click();
  await expect(carousel.getByText("First Wetland", { exact: true })).toBeVisible();
  await expect(previous).toBeDisabled();

  await page.evaluate(() => window.dispatchEvent(new CustomEvent("orna:open-session", {
    detail: { locationSlug: "third-reedbed", sessionSlug: "second-session" },
  })));
  await expect(carousel.getByText("Third Reedbed", { exact: true })).toBeVisible();
  await expect(next).toBeDisabled();
});

test("favorite intent keeps anonymous listening open and offers a sign-in return path", async ({ page }) => {
  await page.route("**/api/v1/users/me/favorites**", (route) => route.fulfill({
    status: 401,
    contentType: "application/json",
    body: JSON.stringify({ detail: "Authentication is required" }),
  }));
  await page.goto("/sessions/first-session");
  await expect(page.getByRole("img", { name: "No field photo available" })).toBeVisible();
  for (const value of ["42 m", "12.5 °C", "8.2 km/h", "73%", "Waxing crescent"]) {
    await expect(page.getByText(value, { exact: true })).toBeVisible();
  }
  await page.getByRole("button", { name: "Save recording" }).click();
  const status = page.getByRole("status").filter({ hasText: "Sign in or create a free account" });
  await expect(status).toContainText("Sign in or create a free account");
  await expect(status.getByRole("link", { name: "Sign in" })).toHaveAttribute(
    "href",
    "/membership?mode=login&returnTo=%2Fsessions%2Ffirst-session",
  );
  await expect(page.getByRole("button", { name: "Play session" })).toBeVisible();
});

test("password sign-in clears anonymous account cache and restores the session return path", async ({ page }) => {
  let authenticated = false;
  let anonymousFavoriteReads = 0;
  let authenticatedFavoriteReads = 0;
  await page.route("**/api/v1/users/me/favorites*", async (route) => {
    if (route.request().method() !== "GET") {
      await route.fulfill({ status: authenticated ? 200 : 401, contentType: "application/json", body: JSON.stringify({ is_favorite: true }) });
      return;
    }
    if (!authenticated) {
      anonymousFavoriteReads += 1;
      await route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Authentication is required" }) });
      return;
    }
    authenticatedFavoriteReads += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ session_id: "20000000-0000-4000-8000-000000000001", is_favorite: false }),
    });
  });
  await page.route("**/api/v1/auth/login", async (route) => {
    const response = await route.fetch();
    authenticated = true;
    await route.fulfill({ response });
  });

  await page.goto("/sessions/first-session");
  await expect.poll(() => anonymousFavoriteReads).toBe(1);
  await page.getByRole("button", { name: "Save recording" }).click();
  await page.getByRole("status").getByRole("link", { name: "Sign in" }).click();
  await page.getByLabel("Password account email").fill("member@example.com");
  const passwordInput = page.getByLabel("Password", { exact: true });
  await passwordInput.fill("secret-password");
  await page.locator("form.auth-form").filter({ has: passwordInput })
    .getByRole("button", { name: "Continue" }).click();

  await expect(page).toHaveURL(/\/sessions\/first-session$/);
  await expect.poll(() => authenticatedFavoriteReads).toBeGreaterThanOrEqual(1);
  await expect(page.getByRole("button", { name: "Save recording" })).toBeEnabled();
});

test("password sign-in invalidates an old-account mutation before the login request settles", async ({ page }) => {
  let accountBoundaries = 0;
  let favoriteWrites = 0;
  let historyWrites = 0;
  let refreshes = 0;
  let releaseFavorite!: () => void;
  let releaseHistory!: () => void;
  let releaseLogin!: () => void;
  const favoriteStarted = new Promise<void>((resolve) => {
    releaseFavorite = resolve;
  });
  const historyMaySettle = new Promise<void>((resolve) => {
    releaseHistory = resolve;
  });
  const loginMaySettle = new Promise<void>((resolve) => {
    releaseLogin = resolve;
  });
  let notifyFavoriteStarted!: () => void;
  let notifyHistoryStarted!: () => void;
  let notifyLoginStarted!: () => void;
  const favoriteRequestStarted = new Promise<void>((resolve) => {
    notifyFavoriteStarted = resolve;
  });
  const historyRequestStarted = new Promise<void>((resolve) => {
    notifyHistoryStarted = resolve;
  });
  const loginRequestStarted = new Promise<void>((resolve) => {
    notifyLoginStarted = resolve;
  });
  await page.addInitScript(() => {
    Object.assign(window, { __accountBoundaries: 0, __listeningProgressContinuations: 0 });
    window.addEventListener("orna:account-auth-changed", () => {
      const target = window as typeof window & { __accountBoundaries?: number };
      target.__accountBoundaries = (target.__accountBoundaries ?? 0) + 1;
    });
    window.addEventListener("orna:test:listening-progress-continuation", () => {
      const target = window as typeof window & { __listeningProgressContinuations?: number };
      target.__listeningProgressContinuations = (target.__listeningProgressContinuations ?? 0) + 1;
    });
    Object.defineProperty(HTMLMediaElement.prototype, "play", {
      configurable: true,
      value: async function play() { this.dispatchEvent(new Event("play")); },
    });
    Object.defineProperty(HTMLMediaElement.prototype, "pause", {
      configurable: true,
      value: function pause() { this.dispatchEvent(new Event("pause")); },
    });
  });
  await page.route("**/api/v1/users/me/favorites**", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
      return;
    }
    favoriteWrites += 1;
    notifyFavoriteStarted();
    await favoriteStarted;
    await route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Expired old-account credentials" }),
    });
  });
  await page.route("**/api/v1/auth/refresh", async (route) => {
    refreshes += 1;
    await route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Expired" }) });
  });
  await page.route("**/api/v1/users/me/listening-history/**", async (route) => {
    historyWrites += 1;
    if (historyWrites === 1) notifyHistoryStarted();
    await historyMaySettle;
    await route.fulfill({
      status: historyWrites === 1 ? 401 : 200,
      contentType: "application/json",
      body: JSON.stringify(historyWrites === 1 ? { detail: "Expired old-account progress" } : {}),
    });
  });
  await page.route("**/api/v1/auth/login", async (route) => {
    notifyLoginStarted();
    await loginMaySettle;
    const response = await route.fetch();
    await route.fulfill({ response });
  });
  await page.route("**/playback-grants", async (route) => {
    await route.fulfill({
      status: 200,
      headers: {
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Origin": "http://127.0.0.1:3100",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        session_id: "20000000-0000-4000-8000-000000000001",
        status: "ready",
        stream_url: "/mock-audio/account-boundary.mp3",
        expires_at: new Date(Date.now() + 600_000).toISOString(),
        refresh_after_seconds: 600,
      }),
    });
  });

  await page.goto("/sessions/first-session");
  const saveButton = page.getByRole("button", { name: "Save recording" });
  await expect(saveButton).toBeEnabled();
  const mutationContinuations = await page.evaluate(() => (
    (window as typeof window & { __favoriteContinuations?: { mutation: number } }).__favoriteContinuations?.mutation ?? 0
  ));
  await saveButton.click();
  await favoriteRequestStarted;
  await page.getByRole("button", { name: "Play session" }).click();
  await historyRequestStarted;
  await page.getByRole("button", { name: "Pause playback" }).click();

  accountBoundaries = await page.evaluate(() => (
    (window as typeof window & { __accountBoundaries?: number }).__accountBoundaries ?? 0
  ));
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("link", { name: "Use password or social sign-in" }).click();
  await page.getByLabel("Password account email").fill("other-member@example.com");
  const passwordInput = page.getByLabel("Password", { exact: true });
  await passwordInput.fill("secret-password");
  await page.locator("form.auth-form").filter({ has: passwordInput })
    .getByRole("button", { name: "Continue" }).click();
  await loginRequestStarted;
  await expect.poll(() => page.evaluate(() => (
    (window as typeof window & { __accountBoundaries?: number }).__accountBoundaries ?? 0
  ))).toBeGreaterThan(accountBoundaries);
  const boundariesAfterLoginStarted = await page.evaluate(() => (
    (window as typeof window & { __accountBoundaries?: number }).__accountBoundaries ?? 0
  ));
  const listeningContinuations = await page.evaluate(() => (
    (window as typeof window & { __listeningProgressContinuations?: number }).__listeningProgressContinuations ?? 0
  ));

  releaseFavorite();
  await expect.poll(() => page.evaluate(() => (
    (window as typeof window & { __favoriteContinuations?: { mutation: number } }).__favoriteContinuations?.mutation ?? 0
  ))).toBe(mutationContinuations + 1);
  expect(favoriteWrites).toBe(1);
  expect(refreshes).toBe(0);

  releaseLogin();
  await expect.poll(() => page.evaluate(() => (
    (window as typeof window & { __accountBoundaries?: number }).__accountBoundaries ?? 0
  ))).toBeGreaterThan(boundariesAfterLoginStarted);
  releaseHistory();
  await expect.poll(() => page.evaluate(() => (
    (window as typeof window & { __listeningProgressContinuations?: number }).__listeningProgressContinuations ?? 0
  ))).toBe(listeningContinuations);
  expect(historyWrites).toBe(1);
});

test("account library refreshes an expired access cookie before becoming anonymous", async ({ page }) => {
  let favoriteReads = 0;
  let refreshes = 0;
  await page.route("**/api/v1/users/me/favorites*", async (route) => {
    favoriteReads += 1;
    if (favoriteReads === 1) {
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Expired" }),
      });
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
  });
  await page.route("**/api/v1/auth/refresh", async (route) => {
    refreshes += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        access_token: "refreshed",
        token_type: "bearer",
        expires_at: "2026-07-23T00:00:00Z",
      }),
    });
  });

  await page.goto("/sessions/first-session");

  await expect.poll(() => refreshes).toBe(1);
  await expect.poll(() => favoriteReads).toBeGreaterThanOrEqual(2);
  await expect(page.getByRole("button", { name: "Save recording" })).toBeEnabled();
});

test("parallel library reads share one refresh-token rotation", async ({ page }) => {
  let refreshes = 0;
  let favoritesReads = 0;
  let historyReads = 0;
  await page.route("**/api/v1/auth/refresh", async (route) => {
    refreshes += 1;
    await new Promise((resolve) => setTimeout(resolve, 100));
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ access_token: "renewed" }) });
  });
  await page.route("**/api/v1/users/me/favorites**", (route) => {
    favoritesReads += 1;
    return route.fulfill({
      status: favoritesReads === 1 ? 401 : 200,
      contentType: "application/json",
      body: JSON.stringify(favoritesReads === 1 ? { detail: "Access token expired" } : []),
    });
  });
  await page.route("**/api/v1/users/me/listening-history**", (route) => {
    historyReads += 1;
    return route.fulfill({
      status: historyReads === 1 ? 401 : 200,
      contentType: "application/json",
      body: JSON.stringify(historyReads === 1 ? { detail: "Access token expired" } : []),
    });
  });

  await page.goto("/library");

  await expect(page.getByRole("heading", { name: "Your Library" })).toBeVisible();
  await expect.poll(() => refreshes).toBe(1);
  await expect.poll(() => favoritesReads).toBe(2);
  await expect.poll(() => historyReads).toBe(2);
});

test("password sign-in aborts a hung older refresh before installing the new account", async ({ page }) => {
  let favoriteReads = 0;
  let loginRequests = 0;
  let loginCompleted = false;
  let refreshHandlerSettled = false;
  let releaseRefresh!: () => void;
  let notifyRefreshStarted!: () => void;
  let notifyLoginStarted!: () => void;
  const refreshMaySettle = new Promise<void>((resolve) => {
    releaseRefresh = resolve;
  });
  const refreshStarted = new Promise<void>((resolve) => {
    notifyRefreshStarted = resolve;
  });
  const loginStarted = new Promise<void>((resolve) => {
    notifyLoginStarted = resolve;
  });
  await page.addInitScript(() => {
    Object.assign(window, { __accountBoundaries: 0 });
    window.addEventListener("orna:account-auth-changed", () => {
      const target = window as typeof window & { __accountBoundaries?: number };
      target.__accountBoundaries = (target.__accountBoundaries ?? 0) + 1;
    });
  });
  await page.route("**/api/v1/users/me/favorites**", async (route) => {
    favoriteReads += 1;
    await route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Old access cookie expired" }),
    });
  });
  await page.route("**/api/v1/users/me/listening-history**", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: "[]",
  }));
  await page.route("**/api/v1/auth/refresh", async (route) => {
    notifyRefreshStarted();
    await refreshMaySettle;
    try {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: { "Set-Cookie": "orna_access=account-a; Path=/; SameSite=Lax" },
        body: JSON.stringify({ access_token: "old-account-token" }),
      });
    } catch {
      // The browser is expected to cancel this intercepted request.
    } finally {
      refreshHandlerSettled = true;
    }
  });
  await page.route("**/api/v1/auth/login", async (route) => {
    loginRequests += 1;
    notifyLoginStarted();
    await page.context().addCookies([{ name: "orna_access", value: "account-b", domain: "localhost", path: "/" }]);
    loginCompleted = true;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        access_token: "e2e-token",
        token_type: "bearer",
        expires_at: "2026-07-23T15:00:00Z",
        user: {
          id: "50000000-0000-4000-8000-000000000001",
          email: "member@example.com",
          role: "member",
          is_active: true,
          created_at: "2026-07-22T07:00:00Z",
        },
      }),
    });
  });
  await page.route("**/api/v1/users/me", async (route) => {
    if (!loginCompleted) {
      await route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Not authenticated" }) });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "50000000-0000-4000-8000-000000000002",
        email: "other-member@example.com",
        role: "member",
        is_active: true,
        created_at: "2026-07-23T00:00:00Z",
      }),
    });
  });
  await page.route("**/api/v1/memberships/me", (route) => route.fulfill({
    status: loginCompleted ? 200 : 401,
    contentType: "application/json",
    body: JSON.stringify(loginCompleted
      ? { plan: "early_access", status: "active", is_entitled: true }
      : { detail: "Not authenticated" }),
  }));

  await page.goto("/library");
  await refreshStarted;
  const boundariesBeforeLogin = await page.evaluate(() => (
    (window as typeof window & { __accountBoundaries?: number }).__accountBoundaries ?? 0
  ));
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("link", { name: "Use password or social sign-in" }).click();
  await page.getByLabel("Password account email").fill("other-member@example.com");
  const passwordInput = page.getByLabel("Password", { exact: true });
  await passwordInput.fill("secret-password");
  await page.locator("form.auth-form").filter({ has: passwordInput })
    .getByRole("button", { name: "Continue" }).click();
  await expect.poll(() => page.evaluate(() => (
    (window as typeof window & { __accountBoundaries?: number }).__accountBoundaries ?? 0
  ))).toBeGreaterThan(boundariesBeforeLogin);
  await loginStarted;
  expect(loginRequests).toBe(1);
  releaseRefresh();
  await expect.poll(() => refreshHandlerSettled).toBe(true);
  expect(favoriteReads).toBe(1);
  await expect(page.getByRole("heading", { name: "Your account" })).toBeVisible();
  const accessCookie = (await page.context().cookies()).find((cookie) => cookie.name === "orna_access");
  expect(accessCookie?.value).toBe("account-b");
});

test("an authentication boundary discards a pending playback grant success", async ({ page }) => {
  let grantRequests = 0;
  let grantHandlerSettled = false;
  let releaseGrant!: () => void;
  const grantMaySettle = new Promise<void>((resolve) => {
    releaseGrant = resolve;
  });
  await page.addInitScript(() => {
    Object.assign(window, { __playerAnalytics: [] });
    window.addEventListener("orna:analytics", (event) => {
      const detail = (event as CustomEvent<{ name?: string }>).detail;
      if (detail?.name) {
        (window as typeof window & { __playerAnalytics?: string[] }).__playerAnalytics?.push(detail.name);
      }
    });
  });
  await page.route("**/api/v1/sessions/*/playback-grants", async (route) => {
    grantRequests += 1;
    await grantMaySettle;
    const sessionId = new URL(route.request().url()).pathname.split("/").at(-2) ?? "stale-session";
    try {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: sessionId,
          status: "ready",
          stream_url: "/mock-audio/stale-account.mp3",
          expires_at: "2030-01-01T00:00:00Z",
          refresh_after_seconds: 60,
        }),
      });
    } catch {
      // The account boundary is expected to abort this intercepted request.
    } finally {
      grantHandlerSettled = true;
    }
  });
  await page.route("**/api/v1/users/me/favorites**", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
      return;
    }
    await route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Old account expired" }),
    });
  });
  await page.route("**/api/v1/auth/refresh", (route) => route.fulfill({
    status: 401,
    contentType: "application/json",
    body: JSON.stringify({ detail: "Refresh expired" }),
  }));

  await page.goto("/");
  await page.locator(".location-card", { hasText: "Pine Marsh" }).click();
  const panel = page.locator("#atlas-session-player");
  await panel.getByRole("button", { name: "Play session" }).click();
  await expect.poll(() => grantRequests).toBe(1);
  await panel.getByRole("button", { name: "Save recording" }).click();
  await expect(panel.getByRole("link", { name: "Sign in" })).toBeVisible();

  releaseGrant();
  await expect.poll(() => grantHandlerSettled).toBe(true);
  await expect(panel.getByRole("button", { name: "Play session" })).toBeVisible();
  await expect(panel.getByRole("button", { name: "Pause playback" })).toHaveCount(0);
  expect(await page.evaluate(() => (
    (window as typeof window & { __playerAnalytics?: string[] }).__playerAnalytics ?? []
  ))).not.toContain("player_play");
});

test("email magic-link signup preserves the internal listening return path", async ({ page }) => {
  await page.goto("/membership?mode=register&returnTo=%2Fsessions%2Ffirst-session");
  await page.getByLabel("Email address", { exact: true }).fill("listener@example.com");
  const requestPromise = page.waitForRequest((request) => request.url().includes("/api/v1/auth/magic-link/request"));
  await page.getByRole("button", { name: "Email me a sign-in link" }).click();
  const request = await requestPromise;
  expect(request.postDataJSON()).toEqual({
    email: "listener@example.com",
    return_to: "/sessions/first-session",
  });
  await expect(page.getByRole("status").filter({ hasText: "Check your email" })).toContainText(
    "expires in 15 minutes",
  );
});

test("magic-link signup completion is recorded after returning to a session", async ({ page }) => {
  const analytics: Array<Record<string, unknown>> = [];
  await page.route("**/api/v1/analytics/events", async (route) => {
    analytics.push(route.request().postDataJSON());
    await route.fulfill({ status: 202, headers: { "Content-Type": "application/json" }, body: "{}" });
  });
  await page.goto("/sessions/first-session?magic=signup");
  await expect.poll(() => analytics).toEqual([
    { name: "signup_completed", placement: "membership_form" },
  ]);
  await expect(page).toHaveURL(/\/sessions\/first-session$/);
});

test("magic-link login is not counted as a signup", async ({ page }) => {
  const analytics: Array<Record<string, unknown>> = [];
  await page.route("**/api/v1/analytics/events", async (route) => {
    analytics.push(route.request().postDataJSON());
    await route.fulfill({ status: 202, headers: { "Content-Type": "application/json" }, body: "{}" });
  });

  await page.goto("/sessions/first-session?magic=login");

  await expect(page).toHaveURL(/\/sessions\/first-session$/);
  expect(analytics).toEqual([]);
});

test("atlas session overlay keeps globe context across timeline, next, close, and mini-player", async ({ page, request }) => {
  if (!process.env.E2E_API_URL) {
    const control = await request.post(`${mockApiUrl}/__e2e/atlas-response?mode=session-navigation`);
    expect(control.ok()).toBeTruthy();
  }
  await page.addInitScript(() => {
    (window as typeof window & { __analytics?: unknown[] }).__analytics = [];
    window.addEventListener("orna:analytics", (event) => {
      (window as typeof window & { __analytics?: unknown[] }).__analytics?.push((event as CustomEvent).detail);
    });
    Object.defineProperty(HTMLMediaElement.prototype, "play", {
      configurable: true,
      value: async function play() {
        this.dispatchEvent(new Event("play"));
      },
    });
  });
  await page.goto("/atlas?location=first-wetland");
  await page.getByRole("tab", { name: "Night" }).click();
  const firstRequest = page.waitForRequest((candidate) => candidate.url().includes("/api/v1/sessions/first-session"));
  await page.locator(".location-card", { hasText: "First Wetland" }).click();
  await firstRequest;
  await expect(page.locator(".dawn-copy strong")).toHaveText("First Wetland");
  const panel = page.locator("#atlas-session-player");
  await expect(panel.getByRole("heading", { name: "Dawn Chorus" })).toBeVisible();
  const playGrant = page.waitForRequest((candidate) => candidate.url().includes("/playback-grants"));
  await panel.getByRole("button", { name: /European Robin.*2:00/ }).first().click({ position: { x: 2, y: 22 } });
  await playGrant;
  await expect(panel.locator(".session-bird-timeline li.is-active")).toContainText("European Robin");
  await expect.poll(() => page.evaluate(() => (
    (window as typeof window & { __analytics?: Array<{ name?: string }> }).__analytics?.map((event) => event.name) ?? []
  ))).toEqual(expect.arrayContaining(["timeline_species_click", "player_seek"]));
  const secondRequest = page.waitForRequest((candidate) => candidate.url().includes("/api/v1/sessions/second-session"));
  await panel.getByRole("button", { name: "Next recording" }).click();
  await secondRequest;
  await expect(panel.getByRole("button", { name: "Previous recording" })).toBeEnabled();
  await expect(page.locator(".dawn-copy strong")).toHaveText("Ridge Dawn");
  await expect(page.getByRole("complementary", { name: "Global audio player" })).toBeVisible();
  await panel.getByRole("button", { name: "Hide player" }).click();
  await expect(panel).toHaveCount(0);
  await expect(page.locator(".dawn-copy strong")).toHaveText("Ridge Dawn");
  await expect(page.getByRole("complementary", { name: "Global audio player" })).toBeVisible();
});

test("timeline seek switches grant ownership when the overlay session changes", async ({ page, request }) => {
  if (!process.env.E2E_API_URL) {
    const control = await request.post(`${mockApiUrl}/__e2e/atlas-response?mode=session-navigation`);
    expect(control.ok()).toBeTruthy();
  }
  let releaseFirstGrant: (() => void) | undefined;
  const firstGrantBarrier = new Promise<void>((resolve) => { releaseFirstGrant = resolve; });
  await page.route("**/playback-grants", async (route) => {
    if (route.request().url().includes("20000000-0000-4000-8000-000000000001")) {
      await firstGrantBarrier;
    }
    await route.continue().catch(() => undefined);
  });
  await page.addInitScript(() => {
    Object.defineProperty(HTMLMediaElement.prototype, "play", {
      configurable: true,
      value: async function play() {
        this.dispatchEvent(new Event("play"));
      },
    });
  });

  await page.goto("/atlas?location=first-wetland");
  await page.getByRole("tab", { name: "Night" }).click();
  await page.locator(".location-card", { hasText: "First Wetland" }).click();
  const panel = page.locator("#atlas-session-player");
  await expect(panel.getByRole("heading", { name: "Dawn Chorus" })).toBeVisible();
  const firstGrant = page.waitForRequest((candidate) => (
    candidate.method() === "POST"
    && candidate.url().includes("20000000-0000-4000-8000-000000000001/playback-grants")
  ));
  await panel.getByRole("slider", { name: "Playback position" }).press("End");
  await firstGrant;

  await panel.getByRole("button", { name: "Next recording" }).click();
  await expect(page.locator(".dawn-copy strong")).toHaveText("Ridge Dawn");
  const secondGrant = page.waitForResponse((candidate) => (
    candidate.request().method() === "POST"
    && candidate.url().includes("20000000-0000-4000-8000-000000000002/playback-grants")
  ));
  await panel.getByRole("slider", { name: "Playback position" }).press("End");
  await secondGrant;
  releaseFirstGrant?.();
  await page.waitForTimeout(100);

  await expect(panel.getByRole("button", { name: "Previous recording" })).toBeEnabled();
  await expect(panel.getByRole("button", { name: "Next recording" })).toBeDisabled();
  await expect(panel.getByRole("slider", { name: "Playback position" })).toHaveAttribute("aria-valuenow", "3600");
});

test("featured session remains reachable when its location is outside the current atlas window", async ({ page }) => {
  const mounted = page.waitForRequest((request) => (
    request.method() === "POST"
    && request.url().includes("/api/v1/analytics/events")
    && request.postDataJSON()?.name === "globe_view"
  ));
  await page.goto("/");
  await mounted;
  await expect(page.getByRole("region", { name: "ORNA Atlas" })).toBeVisible();
  await page.evaluate(() => {
    window.dispatchEvent(new CustomEvent("orna:open-session", {
      detail: { locationSlug: "outside-current-window", sessionSlug: "second-session" },
    }));
  });
  await expect(page).toHaveURL(/\/sessions\/second-session$/);
  await expect(page.getByRole("heading", { name: "Second Session", level: 1 })).toBeVisible();
});

test("homepage discovery supports inline preview, collections, and conversion header routes", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(HTMLMediaElement.prototype, "play", {
      configurable: true,
      value: async function play() {
        this.dispatchEvent(new Event("play"));
      },
    });
  });
  await page.goto("/");
  await expect(page.locator(".cesium-widget canvas")).toBeVisible();
  const preview = page.getByRole("button", { name: /Play preview for/ }).first();
  const grant = page.waitForRequest((candidate) => candidate.url().includes("/playback-grants"));
  await preview.click();
  await grant;
  await expect(page.getByRole("complementary", { name: "Global audio player" })).toBeVisible();
});

test("the latest popular preview wins when an earlier detail request resolves late", async ({ page, request }) => {
  test.skip(Boolean(process.env.E2E_API_URL), "requires the deterministic mock API control endpoint");
  const control = await request.post(`${mockApiUrl}/__e2e/atlas-response?mode=session-navigation`);
  expect(control.ok()).toBeTruthy();
  let releaseFirst: (() => void) | undefined;
  const firstBarrier = new Promise<void>((resolve) => { releaseFirst = resolve; });
  await page.route("**/api/v1/sessions/first-session", async (route) => {
    await firstBarrier;
    await route.continue();
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Play preview for First Wetland" }).click();
  await page.getByRole("button", { name: "Play preview for Ridge Dawn" }).click();
  const player = page.getByRole("complementary", { name: "Global audio player" });
  await expect(player).toContainText("Second Session");
  releaseFirst?.();
  await expect(player).toContainText("Second Session");
});

test("favorite loading cannot overwrite a completed same-session save", async ({ page }) => {
  let releaseInitialLoad: (() => void) | undefined;
  const initialLoadBarrier = new Promise<void>((resolve) => { releaseInitialLoad = resolve; });
  await page.route("**/api/v1/users/me/favorites**", async (route) => {
    if (route.request().method() === "GET") {
      await initialLoadBarrier;
      await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  await page.goto("/sessions/first-session");
  const save = page.getByRole("button", { name: "Save recording" });
  await expect(save).toBeDisabled();
  releaseInitialLoad?.();
  await expect(save).toBeEnabled();
  await save.click();
  await expect(page.getByRole("button", { name: "Remove from favorites" })).toHaveAttribute("aria-pressed", "true");
});

test("a favorite response for the previous session cannot update the next session", async ({ page, request }) => {
  test.skip(Boolean(process.env.E2E_API_URL), "requires the deterministic mock API control endpoint");
  const control = await request.post(`${mockApiUrl}/__e2e/atlas-response?mode=session-navigation`);
  expect(control.ok()).toBeTruthy();
  let releaseFavorite: (() => void) | undefined;
  const favoriteBarrier = new Promise<void>((resolve) => { releaseFavorite = resolve; });
  await page.route("**/api/v1/users/me/favorites**", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
      return;
    }
    await favoriteBarrier;
    await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  await page.goto("/atlas?location=first-wetland");
  await page.getByRole("tab", { name: "Night" }).click();
  await page.locator(".location-card", { hasText: "First Wetland" }).click();
  const panel = page.locator("#atlas-session-player");
  await panel.getByRole("button", { name: "Save recording" }).click();
  await panel.getByRole("button", { name: "Next recording" }).click();
  releaseFavorite?.();
  await expect(page.locator(".dawn-copy strong")).toHaveText("Ridge Dawn");
  await expect(panel.getByRole("button", { name: "Save recording" })).toHaveAttribute("aria-pressed", "false");
  await expect(panel.getByText(/Saved to your account/)).toHaveCount(0);
});

test("an external authentication boundary invalidates an in-flight favorite read", async ({ page }) => {
  let favoriteReads = 0;
  let staleReadsFulfilled = 0;
  let authBoundaryCrossed = false;
  let releaseStaleReads!: () => void;
  const staleReads = new Promise<void>((resolve) => {
    releaseStaleReads = resolve;
  });
  const favorite = {
    session: {
      id: "20000000-0000-4000-8000-000000000002",
      slug: "second-session",
      title: "Second Session",
      recorded_at: "2026-03-20T04:30:00Z",
      duration_seconds: 600,
      access_level: "public",
      location: {
        id: "10000000-0000-4000-8000-000000000001",
        slug: "pine-marsh",
        name: "Pine Marsh",
        region: "Harju County",
        habitat: "Wetland",
      },
    },
    favorited_at: "2026-07-22T07:00:00Z",
  };
  await page.route("**/api/v1/users/me/favorites**", async (route) => {
    favoriteReads += 1;
    if (!authBoundaryCrossed) {
      await staleReads;
      await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
      staleReadsFulfilled += 1;
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([favorite]) });
  });

  await page.goto("/");
  await page.locator(".location-card", { hasText: "Pine Marsh" }).click();
  await expect.poll(() => favoriteReads).toBeGreaterThan(0);
  await page.waitForTimeout(100);
  const initialReads = favoriteReads;
  authBoundaryCrossed = true;
  await page.evaluate(() => {
    window.dispatchEvent(new CustomEvent("orna:account-auth-changed", {
      detail: { state: "authenticated" },
    }));
  });
  await expect.poll(() => favoriteReads).toBeGreaterThan(initialReads);

  const panel = page.locator("#atlas-session-player");
  await expect(panel.getByRole("button", { name: "Remove from favorites" })).toHaveAttribute("aria-pressed", "true");
  const settledLoads = await page.evaluate(() => (
    (window as typeof window & { __favoriteContinuations?: { load: number } }).__favoriteContinuations?.load ?? 0
  ));
  releaseStaleReads();
  await expect.poll(() => staleReadsFulfilled).toBe(initialReads);
  await expect.poll(() => page.evaluate(() => (
    (window as typeof window & { __favoriteContinuations?: { load: number } }).__favoriteContinuations?.load ?? 0
  ))).toBe(settledLoads);
  await expect(panel.getByRole("button", { name: "Remove from favorites" })).toHaveAttribute("aria-pressed", "true");
});

test("a favorite mutation from the previous account cannot settle in the next account", async ({ page }) => {
  let accountBoundaryCrossed = false;
  let favoriteReads = 0;
  let removeRequests = 0;
  let removeResponses = 0;
  let releaseRemove!: () => void;
  let releaseNextAccountRead!: () => void;
  const removeBarrier = new Promise<void>((resolve) => {
    releaseRemove = resolve;
  });
  const nextAccountReadBarrier = new Promise<void>((resolve) => {
    releaseNextAccountRead = resolve;
  });
  const favorite = {
    session: {
      id: "20000000-0000-4000-8000-000000000002",
      slug: "second-session",
      title: "Second Session",
      recorded_at: "2026-03-20T04:30:00Z",
      duration_seconds: 600,
      access_level: "public",
      location: {
        id: "10000000-0000-4000-8000-000000000001",
        slug: "pine-marsh",
        name: "Pine Marsh",
        region: "Harju County",
        habitat: "Wetland",
      },
    },
    favorited_at: "2026-07-22T07:00:00Z",
  };
  await page.route("**/api/v1/users/me/favorites**", async (route) => {
    if (route.request().method() === "GET") {
      favoriteReads += 1;
      if (accountBoundaryCrossed) await nextAccountReadBarrier;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([favorite]) });
      return;
    }
    if (route.request().method() === "DELETE") {
      removeRequests += 1;
      await removeBarrier;
      await route.fulfill({ status: 204, body: "" });
      removeResponses += 1;
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });

  await page.goto("/");
  await page.locator(".location-card", { hasText: "Pine Marsh" }).click();
  const panel = page.locator("#atlas-session-player");
  const remove = panel.getByRole("button", { name: "Remove from favorites" });
  await expect(remove).toBeEnabled();
  await remove.click();
  await expect.poll(() => removeRequests).toBe(1);

  const readsBeforeBoundary = favoriteReads;
  accountBoundaryCrossed = true;
  await page.evaluate(() => {
    window.dispatchEvent(new CustomEvent("orna:account-auth-changed", {
      detail: { state: "authenticated" },
    }));
  });
  await expect.poll(() => favoriteReads).toBeGreaterThan(readsBeforeBoundary);

  const save = panel.getByRole("button", { name: "Save recording" });
  await expect(save).toBeDisabled();
  const settledMutations = await page.evaluate(() => (
    (window as typeof window & { __favoriteContinuations?: { mutation: number } }).__favoriteContinuations?.mutation ?? 0
  ));
  releaseRemove();
  await expect.poll(() => removeResponses).toBe(1);
  await expect.poll(() => page.evaluate(() => (
    (window as typeof window & { __favoriteContinuations?: { mutation: number } }).__favoriteContinuations?.mutation ?? 0
  ))).toBe(settledMutations);
  await expect(save).toBeDisabled();
  await expect(panel.getByText("Removed from your account.")).toHaveCount(0);

  releaseNextAccountRead();
  await expect(remove).toBeEnabled();
  await expect(remove).toHaveAttribute("aria-pressed", "true");
  await expect(panel.getByText("Removed from your account.")).toHaveCount(0);
});

test("a favorite mutation cannot retry after another request crosses the account epoch", async ({ page }) => {
  let favoriteMutations = 0;
  let refreshRequests = 0;
  let historyRequests = 0;
  let releaseMutation!: () => void;
  const mutationBarrier = new Promise<void>((resolve) => {
    releaseMutation = resolve;
  });
  await page.addInitScript(() => {
    Object.defineProperty(HTMLMediaElement.prototype, "play", {
      configurable: true,
      value: async function play() { this.dispatchEvent(new Event("play")); },
    });
  });
  await page.route("**/api/v1/auth/refresh", async (route) => {
    refreshRequests += 1;
    await route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Authentication is required" }),
    });
  });
  await page.route("**/api/v1/users/me/listening-history/**", async (route) => {
    historyRequests += 1;
    await route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Authentication is required" }),
    });
  });
  await page.route("**/api/v1/users/me/favorites**", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([{
          session: { id: "20000000-0000-4000-8000-000000000002" },
          favorited_at: "2026-07-22T07:00:00Z",
        }]),
      });
      return;
    }
    favoriteMutations += 1;
    await mutationBarrier;
    await route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Authentication is required" }),
    });
  });

  await page.goto("/");
  await page.locator(".location-card", { hasText: "Pine Marsh" }).click();
  const panel = page.locator("#atlas-session-player");
  await panel.getByRole("button", { name: "Remove from favorites" }).click();
  await expect.poll(() => favoriteMutations).toBe(1);
  await panel.getByRole("button", { name: "Play session" }).click();
  await expect.poll(() => historyRequests).toBe(1);
  await expect.poll(() => refreshRequests).toBe(1);
  await expect(panel.getByRole("button", { name: "Save recording" })).toHaveAttribute("aria-pressed", "false");

  const settledMutations = await page.evaluate(() => (
    (window as typeof window & { __favoriteContinuations?: { mutation: number } }).__favoriteContinuations?.mutation ?? 0
  ));
  releaseMutation();
  await expect.poll(() => page.evaluate(() => (
    (window as typeof window & { __favoriteContinuations?: { mutation: number } }).__favoriteContinuations?.mutation ?? 0
  ))).toBe(settledMutations);
  await expect.poll(() => favoriteMutations).toBe(1);
  await expect.poll(() => refreshRequests).toBe(1);
  await expect(panel.getByRole("button", { name: "Save recording" })).toHaveAttribute("aria-pressed", "false");
  await expect(panel.getByText("Removed from your account.")).toHaveCount(0);
});

test("a favorite mutation cannot retry or emit analytics after its player unmounts", async ({ page }) => {
  let addRequests = 0;
  let addResponses = 0;
  let refreshRequests = 0;
  let releaseAdd!: () => void;
  const addBarrier = new Promise<void>((resolve) => {
    releaseAdd = resolve;
  });
  await page.addInitScript(() => {
    const analytics: string[] = [];
    Object.assign(window, { __favoriteAnalytics: analytics });
    window.addEventListener("orna:analytics", ((event: CustomEvent<{ name?: string }>) => {
      if (event.detail.name) analytics.push(event.detail.name);
    }) as EventListener);
  });
  await page.route("**/api/v1/auth/refresh", async (route) => {
    refreshRequests += 1;
    await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  await page.route("**/api/v1/users/me/favorites**", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
      return;
    }
    if (route.request().method() === "PUT") {
      addRequests += 1;
      await addBarrier;
      try {
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Expired" }),
        });
      } finally {
        addResponses += 1;
      }
      return;
    }
    await route.fulfill({ status: 204, body: "" });
  });

  await page.goto("/");
  await page.locator(".location-card", { hasText: "Pine Marsh" }).click();
  const panel = page.locator("#atlas-session-player");
  const settledMutations = await page.evaluate(() => (
    (window as typeof window & { __favoriteContinuations?: { mutation: number } }).__favoriteContinuations?.mutation ?? 0
  ));
  await panel.getByRole("button", { name: "Save recording" }).click();
  await expect.poll(() => addRequests).toBe(1);
  await panel.getByRole("button", { name: "Hide player" }).click();
  await expect(panel).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => (
    (window as typeof window & { __favoriteContinuations?: { mutation: number } }).__favoriteContinuations?.mutation ?? 0
  ))).toBe(settledMutations + 1);

  releaseAdd();
  await expect.poll(() => addResponses).toBe(1);
  await expect.poll(() => addRequests).toBe(1);
  await expect.poll(() => refreshRequests).toBe(0);
  await expect.poll(() => page.evaluate(() => (
    (window as typeof window & { __favoriteAnalytics?: string[] }).__favoriteAnalytics ?? []
  ))).not.toContain("favorite_add");
});

test("a favorite mutation that loses authentication offers sign-in recovery", async ({ page }) => {
  const analytics: string[] = [];
  await page.addInitScript(() => {
    window.addEventListener("orna:analytics", ((event: CustomEvent<{ name?: string }>) => {
      if (event.detail.name) {
        (window as typeof window & { __favoriteAnalytics?: string[] }).__favoriteAnalytics?.push(event.detail.name);
      }
    }) as EventListener);
    Object.assign(window, { __favoriteAnalytics: [] as string[] });
  });
  await page.route("**/api/v1/auth/refresh", (route) => route.fulfill({
    status: 401,
    contentType: "application/json",
    body: JSON.stringify({ detail: "Authentication is required" }),
  }));
  await page.route("**/api/v1/users/me/favorites**", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([{
          session: { id: "20000000-0000-4000-8000-000000000002" },
          favorited_at: "2026-07-22T07:00:00Z",
        }]),
      });
      return;
    }
    await route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Authentication is required" }),
    });
  });

  await page.goto("/");
  await page.locator(".location-card", { hasText: "Pine Marsh" }).click();
  const panel = page.locator("#atlas-session-player");
  await panel.getByRole("button", { name: "Remove from favorites" }).click();
  await expect(panel.getByText("Sign in or create a free account to save favorites.")).toBeVisible();
  await expect(panel.getByRole("link", { name: "Sign in" })).toBeVisible();
  await expect(panel.getByRole("button", { name: "Save recording" })).toHaveAttribute("aria-pressed", "false");
  const emitted = await page.evaluate(() => (
    (window as typeof window & { __favoriteAnalytics?: string[] }).__favoriteAnalytics ?? []
  ));
  analytics.push(...emitted);
  expect(analytics.filter((name) => name === "favorite_requires_login")).toHaveLength(1);
  expect(analytics).not.toContain("favorite_add");
});

test("signed-in favorites are saved to the account library", async ({ page }) => {
  let favoriteReads = 0;
  let favoriteWrites = 0;
  await page.route("**/api/v1/users/me/favorites**", async (route) => {
    if (route.request().method() === "GET") {
      favoriteReads += 1;
      await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
      return;
    }
    favoriteWrites += 1;
    await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  await page.goto("/");
  await page.locator(".location-card", { hasText: "Pine Marsh" }).click();
  const panel = page.locator("#atlas-session-player");
  const save = panel.getByRole("button", { name: "Save recording" });
  await expect(save).toBeEnabled();
  expect(favoriteReads).toBeGreaterThan(0);
  await save.click();
  await expect.poll(() => favoriteWrites).toBe(1);
  await expect(panel.getByRole("button", { name: "Remove from favorites" })).toHaveAttribute("aria-pressed", "true");
  await expect(panel.getByText("Saved to your account.")).toBeVisible();
  await expect(panel.getByRole("link", { name: "View your library" })).toHaveAttribute("href", "/library");
});

test("anonymous favorite intent asks for sign-in without blocking playback", async ({ page }) => {
  await page.route("**/api/v1/users/me/favorites**", (route) => route.fulfill({
    status: 401,
    contentType: "application/json",
    body: JSON.stringify({ detail: "Authentication is required" }),
  }));
  await page.goto("/");
  await page.locator(".location-card", { hasText: "Pine Marsh" }).click();
  const panel = page.locator("#atlas-session-player");
  await panel.getByRole("button", { name: "Save recording" }).click();
  await expect(panel.getByText("Sign in or create a free account to save favorites.")).toBeVisible();
  await expect(panel.getByRole("button", { name: "Play session" })).toBeEnabled();
});

test("listening-history rejection never blocks anonymous preview playback", async ({ page }) => {
  let historyWrites = 0;
  page.on("request", (candidate) => {
    if (candidate.method() === "PUT" && candidate.url().includes("/users/me/listening-history/")) historyWrites += 1;
  });
  await page.addInitScript(() => {
    Object.defineProperty(HTMLMediaElement.prototype, "play", {
      configurable: true,
      value: async function play() { this.dispatchEvent(new Event("play")); },
    });
    Object.defineProperty(HTMLMediaElement.prototype, "pause", {
      configurable: true,
      value: function pause() { this.dispatchEvent(new Event("pause")); },
    });
  });
  await page.route("**/api/v1/users/me/listening-history/**", (route) => route.fulfill({
    status: 401,
    contentType: "application/json",
    body: JSON.stringify({ detail: "Authentication is required" }),
  }));
  await page.goto("/");
  const historyWrite = page.waitForRequest((candidate) => (
    candidate.method() === "PUT" && candidate.url().includes("/users/me/listening-history/")
  ));
  const preview = page.getByRole("button", { name: /Play preview for/ }).first();
  await preview.click();
  await historyWrite;
  const globalPlayer = page.getByRole("complementary", { name: "Global audio player" });
  await expect(globalPlayer).toBeVisible();
  await page.getByRole("link", { name: "First Session", exact: true }).click();
  const firstSessionPlayer = page.locator("#atlas-session-player");
  const secondGrant = page.waitForRequest((candidate) => (
    candidate.method() === "POST" && candidate.url().includes("/playback-grants")
  ));
  await firstSessionPlayer.getByRole("button", { name: "Play session" }).click();
  await secondGrant;
  await page.waitForTimeout(100);
  expect(historyWrites).toBe(1);
});

test("preview analytics names only the first and second preview", async ({ page }) => {
  const analytics: Array<Record<string, unknown>> = [];
  await page.addInitScript(() => {
    Object.defineProperty(HTMLMediaElement.prototype, "play", {
      configurable: true,
      value: async function play() { this.dispatchEvent(new Event("play")); },
    });
  });
  await page.route("**/api/v1/analytics/events", async (route) => {
    analytics.push(route.request().postDataJSON() as Record<string, unknown>);
    await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ accepted: true }) });
  });

  for (let previewNumber = 1; previewNumber <= 3; previewNumber += 1) {
    if (previewNumber === 1) await page.goto("/");
    else await page.reload();
    const grant = page.waitForRequest((candidate) => candidate.url().includes("/playback-grants"));
    await page.getByRole("button", { name: /Play preview for/ }).first().click();
    await grant;
    await expect.poll(() => analytics.filter((event) => event.name === "player_play").length).toBe(previewNumber);
  }

  expect(analytics.filter((event) => event.name === "session_preview_start")).toHaveLength(1);
  expect(analytics.filter((event) => event.name === "session_preview_second")).toHaveLength(1);
});

test("account library renders synced favorites and listening history without coordinates", async ({ page }) => {
  const session = {
    id: "20000000-0000-4000-8000-000000000001",
    slug: "first-session",
    title: "First Session",
    recorded_at: "2026-03-20T04:30:00Z",
    duration_seconds: 600,
    access_level: "public",
    location: {
      id: "10000000-0000-4000-8000-000000000001",
      slug: "pine-marsh",
      name: "Pine Marsh",
      region: "Harju County",
      habitat: "Wetland",
    },
  };
  await page.route("**/api/v1/users/me/favorites**", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify([{ session, favorited_at: "2026-07-22T07:00:00Z" }]),
  }));
  await page.route("**/api/v1/users/me/listening-history**", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify([{
      session,
      first_listened_at: "2026-07-22T06:00:00Z",
      last_listened_at: "2026-07-22T07:00:00Z",
      last_position_seconds: 42,
      completed_at: null,
    }]),
  }));
  await page.goto("/library");
  await expect(page.getByRole("heading", { name: "Your library", level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Favorites" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Listening history" })).toBeVisible();
  await expect(page.getByText("First Session")).toHaveCount(2);
  await expect(page.getByText(/latitude|longitude|coordinates/i)).toHaveCount(0);
});

test("account library discards old-account successes and reloads after an authentication boundary", async ({ page }) => {
  await page.addInitScript(() => {
    Object.assign(window, { __libraryMutationContinuations: 0 });
    window.addEventListener("orna:test:library-mutation-continuation", () => {
      const target = window as typeof window & { __libraryMutationContinuations?: number };
      target.__libraryMutationContinuations = (target.__libraryMutationContinuations ?? 0) + 1;
    });
  });
  let favoriteReads = 0;
  let historyReads = 0;
  let releaseOldFavorite!: () => void;
  let releaseFavoriteRemoval!: () => void;
  let releaseHistoryClear!: () => void;
  let notifyFavoriteRemovalStarted!: () => void;
  let notifyHistoryClearStarted!: () => void;
  const oldFavoriteMaySettle = new Promise<void>((resolve) => {
    releaseOldFavorite = resolve;
  });
  const favoriteRemovalMaySettle = new Promise<void>((resolve) => {
    releaseFavoriteRemoval = resolve;
  });
  const historyClearMaySettle = new Promise<void>((resolve) => {
    releaseHistoryClear = resolve;
  });
  const favoriteRemovalStarted = new Promise<void>((resolve) => {
    notifyFavoriteRemovalStarted = resolve;
  });
  const historyClearStarted = new Promise<void>((resolve) => {
    notifyHistoryClearStarted = resolve;
  });
  const session = (title: string) => ({
    id: "20000000-0000-4000-8000-000000000001",
    slug: "first-session",
    title,
    recorded_at: "2026-03-20T04:30:00Z",
    duration_seconds: 600,
    access_level: "public",
    location: {
      id: "10000000-0000-4000-8000-000000000001",
      slug: "pine-marsh",
      name: "Pine Marsh",
      region: "Harju County",
      habitat: "Wetland",
    },
  });
  await page.route("**/api/v1/users/me/favorites**", async (route) => {
    if (route.request().method() === "DELETE") {
      notifyFavoriteRemovalStarted();
      await favoriteRemovalMaySettle;
      await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "Old mutation" }) });
      return;
    }
    favoriteReads += 1;
    if (favoriteReads === 1) {
      await oldFavoriteMaySettle;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([{ session: session("Old account recording"), favorited_at: "2026-07-22T07:00:00Z" }]),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([{ session: session("Current account recording"), favorited_at: "2026-07-22T08:00:00Z" }]),
    });
  });
  await page.route("**/api/v1/users/me/listening-history**", async (route) => {
    if (route.request().method() === "DELETE") {
      notifyHistoryClearStarted();
      await historyClearMaySettle;
      await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "Old mutation" }) });
      return;
    }
    historyReads += 1;
    if (historyReads === 1) {
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Expired previous account" }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([{
        session: session("Current account recording"),
        first_listened_at: "2026-07-22T07:00:00Z",
        last_listened_at: "2026-07-22T08:00:00Z",
        last_position_seconds: 42,
        completed_at: null,
      }]),
    });
  });
  await page.route("**/api/v1/auth/refresh", (route) => route.fulfill({
    status: 401,
    contentType: "application/json",
    body: JSON.stringify({ detail: "Refresh expired" }),
  }));

  await page.goto("/library");
  await expect.poll(() => favoriteReads).toBeGreaterThanOrEqual(2);
  await expect(page.getByText("Current account recording").first()).toBeVisible();
  releaseOldFavorite();
  await expect(page.getByText("Old account recording")).toHaveCount(0);
  await expect(page.getByText("Current account recording").first()).toBeVisible();

  await page.getByRole("button", { name: "Remove" }).click();
  await favoriteRemovalStarted;
  const continuationsBeforeRemoval = await page.evaluate(() => (
    (window as typeof window & { __libraryMutationContinuations?: number }).__libraryMutationContinuations ?? 0
  ));
  const readsBeforeRemovalBoundary = favoriteReads;
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("orna:account-auth-changed", {
    detail: { state: "authenticated", source: null },
  })));
  await expect.poll(() => favoriteReads).toBeGreaterThan(readsBeforeRemovalBoundary);
  releaseFavoriteRemoval();
  await expect.poll(() => page.evaluate(() => (
    (window as typeof window & { __libraryMutationContinuations?: number }).__libraryMutationContinuations ?? 0
  ))).toBe(continuationsBeforeRemoval + 1);
  await expect(page.getByText("Your library is temporarily unavailable. Please try again.")).toHaveCount(0);
  await expect(page.getByText("Current account recording").first()).toBeVisible();

  await page.getByRole("button", { name: "Clear history" }).click();
  await historyClearStarted;
  const continuationsBeforeClear = await page.evaluate(() => (
    (window as typeof window & { __libraryMutationContinuations?: number }).__libraryMutationContinuations ?? 0
  ));
  const readsBeforeHistoryBoundary = historyReads;
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("orna:account-auth-changed", {
    detail: { state: "authenticated", source: null },
  })));
  await expect.poll(() => historyReads).toBeGreaterThan(readsBeforeHistoryBoundary);
  releaseHistoryClear();
  await expect.poll(() => page.evaluate(() => (
    (window as typeof window & { __libraryMutationContinuations?: number }).__libraryMutationContinuations ?? 0
  ))).toBe(continuationsBeforeClear + 1);
  await expect(page.getByText("Your library is temporarily unavailable. Please try again.")).toHaveCount(0);
  await expect(page.getByText("Current account recording").first()).toBeVisible();
});

test("homepage discovery links reach collections, sign-in, and subscription entry points", async ({ page }) => {
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  const collectionsLink = page.getByRole("link", { name: "See all collections" });
  await expect(collectionsLink).toHaveAttribute("href", "/collections");
  await page.goto("/collections");
  await expect(page).toHaveURL(/\/collections$/);
  await expect(page.getByRole("heading", { name: "Collections", level: 1 })).toBeVisible();
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  const passwordSignInLink = page.getByRole("dialog", { name: "Sign in without leaving the atlas" })
    .getByRole("link", { name: "Use password or social sign-in" });
  await expect(passwordSignInLink).toHaveAttribute("href", "/membership?mode=login");
  await page.goto("/membership?mode=login");
  await expect(page).toHaveURL(/\/membership\?mode=login/);
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  await expect(page.getByRole("link", { name: "Subscribe" })).toHaveAttribute("href", "/membership?mode=register");
  await page.goto("/membership?mode=register");
  await expect(page).toHaveURL(/\/membership\?mode=register/);
});

test("browser funnel analytics remains bounded across globe, preview, collections, and signup", async ({ page }) => {
  const analytics: Array<Record<string, unknown>> = [];
  await page.route("**/api/v1/analytics/events", async (route) => {
    analytics.push(route.request().postDataJSON() as Record<string, unknown>);
    await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ accepted: true }) });
  });
  await page.addInitScript(() => {
    Object.defineProperty(HTMLMediaElement.prototype, "play", {
      configurable: true,
      value: async function play() {
        this.dispatchEvent(new Event("play"));
      },
    });
  });
  await page.goto("/");
  await expect.poll(() => analytics.map((event) => event.name)).toContain("globe_view");
  await page.getByRole("button", { name: "Reset globe" }).click();
  await page.getByRole("button", { name: /Play preview for/ }).first().click();
  await expect(page.getByRole("complementary", { name: "Global audio player" })).toBeVisible();
  const seeAllCollections = page.getByRole("link", { name: "See all collections" });
  await expect(seeAllCollections).toHaveAttribute("href", "/collections");
  await Promise.all([
    page.waitForURL((url) => url.pathname === "/collections"),
    seeAllCollections.click(),
  ]);
  await page.goto("/membership?mode=register&returnTo=%2Fsessions%2Ffirst-session");
  await page.getByLabel("Email address", { exact: true }).fill("bounded@example.com");
  await page.getByRole("button", { name: "Email me a sign-in link" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Check your email" })).toBeVisible();

  await expect.poll(() => analytics.map((event) => event.name)).toEqual(expect.arrayContaining([
    "globe_view",
    "reset_view_click",
    "card_inline_play",
    "player_play",
    "session_preview_start",
    "see_all_click",
    "signup_email_submit",
  ]));
  expect(analytics.filter((event) => event.name === "card_inline_play")).toHaveLength(1);
  expect(analytics.filter((event) => event.name === "session_preview_start")).toHaveLength(1);
  expect(analytics.filter((event) => event.name === "session_preview_second")).toHaveLength(0);
  expect(analytics.filter((event) => event.name === "player_play")).toHaveLength(1);
  for (const event of analytics) {
    expect(Object.keys(event).sort()).toEqual(["name", "placement"]);
  }
  expect(JSON.stringify(analytics)).not.toContain("bounded@example.com");
  expect(JSON.stringify(analytics)).not.toMatch(/latitude|longitude|return_to|token|url/i);
});
