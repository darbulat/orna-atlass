import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const adminLocationId = "11000000-0000-4000-8000-000000000001";
const adminSessionId = "21000000-0000-4000-8000-000000000001";
const adminAssetId = "31000000-0000-4000-8000-000000000001";
const adminCollectionId = "41000000-0000-4000-8000-000000000001";
const adminRevision = 'W/"location-r1"';
const sessionRevision = 'W/"session-r1"';
const collectionRevision = 'W/"collection-r1"';

test.beforeEach(async ({ request }) => {
  const reset = await request.post("http://127.0.0.1:4010/__e2e/admin-state?reset=true&revoked=false");
  expect(reset.status()).toBe(204);
});

async function adminProbeState(request: APIRequestContext) {
  const response = await request.get("http://127.0.0.1:4010/__e2e/admin-state");
  expect(response.status()).toBe(200);
  return await response.json() as {
    access_revoked: boolean;
    refresh_pending: boolean;
    identity_held: boolean;
    request_counts: Record<string, number>;
  };
}

async function useAdminCookie(page: Page, value = "admin-e2e") {
  await page.context().addCookies([
    {
      name: "orna_access",
      value,
      domain: "127.0.0.1",
      path: "/",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);
}

function locationUpdateForm(page: Page) {
  const card = page.locator(".admin-action-card").filter({
    has: page.getByRole("heading", { level: 3, name: "Локации" }),
  });
  return card.locator("form").filter({
    has: page.getByRole("heading", { level: 4, name: "Редактировать" }),
  });
}

function actionForm(page: Page, section: string, action: string) {
  const card = page.locator(".admin-action-card").filter({
    has: page.getByRole("heading", { level: 3, name: section, exact: true }),
  });
  return card.locator("form").filter({
    has: page.getByRole("heading", { level: 4, name: action, exact: true }),
  });
}

test("anonymous and non-admin identities fail closed without admin data", async ({ page }) => {
  await page.goto("/admin");
  await expect(page.getByRole("heading", { level: 1, name: "Админ-панель" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Войти и получить доступ" })).toHaveAttribute(
    "href",
    "/membership?mode=login&returnTo=%2Fadmin",
  );
  await expect(page.getByText("Hidden Nesting Site")).toHaveCount(0);

  await useAdminCookie(page, "member-e2e");
  await page.goto("/admin");
  await expect(page.getByText("У вас нет прав для админ-панели.")).toBeVisible();
  await expect(page.getByText("Hidden Nesting Site")).toHaveCount(0);
});

test("admin workspace renders protected projections without leaking hidden public coordinates", async ({ page }) => {
  await useAdminCookie(page);
  await page.goto("/admin");

  await expect(page.getByText("Hidden Nesting Site", { exact: true })).toBeVisible();
  await expect(page.getByText(/Exact admin: 59\.555555, 24\.555555/)).toBeVisible();
  await expect(page.getByText("Public preview: скрыт политикой hidden_public")).toBeVisible();
  await expect(page.getByText(/11\.111111|22\.222222/)).toHaveCount(0);
  await expect(page.getByText("Draft Admin Session", { exact: true })).toBeVisible();
  await expect(page.getByText("Admin Collection", { exact: true })).toBeVisible();
  await expect(page.getByText("target-admin@example.test", { exact: true })).toBeVisible();

  const metadata = page.locator(".admin-audit-metadata");
  await expect(metadata.locator("pre")).not.toBeVisible();
  await metadata.locator("summary").click();
  await expect(metadata.locator("pre")).toContainText("changed_fields");
  await expect(page.getByText("Gate: включён.")).toBeVisible();
});

test("quick navigation keeps every admin workspace section reachable", async ({ page }) => {
  await useAdminCookie(page);
  await page.goto("/admin");

  const navigation = page.getByRole("navigation", { name: "Быстрая навигация" });
  await expect(navigation).toBeVisible();

  const destinations = [
    ["Обзор", "#overview"],
    ["Фильтры", "#filters"],
    ["Операции", "#operations"],
    ["Локации", "#locations"],
    ["Сессии", "#sessions"],
    ["Коллекции", "#collections"],
    ["Пользователи", "#users"],
    ["Аудит", "#audit"],
  ] as const;

  for (const [name, href] of destinations) {
    await expect(navigation.getByRole("link", { name, exact: true })).toHaveAttribute("href", href);
  }

  await navigation.getByRole("link", { name: "Операции", exact: true }).click();
  await expect(page).toHaveURL(/#operations$/);
  await expect(page.getByRole("heading", { level: 2, name: "Операции администратора" })).toBeVisible();

  const filterPanel = page.locator("#filters");
  await expect(filterPanel).toHaveAttribute("open", "");
  await filterPanel.getByText("Фильтры списков", { exact: true }).click();
  await expect(filterPanel).not.toHaveAttribute("open", "");
  await expect(filterPanel.getByRole("button", { name: "Применить фильтры" })).not.toBeVisible();
});

test("revoked admin access clears every privileged projection on focus revalidation", async ({ page, request }) => {
  await useAdminCookie(page);
  await page.goto("/admin");
  await expect(page.getByText("Hidden Nesting Site", { exact: true })).toBeVisible();

  const revoke = await request.post("http://127.0.0.1:4010/__e2e/admin-state?revoked=true");
  expect(revoke.status()).toBe(204);
  await expect.poll(async () => {
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    const state = await adminProbeState(request);
    return state.request_counts["GET /api/v1/admin/me"] ?? 0;
  }).toBeGreaterThan(1);

  await expect(page.getByRole("heading", { name: "Доступ администратора отозван" })).toBeVisible();
  await expect(page.getByText("Hidden Nesting Site", { exact: true })).toHaveCount(0);
  await expect(page.getByText("target-admin@example.test", { exact: true })).toHaveCount(0);
  await expect(page.getByText(/59\.555555|24\.555555/)).toHaveCount(0);
});

test("an older successful identity response cannot restore revoked admin access", async ({ page, request }) => {
  await useAdminCookie(page);
  await page.goto("/admin");
  await expect(page.getByText("Hidden Nesting Site", { exact: true })).toBeVisible();

  const hold = await request.post("http://127.0.0.1:4010/__e2e/admin-state?hold_next_identity=true");
  expect(hold.status()).toBe(204);
  await expect.poll(async () => {
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    return (await adminProbeState(request)).identity_held;
  }).toBe(true);

  const revoke = await request.post("http://127.0.0.1:4010/__e2e/admin-state?revoked=true");
  expect(revoke.status()).toBe(204);
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("heading", { name: "Доступ администратора отозван" })).toBeVisible();

  const release = await request.post(
    "http://127.0.0.1:4010/__e2e/admin-state?revoked=true&release_identity=true",
  );
  expect(release.status()).toBe(204);
  await expect.poll(async () => (await adminProbeState(request)).identity_held).toBe(false);

  await expect(page.getByRole("heading", { name: "Доступ администратора отозван" })).toBeVisible();
  await expect(page.getByText("Hidden Nesting Site", { exact: true })).toHaveCount(0);
});

test("an expired admin access cookie refreshes once without clearing privileged content", async ({ page, request }) => {
  await useAdminCookie(page);
  await page.goto("/admin");
  await expect(page.getByText("Hidden Nesting Site", { exact: true })).toBeVisible();
  const expire = await request.post("http://127.0.0.1:4010/__e2e/admin-state?unauthorized_once=true");
  expect(expire.status()).toBe(204);

  await expect.poll(async () => {
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    return (await adminProbeState(request)).refresh_pending;
  }).toBe(false);

  await expect(page.getByText("Hidden Nesting Site", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Доступ администратора отозван" })).toHaveCount(0);
});

test("malformed privileged enum fails the location region closed", async ({ page }) => {
  await useAdminCookie(page, "malformed-admin-e2e");
  await page.goto("/admin");

  const locations = page.getByRole("region", { name: "Локации" });
  await expect(locations.getByText("Сбой чтения данных админ-API.")).toBeVisible();
  await expect(locations.getByText("Hidden Nesting Site")).toHaveCount(0);
  await expect(page.getByText(/59\.555555|24\.555555/)).toHaveCount(0);
});

test("sensitive email search stays out of URL and browser history state", async ({ page }) => {
  await useAdminCookie(page);
  await page.goto("/admin");

  const search = page.locator(".admin-sensitive-search");
  await search.getByLabel("Email").fill("target-admin@example.test");
  await search.getByRole("button", { name: "Найти" }).click();

  await expect(search.getByText("target-admin@example.test", { exact: true })).toBeVisible();
  expect(page.url()).not.toContain("target-admin%40example.test");
  expect(page.url()).not.toContain("user_email");
  expect(await page.evaluate(() => JSON.stringify(history.state))).not.toContain("target-admin@example.test");
});

test("target-email confirmation blocks mismatched account mutations without a request", async ({ page, request }) => {
  await useAdminCookie(page);
  await page.goto("/admin");

  let form = actionForm(page, "Пользователи и membership", "Изменить роль");
  await form.getByLabel("User ID", { exact: true }).fill("51000000-0000-4000-8000-000000000001");
  await form.getByLabel("Aggregate user/membership revision", { exact: true }).fill('W/"user-r1"');
  await form.getByLabel("Подтверждение · email целевого пользователя", { exact: true }).fill("wrong@example.test");
  await form.getByRole("button", { name: "Обновить роль" }).click();
  await expect(page.locator(".admin-notice-error")).toContainText("Операция отклонена.");
  let state = await adminProbeState(request);
  expect(state.request_counts["PATCH /api/v1/admin/users/51000000-0000-4000-8000-000000000001/role"] ?? 0).toBe(0);

  form = actionForm(page, "Пользователи и membership", "Изменить роль");
  await form.getByLabel("User ID", { exact: true }).fill("51000000-0000-4000-8000-000000000001");
  await form.getByLabel("Aggregate user/membership revision", { exact: true }).fill('W/"user-r1"');
  await form.getByLabel("Подтверждение · email целевого пользователя", { exact: true }).fill("target-admin@example.test");
  await form.getByRole("button", { name: "Обновить роль" }).click();
  await expect(page.locator(".admin-notice-success")).toContainText("Операция выполнена.");
  state = await adminProbeState(request);
  expect(state.request_counts["PATCH /api/v1/admin/users/51000000-0000-4000-8000-000000000001/role"]).toBe(1);
  expect(page.url()).not.toContain("target-admin");
  expect(page.url()).not.toContain("51000000");
});

test("transient operational identifiers stay out of URL history notices and storage", async ({ page }) => {
  await useAdminCookie(page);
  await page.goto("/admin");
  const search = page.locator(".admin-sensitive-search").filter({ hasText: "Transient operational ID filters" });
  const locationId = "11000000-0000-4000-8000-000000000001";
  await search.getByLabel("Location ID", { exact: true }).fill(locationId);
  await search.getByRole("button", { name: "Выполнить transient-поиск" }).click();
  await expect(search.getByText("Draft Admin Session", { exact: true })).toBeVisible();
  const persisted = await page.evaluate(() => JSON.stringify({ history: history.state, local: localStorage, session: sessionStorage }));
  expect(page.url()).not.toContain(locationId);
  expect(persisted).not.toContain(locationId);
  expect((await page.locator(".admin-notice").allTextContents()).join(" ")).not.toContain(locationId);
});

test("location mutation reports success and a stale If-Match without replay", async ({ page, request }) => {
  await useAdminCookie(page);
  await page.goto("/admin");

  let form = locationUpdateForm(page);
  await form.getByLabel("ID", { exact: true }).fill(adminLocationId);
  await form.getByLabel("Revision / If-Match", { exact: true }).fill(adminRevision);
  await form.getByLabel("Название", { exact: true }).fill("Renamed location");
  await form.getByRole("button", { name: "Сохранить" }).click();
  await expect(page.locator(".admin-notice")).toContainText("Операция выполнена.");
  expect(page.url()).not.toContain(adminLocationId);
  expect(page.url()).not.toContain("operation_log");

  let persisted = await request.get("http://127.0.0.1:4010/api/v1/admin/locations?limit=1&offset=0", {
    headers: { Cookie: "orna_access=admin-e2e" },
  });
  expect(persisted.status()).toBe(200);
  let [persistedLocation] = await persisted.json();
  expect(persistedLocation.name).toBe("Renamed location");
  expect(persistedLocation.revision).toBe('W/"location-r2"');

  form = locationUpdateForm(page);
  await form.getByLabel("ID", { exact: true }).fill(adminLocationId);
  await form.getByLabel("Revision / If-Match", { exact: true }).fill(adminRevision);
  await form.getByLabel("Название", { exact: true }).fill("Stale location");
  await form.getByRole("button", { name: "Сохранить" }).click();
  await expect(page.locator(".admin-notice-error")).toContainText(
    "Запись была изменена другим администратором. Обновите список и используйте новую revision.",
  );
  const state = await adminProbeState(request);
  expect(state.request_counts[`PATCH /api/v1/admin/locations/${adminLocationId}`]).toBe(2);

  persisted = await request.get("http://127.0.0.1:4010/api/v1/admin/locations?limit=1&offset=0", {
    headers: { Cookie: "orna_access=admin-e2e" },
  });
  expect(persisted.status()).toBe(200);
  [persistedLocation] = await persisted.json();
  expect(persistedLocation.name).toBe("Renamed location");
  expect(persistedLocation.revision).toBe('W/"location-r2"');
});

test("editorial create/update/archive and ordered collection workflows are deterministic", async ({ page }) => {
  await useAdminCookie(page);
  await page.goto("/admin");

  let form = actionForm(page, "Локации", "Создать");
  await form.getByLabel("Название", { exact: true }).fill("New admin location");
  await form.getByLabel("Slug", { exact: true }).fill("new-admin-location");
  await form.getByLabel("Exact latitude", { exact: true }).fill("55.1");
  await form.getByLabel("Exact longitude", { exact: true }).fill("37.2");
  await form.getByLabel("Timezone (IANA)", { exact: true }).fill("Europe/Paris");
  await form.getByRole("button", { name: "Создать локацию" }).click();
  await expect(page.locator(".admin-notice-success")).toContainText("Операция выполнена.");

  form = actionForm(page, "Сессии", "Создать");
  await form.getByLabel("Название", { exact: true }).fill("New draft session");
  await form.getByLabel("Slug", { exact: true }).fill("new-draft-session");
  await form.getByLabel("Location ID", { exact: true }).fill(adminLocationId);
  await form.getByLabel("Recorded at", { exact: true }).fill("2026-07-30T10:00:00Z");
  await form.getByRole("button", { name: "Создать сессию" }).click();
  await expect(page.locator(".admin-notice-success")).toContainText("Операция выполнена.");

  await useAdminCookie(page, "stale-admin-e2e");
  form = actionForm(page, "Сессии", "Редактировать");
  await form.getByLabel("Session ID", { exact: true }).fill(adminSessionId);
  await form.getByLabel("Revision / If-Match", { exact: true }).fill(sessionRevision);
  await form.getByLabel("Название", { exact: true }).fill("Stale session edit");
  await form.getByRole("button", { name: "Сохранить" }).click();
  await expect(page.locator(".admin-notice-error")).toContainText("Запись была изменена");

  await useAdminCookie(page);
  form = actionForm(page, "Сессии", "Архивировать");
  await form.getByLabel("Session ID", { exact: true }).fill(adminSessionId);
  await form.getByLabel("Revision / If-Match", { exact: true }).fill(sessionRevision);
  await form.getByLabel("Подтверждение: повторите Session ID", { exact: true }).fill(adminSessionId);
  await form.getByRole("button", { name: "Архивировать сессию" }).click();
  await expect(page.locator(".admin-notice-success")).toContainText("Операция выполнена.");

  form = actionForm(page, "Коллекции", "Создать");
  await form.getByLabel("Название", { exact: true }).fill("Ordered collection");
  await form.getByLabel("Slug", { exact: true }).fill("ordered-collection");
  await form.locator('textarea[name="collection_location_ids"]').fill(JSON.stringify([adminLocationId]));
  await form.locator('textarea[name="collection_session_ids"]').fill(JSON.stringify([adminSessionId]));
  await form.getByRole("button", { name: "Создать коллекцию" }).click();
  await expect(page.locator(".admin-notice-success")).toContainText("Операция выполнена.");

  form = actionForm(page, "Коллекции", "Редактировать");
  await form.getByLabel("ID", { exact: true }).fill(adminCollectionId);
  await form.getByLabel("Revision / If-Match", { exact: true }).fill(collectionRevision);
  await form.locator('textarea[name="collection_location_ids"]').fill("[]");
  await form.locator('textarea[name="collection_session_ids"]').fill(JSON.stringify([adminSessionId]));
  await form.getByRole("button", { name: "Сохранить" }).click();
  await expect(page.locator(".admin-notice-success")).toContainText("Операция выполнена.");
});

test("media registration and retry fail closed during dependency outage", async ({ page }) => {
  await useAdminCookie(page);
  await page.goto("/admin");

  let form = actionForm(page, "Сессии", "Зарегистрировать managed asset");
  await form.getByLabel("Session ID", { exact: true }).fill(adminSessionId);
  await form.getByLabel("Storage key", { exact: true }).fill("sessions/admin/source.wav");
  await form.getByRole("button", { name: "Зарегистрировать asset" }).click();
  await expect(page.locator(".admin-notice-success")).toContainText("Операция выполнена.");

  form = actionForm(page, "Сессии", "Зарегистрировать сегменты");
  await form.getByLabel("Session ID", { exact: true }).fill(adminSessionId);
  await form.getByLabel("JSON-массив сегментов (1..N)", { exact: true }).fill(JSON.stringify([{ sequence_number: 1, storage_key: "sessions/admin/segment-1.wav" }]));
  await form.getByRole("button", { name: "Зарегистрировать сегменты" }).click();
  await expect(page.locator(".admin-notice-success")).toContainText("Операция выполнена.");

  form = actionForm(page, "Сессии", "Retry HLS сессии");
  await form.getByLabel("Session ID", { exact: true }).fill(adminSessionId);
  await form.getByRole("button", { name: "Поставить retry в очередь" }).click();
  await expect(page.locator(".admin-notice-success")).toContainText("Операция выполнена.");

  await useAdminCookie(page, "unavailable-admin-e2e");
  form = actionForm(page, "Сессии", "Retry asset");
  await form.getByLabel("Asset ID", { exact: true }).fill(adminAssetId);
  await form.getByRole("button", { name: "Повторить обработку asset" }).click();
  await expect(page.locator(".admin-notice-error")).toContainText("HTTP 503");
  await expect(page.locator(".admin-notice-error")).not.toContainText(/ready|playable/);
});

test("bounded filters and load-more preserve only non-sensitive query state", async ({ page }) => {
  await useAdminCookie(page, "pagination-admin-e2e");
  await page.goto("/admin");
  const filters = page.locator("form.admin-filters");
  await filters.getByLabel("Локации: поиск", { exact: true }).fill("nest");
  await filters.locator('select[name="session_publication_status"]').selectOption("draft");
  await filters.locator('select[name="collection_is_public"]').selectOption("true");
  await filters.getByRole("button", { name: "Применить фильтры" }).click();
  await expect(page).toHaveURL(/location_q=nest/);
  await expect(page).toHaveURL(/session_publication_status=draft/);
  await expect(page).toHaveURL(/collection_is_public=true/);
  await page.getByRole("link", { name: "Загрузить ещё локации" }).click();
  await expect(page).toHaveURL(/locations_limit=100/);
  const ids = await page.locator("#locations .admin-resource-id code").evaluateAll((nodes) => nodes.map((node) => node.textContent));
  expect(ids).toHaveLength(200);
  expect(new Set(ids.filter((_, index) => index % 2 === 0)).size).toBe(100);
  expect(page.url()).not.toMatch(/user_email|audit_ip_address|audit_user_agent|operation_log/);
});

test("admin response is no-store and sensitive values never enter browser persistence", async ({ page }) => {
  await useAdminCookie(page);
  const response = await page.goto("/admin");
  expect(response?.headers()["cache-control"]).toMatch(/no-store|no-cache/);
  const persistence = await page.evaluate(async () => ({
    local: JSON.stringify(localStorage),
    session: JSON.stringify(sessionStorage),
    history: JSON.stringify(history.state),
    cacheKeys: "caches" in window ? await caches.keys() : [],
  }));
  const serialized = JSON.stringify(persistence);
  expect(serialized).not.toContain("target-admin@example.test");
  expect(serialized).not.toContain("59.555555");
  expect(serialized).not.toContain("24.555555");
});

test("admin workspace remains reachable at 320px with visible 44px controls", async ({ page }) => {
  await useAdminCookie(page);
  await page.setViewportSize({ width: 320, height: 700 });
  await page.goto("/admin");

  const geometry = await page.evaluate(() => {
    const elements = Array.from(document.querySelectorAll<HTMLElement>(".admin-shell a, .admin-shell button, .admin-shell input, .admin-shell select, .admin-shell textarea"))
      .filter((element) => element.getClientRects().length > 0);
    const controls = elements.map((element) => element.getBoundingClientRect());
    const viewport = document.documentElement.clientWidth;
    const shell = document.querySelector<HTMLElement>(".shell");
    const adminShell = document.querySelector<HTMLElement>(".admin-shell");
    const adminHeader = document.querySelector<HTMLElement>(".admin-header");
    const offenders = Array.from(document.querySelectorAll<HTMLElement>("body *"))
      .filter((element) => {
        const box = element.getBoundingClientRect();
        return element.getClientRects().length > 0 && (box.left < 0 || box.right > viewport);
      })
      .slice(0, 10)
      .map((element) => {
        const box = element.getBoundingClientRect();
        return { tag: element.tagName, className: element.className, left: box.left, right: box.right, width: box.width };
      });
    return {
      viewport,
      scrollWidth: document.documentElement.scrollWidth,
      controlsFit: controls.every((box) => box.left >= 0 && box.right <= document.documentElement.clientWidth),
      controlsTallEnough: controls.every((box) => box.height >= 44),
      offenders,
      boxes: {
        shell: shell ? { ...shell.getBoundingClientRect().toJSON(), widthStyle: getComputedStyle(shell).width } : null,
        adminShell: adminShell ? { ...adminShell.getBoundingClientRect().toJSON(), widthStyle: getComputedStyle(adminShell).width } : null,
        adminHeader: adminHeader ? { ...adminHeader.getBoundingClientRect().toJSON(), widthStyle: getComputedStyle(adminHeader).width } : null,
      },
    };
  });

  expect(geometry.scrollWidth, JSON.stringify({ offenders: geometry.offenders, boxes: geometry.boxes })).toBe(geometry.viewport);
  expect(geometry.controlsFit).toBe(true);
  expect(geometry.controlsTallEnough).toBe(true);
});
