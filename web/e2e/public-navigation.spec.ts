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
});

test("atlas route renders without a browser error", async ({ page }) => {
  await page.goto("/atlas?view=list");
  await expect(page.locator("main#main-content")).toBeVisible();
  await expect(page.getByLabel("Atlas list view")).toBeVisible();
});
