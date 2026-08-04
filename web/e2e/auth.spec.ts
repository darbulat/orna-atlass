import { expect, test, type Page } from "@playwright/test";


type PaidAccountFixture = {
  amountMinor?: number;
  currency?: "KZT" | "USD";
  isEntitled?: boolean | null;
  merchantReference?: string;
  paidAt?: string | null;
  status?: "paid" | "refund_requested";
};

async function mockPaidAccount(page: Page, fixture: PaidAccountFixture = {}) {
  const amountMinor = fixture.amountMinor ?? 1000;
  const currency = fixture.currency ?? "USD";
  const isEntitled = fixture.isEntitled === undefined ? true : fixture.isEntitled;
  const merchantReference = fixture.merchantReference ?? `orna-${"c".repeat(31)}`;
  const paidAt = fixture.paidAt === undefined ? "2026-08-04T09:00:00Z" : fixture.paidAt;
  const status = fixture.status ?? "paid";

  await page.route("**/api/v1/users/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "50000000-0000-4000-8000-000000000001",
        email: "member@example.com",
        role: "member",
        is_active: true,
        email_verified: true,
        created_at: "2026-07-19T00:00:00Z",
      }),
    });
  });
  await page.route("**/api/v1/memberships/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        plan: isEntitled ? "lifetime_member" : "none",
        status: isEntitled ? "active" : "inactive",
        is_entitled: isEntitled,
      }),
    });
  });
  await page.route("**/api/v1/billing/offer", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        product_code: "lifetime_member",
        name: "Lifetime Member Access",
        description: "Permanent access to available members-only field recordings.",
        amount_minor: amountMinor,
        currency,
        is_recurring: false,
        checkout_available: true,
        refund_summary: "Full refund requests are accepted within 14 calendar days.",
      }),
    });
  });
  await page.route("**/api/v1/billing/purchases/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([{
        id: "60000000-0000-4000-8000-000000000001",
        merchant_reference: merchantReference,
        product_code: "lifetime_member",
        amount_minor: amountMinor,
        currency,
        status,
        paid_at: paidAt,
        refunded_at: null,
        created_at: "2026-08-04T08:59:00Z",
      }]),
    });
  });

  return { merchantReference };
}


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
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("minlength", "8");
  const metrics = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    cardWidth: document.querySelector<HTMLElement>(".auth-card")?.getBoundingClientRect().width,
  }));
  expect(metrics.scrollWidth).toBe(metrics.viewport);
  expect(metrics.cardWidth).toBeLessThanOrEqual(320);
});


test("signed-out Profile header aligns its menu to the right edge", async ({ page }) => {
  for (const width of [390, 700, 701]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/membership");
    await expect(page.getByRole("heading", {
      level: 1,
      name: "Sign in or create your account",
    })).toBeVisible();

    const navigation = page.getByRole("navigation", { name: "Primary navigation" });
    const metrics = await navigation.evaluate((element) => {
      const page = element.closest<HTMLElement>(".auth-page");
      const box = element.getBoundingClientRect();
      const pageStyle = page ? getComputedStyle(page) : null;
      return {
        navigationRight: box.right,
        expectedRight: window.innerWidth - Number.parseFloat(pageStyle?.paddingRight ?? "0"),
      };
    });

    expect(metrics.navigationRight).toBeCloseTo(metrics.expectedRight, 1);
    if (width <= 700) {
      const triggerBox = await navigation.locator("summary[aria-label='Menu']").boundingBox();
      expect(triggerBox).not.toBeNull();
      expect(triggerBox!.x + triggerBox!.width).toBeCloseTo(metrics.expectedRight, 1);
    } else {
      const profileBox = await navigation.getByRole("link", { name: "Profile" }).boundingBox();
      expect(profileBox).not.toBeNull();
      expect(profileBox!.x + profileBox!.width).toBeCloseTo(metrics.expectedRight, 1);
    }
  }
});


test("signed-in account is a responsive dashboard with clear access and next actions", async ({ page }) => {
  await page.route("**/api/v1/users/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "50000000-0000-4000-8000-000000000001",
        email: "member@example.com",
        role: "member",
        is_active: true,
        email_verified: true,
        created_at: "2026-07-19T00:00:00Z",
      }),
    });
  });
  await page.route("**/api/v1/memberships/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ plan: "none", status: "inactive", is_entitled: false }),
    });
  });

  await page.goto("/membership");

  await expect(page.getByRole("heading", { level: 1, name: "Your account" })).toBeVisible();
  const overview = page.getByRole("region", { name: "Account overview" });
  await expect(overview.getByText("member@example.com")).toBeVisible();
  await expect(overview.getByText("Public previews only")).toBeVisible();
  await expect(page.getByRole("link", { name: "Explore the atlas" })).toHaveAttribute("href", "/#atlas-entry");
  await expect(page.getByRole("link", { name: "Open your library" })).toHaveAttribute("href", "/library");
  await expect(page.getByText("Lifetime access uses one payment at the displayed checkout price.")).toBeVisible();
  await expect(page.getByText("No automatic renewal.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "One payment. No renewal." })).toBeVisible();
  await expect(page.getByText("Test payment mode", { exact: true })).toBeVisible();
  await expect(page.getByText(/does not indicate production payment readiness/)).toBeVisible();
  await expect(page.getByText("Test checkout price", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Checkout unavailable" })).toBeDisabled();

  await page.setViewportSize({ width: 320, height: 700 });
  const geometry = await page.evaluate(() => {
    const dashboard = document.querySelector<HTMLElement>(".account-dashboard")?.getBoundingClientRect();
    const controls = Array.from(document.querySelectorAll<HTMLElement>(".account-page a, .account-page button"))
      .filter((element) => element.getClientRects().length > 0)
      .map((element) => element.getBoundingClientRect());
    return {
      viewport: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      dashboardLeft: dashboard?.left,
      dashboardRight: dashboard?.right,
      controlsFit: controls.every((box) => box.left >= 0 && box.right <= document.documentElement.clientWidth),
      controlsTallEnough: controls.every((box) => box.height >= 44),
    };
  });
  expect(geometry.scrollWidth).toBe(geometry.viewport);
  expect(geometry.dashboardLeft).toBeGreaterThanOrEqual(0);
  expect(geometry.dashboardRight).toBeLessThanOrEqual(320);
  expect(geometry.controlsFit).toBe(true);
  expect(geometry.controlsTallEnough).toBe(true);
});


test("paid billing stays inside narrow viewports with a maximum-length order reference", async ({ page }) => {
  const merchantReference = `orna-${"a".repeat(75)}`;
  await page.route("**/api/v1/users/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "50000000-0000-4000-8000-000000000001",
        email: "member@example.com",
        role: "member",
        is_active: true,
        email_verified: true,
        created_at: "2026-07-19T00:00:00Z",
      }),
    });
  });
  await page.route("**/api/v1/memberships/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ plan: "lifetime_member", status: "active", is_entitled: true }),
    });
  });
  await page.route("**/api/v1/billing/purchases/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([{
        id: "60000000-0000-4000-8000-000000000001",
        merchant_reference: merchantReference,
        product_code: "lifetime_member",
        amount_minor: 200,
        currency: "KZT",
        status: "paid",
        paid_at: "2026-08-04T09:00:00Z",
        refunded_at: null,
        created_at: "2026-08-04T08:59:00Z",
      }]),
    });
  });

  for (const { width, enlargedText } of [
    { width: 320, enlargedText: false },
    { width: 390, enlargedText: false },
    { width: 390, enlargedText: true },
  ]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/membership");
    if (enlargedText) await page.addStyleTag({ content: "html { font-size: 200%; }" });
    await expect(page.getByRole("button", { name: "Request full refund" })).toBeVisible();

    const geometry = await page.locator(".billing-panel").evaluate((panel) => {
      const viewport = document.documentElement.clientWidth;
      const visibleElements = [panel, ...Array.from(panel.querySelectorAll<HTMLElement>("*"))]
        .filter((element) => {
          const style = getComputedStyle(element);
          return element.getClientRects().length > 0 && style.display !== "none" && style.visibility !== "hidden";
        });
      const visibleBoxes = visibleElements.map((element) => {
        const box = element.getBoundingClientRect();
        return { tag: element.tagName, className: element.className, left: box.left, right: box.right };
      });
      const controls = visibleElements
        .filter((element) => element.matches("a, button"))
        .map((element) => element.getBoundingClientRect());
      return {
        viewport,
        scrollWidth: document.documentElement.scrollWidth,
        controlsTallEnough: controls.every((box) => box.height >= 44),
        offenders: visibleBoxes.filter((box) => box.left < 0 || box.right > viewport),
      };
    });

    expect(geometry.scrollWidth).toBe(geometry.viewport);
    expect(geometry.controlsTallEnough).toBe(true);
    expect(geometry.offenders, JSON.stringify({ enlargedText, offenders: geometry.offenders })).toEqual([]);
  }
});


test("paid billing presents an active-access purchase summary with localized facts", async ({ page }) => {
  const merchantReference = `orna-${"b".repeat(31)}`;
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async (value: string) => window.localStorage.setItem("copied-order-reference", value),
      },
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
        email_verified: true,
        created_at: "2026-07-19T00:00:00Z",
      }),
    });
  });
  await page.route("**/api/v1/memberships/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ plan: "lifetime_member", status: "active", is_entitled: true }),
    });
  });
  await page.route("**/api/v1/billing/offer", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        product_code: "lifetime_member",
        name: "Lifetime Member Access",
        description: "Permanent access to available members-only field recordings.",
        amount_minor: 1000,
        currency: "USD",
        is_recurring: false,
        checkout_available: true,
        refund_summary: "Full refund requests are accepted within 14 calendar days.",
      }),
    });
  });
  await page.route("**/api/v1/billing/purchases/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([{
        id: "60000000-0000-4000-8000-000000000001",
        merchant_reference: merchantReference,
        product_code: "lifetime_member",
        amount_minor: 1000,
        currency: "USD",
        status: "paid",
        paid_at: "2026-08-04T09:00:00Z",
        refunded_at: null,
        created_at: "2026-08-04T08:59:00Z",
      }]),
    });
  });

  await page.goto("/membership");

  await expect(page.getByRole("heading", { name: "Lifetime access is active" })).toBeVisible();
  const summary = page.getByRole("group", { name: "Purchase summary" });
  await expect(summary.getByText("USD 10.00", { exact: true })).toBeVisible();
  await expect(summary.getByText(/Aug.*4.*2026|4.*Aug.*2026/)).toBeVisible();
  await expect(summary.getByText("Bereke Bank", { exact: true })).toBeVisible();
  await expect(summary.getByText("orna-bbbbbbb…bbbbbb", { exact: true })).toBeVisible();
  await expect(summary.getByText(merchantReference, { exact: true })).not.toBeVisible();
  const copyOrder = summary.getByRole("button", { name: "Copy order ID" });
  const descriptionId = await copyOrder.getAttribute("aria-describedby");
  expect(descriptionId).toBeTruthy();
  const fullReferenceDescription = page.locator(`#${descriptionId}`);
  await expect(fullReferenceDescription).toHaveText(`Full order ID ${merchantReference}`);
  await expect(fullReferenceDescription).toHaveClass("visually-hidden");
  const descriptionBox = await fullReferenceDescription.boundingBox();
  expect(descriptionBox?.width).toBeLessThanOrEqual(1);
  expect(descriptionBox?.height).toBeLessThanOrEqual(1);
  await copyOrder.click();
  await expect(page.getByRole("status")).toHaveText("Order ID copied.");
  await expect.poll(() => page.evaluate(() => window.localStorage.getItem("copied-order-reference")))
    .toBe(merchantReference);
  await page.evaluate(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: async () => { throw new Error("denied"); } },
    });
  });
  await summary.getByRole("button", { name: "Copy order ID" }).click();
  await expect(page.getByRole("status")).toHaveText("Unable to copy the order ID.");
  await expect(page.getByText("Test payment mode", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "One payment. No renewal." })).toHaveCount(0);
  await expect(page.getByText(/By continuing/)).toHaveCount(0);
  await expect(page.getByText(/Payment was processed by Bereke Bank/)).toBeVisible();
});


test("refund requires confirmation and becomes a truthful pending status", async ({ page }) => {
  await mockPaidAccount(page);
  let refundRequests = 0;
  let releaseRefund: (() => void) | undefined;
  const refundReleased = new Promise<void>((resolve) => { releaseRefund = resolve; });
  await page.route("**/api/v1/billing/purchases/*/refund-requests", async (route) => {
    refundRequests += 1;
    await refundReleased;
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        id: "70000000-0000-4000-8000-000000000001",
        purchase_id: "60000000-0000-4000-8000-000000000001",
        status: "requested",
        requested_at: "2026-08-05T09:00:00Z",
      }),
    });
  });

  await page.goto("/membership");
  const trigger = page.getByRole("button", { name: "Request full refund" });
  await expect(trigger).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
  await expect(trigger).toHaveCSS("border-top-width", "1px");
  await expect(page.getByText(/Full refunds can be requested until.*Aug.*18.*2026|Full refunds can be requested until.*18.*Aug.*2026/)).toBeVisible();

  await trigger.click();
  expect(refundRequests).toBe(0);
  const confirmation = page.getByRole("group", { name: "Confirm full refund" });
  await expect(confirmation).toBeVisible();
  await expect(confirmation).toBeFocused();
  await expect(confirmation).toContainText("Your payment will be refunded in full");
  await expect(confirmation).toContainText("purchase-backed access will end after Bereke Bank confirms the refund");

  await confirmation.getByRole("button", { name: "Keep membership" }).click();
  expect(refundRequests).toBe(0);
  await expect(confirmation).toHaveCount(0);
  await expect(trigger).toBeFocused();

  await trigger.click();
  const confirm = confirmation.locator(".billing-refund-confirm");
  await expect(confirm).toHaveAccessibleName("Confirm full refund");
  await confirm.click();
  await expect(confirm).toBeDisabled();
  expect(refundRequests).toBe(1);
  await confirm.click({ force: true });
  expect(refundRequests).toBe(1);
  releaseRefund?.();

  await expect(page.getByText("Refund requested", { exact: true })).toBeVisible();
  await expect(page.getByText(/Bereke Bank confirmation is pending/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Request full refund" })).toHaveCount(0);
  await expect(page.getByRole("group", { name: "Purchase summary" })).toBeVisible();
});


test("a server-confirmed refund request keeps purchase facts without another mutation action", async ({ page }) => {
  await mockPaidAccount(page, { isEntitled: false, status: "refund_requested" });

  await page.goto("/membership");

  await expect(page.getByRole("heading", { name: "Purchase confirmed" })).toBeVisible();
  await expect(page.getByText("Membership access is not currently active.", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Lifetime access is active" })).toHaveCount(0);
  await expect(page.getByRole("group", { name: "Purchase summary" })).toBeVisible();
  await expect(page.getByText("Refund requested", { exact: true })).toBeVisible();
  await expect(page.getByText(/Bereke Bank confirmation is pending/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Request full refund" })).toHaveCount(0);
});


test("an invalid paid timestamp falls back without breaking the paid summary", async ({ page }) => {
  await mockPaidAccount(page, { paidAt: "not-a-date" });

  await page.goto("/membership");

  const summary = page.getByRole("group", { name: "Purchase summary" });
  await expect(summary.getByText("Confirmed", { exact: true })).toBeVisible();
  await expect(page.getByText("Full refunds can be requested within 14 calendar days of payment."))
    .toBeVisible();
  await expect(page.locator(".billing-purchase-card")).toBeVisible();
});


test("a rejected refund keeps the paid summary and allows a deliberate retry", async ({ page }) => {
  await mockPaidAccount(page);
  let refundRequests = 0;
  await page.route("**/api/v1/billing/purchases/*/refund-requests", async (route) => {
    refundRequests += 1;
    await route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({ detail: "The self-service refund window has closed." }),
    });
  });

  await page.goto("/membership");
  await page.getByRole("button", { name: "Request full refund" }).click();
  const confirmation = page.getByRole("group", { name: "Confirm full refund" });
  await confirmation.locator(".billing-refund-confirm").click();

  await expect(page.locator(".billing-purchase-card [role='alert']"))
    .toContainText("The self-service refund window has closed.");
  await expect(page.getByRole("group", { name: "Purchase summary" })).toBeVisible();
  await expect(page.getByText("Refund requested", { exact: true })).toHaveCount(0);
  await expect(confirmation).toBeVisible();
  await expect(confirmation.locator(".billing-refund-confirm")).toBeEnabled();
  expect(refundRequests).toBe(1);
});


test("an existing entitlement hides the checkout action without a billing purchase", async ({ page }) => {
  await page.route("**/api/v1/users/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "50000000-0000-4000-8000-000000000001",
        email: "member@example.com",
        role: "member",
        is_active: true,
        email_verified: true,
        created_at: "2026-07-19T00:00:00Z",
      }),
    });
  });
  await page.route("**/api/v1/memberships/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ plan: "lifetime_member", status: "active", is_entitled: true }),
    });
  });
  await page.route("**/api/v1/billing/offer", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        product_code: "lifetime_member",
        name: "Lifetime Member Access",
        description: "Permanent access to available members-only field recordings.",
        amount_minor: 200,
        currency: "KZT",
        is_recurring: false,
        checkout_available: true,
        refund_summary: "Full refund requests are accepted within 14 calendar days.",
      }),
    });
  });

  await page.goto("/membership");

  await expect(page.getByText("Lifetime access is already active on this account.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Continue to secure payment" })).toHaveCount(0);
});


test("hosted checkout return polls purchases and refreshes membership", async ({ page }) => {
  let purchaseReads = 0;
  await page.route("**/api/v1/users/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "50000000-0000-4000-8000-000000000001",
        email: "member@example.com",
        role: "member",
        is_active: true,
        email_verified: true,
        created_at: "2026-07-19T00:00:00Z",
      }),
    });
  });
  await page.route("**/api/v1/memberships/me", async (route) => {
    const entitled = purchaseReads >= 2;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        plan: entitled ? "lifetime_member" : "none",
        status: entitled ? "active" : "inactive",
        is_entitled: entitled,
      }),
    });
  });
  await page.route("**/api/v1/billing/offer", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        product_code: "lifetime_member",
        name: "Lifetime Member Access",
        description: "Permanent access to available members-only field recordings.",
        amount_minor: 200,
        currency: "KZT",
        is_recurring: false,
        checkout_available: true,
        refund_summary: "Full refund requests are accepted within 14 calendar days.",
      }),
    });
  });
  await page.route("**/api/v1/billing/purchases/me", async (route) => {
    purchaseReads += 1;
    const paid = purchaseReads >= 2;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([{
        id: "60000000-0000-4000-8000-000000000001",
        merchant_reference: "orna-return",
        product_code: "lifetime_member",
        amount_minor: 200,
        currency: "KZT",
        status: paid ? "paid" : "pending",
        paid_at: paid ? "2026-07-30T09:00:00Z" : null,
        refunded_at: null,
        created_at: "2026-07-30T08:59:00Z",
      }]),
    });
  });

  await page.goto("/membership?payment_return=orna-return");

  await expect(page.getByText("Payment confirmed. Lifetime access is active.")).toBeVisible();
  await expect(page.getByText("Member sessions unlocked")).toBeVisible();
  await expect(page).toHaveURL(/\/membership$/);
  expect(purchaseReads).toBeGreaterThanOrEqual(2);
});


test("OAuth callback outcome is announced without exposing provider data", async ({ page }) => {
  await page.goto("/membership?oauth=error&oauth_provider=google&oauth_error=cancelled");
  await expect(page.locator("main").getByRole("alert")).toContainText("Google sign-in was cancelled");

  await page.goto("/membership?oauth=success&oauth_provider=apple");
  await expect(page.getByRole("alert").filter({ hasText: "Apple sign-in could not be confirmed" })).toBeVisible();
  await expect(page).toHaveURL(/\/membership$/);

  await page.route("**/api/v1/auth/oauth/link/pending", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ pending: true, provider: "google", ready: false }),
    });
  });
  let cancelledLink = false;
  await page.route("**/api/v1/auth/oauth/link/cancel", async (route) => {
    cancelledLink = true;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "cancelled" }),
    });
  });
  await page.goto("/membership?oauth=error&oauth_provider=google&oauth_error=account_conflict");
  const conflict = page.locator("main .auth-notice").filter({
    hasText: "Sign in to your existing account to connect Google",
  });
  await expect(conflict).toBeVisible();
  await expect(page.getByRole("button", { name: "Send a sign-in link" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Cancel Google linking" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Continue with Google" })).toHaveCount(0);
  await expect(page).toHaveURL(/\/membership$/);
  await page.getByRole("button", { name: "Cancel Google linking" }).click();
  expect(cancelledLink).toBe(true);
  await expect(conflict).toHaveCount(0);
});


test("magic-link reauthentication restores explicit Google linking confirmation", async ({ page }) => {
  await page.route("**/api/v1/users/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "50000000-0000-4000-8000-000000000001",
        email: "member@example.com",
        role: "member",
        is_active: true,
        email_verified: true,
        created_at: "2026-07-19T00:00:00Z",
      }),
    });
  });
  await page.route("**/api/v1/memberships/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ plan: "none", status: "inactive", is_entitled: false }),
    });
  });
  await page.route("**/api/v1/auth/oauth/link/pending", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ pending: true, provider: "google", ready: true }),
    });
  });
  let confirmed = false;
  await page.route("**/api/v1/auth/oauth/link/confirm", async (route) => {
    confirmed = true;
    expect(route.request().postDataJSON()).toEqual({ confirmed: true });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "linked", provider: "google", return_to: "/membership" }),
    });
  });

  await page.goto("/membership?magic=login");
  const linking = page.getByRole("region", { name: "Connect Google" });
  await expect(linking).toContainText("member@example.com");
  expect(confirmed).toBe(false);
  await linking.getByRole("button", { name: "Connect Google" }).click();

  expect(confirmed).toBe(true);
  await expect(page.getByRole("status")).toContainText("Google is now connected");
  await expect(linking).toHaveCount(0);
});


test("terminal Apple linking failure names the selected provider truthfully", async ({ page }) => {
  await page.route("**/api/v1/users/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "50000000-0000-4000-8000-000000000001",
        email: "member@example.com",
        role: "member",
        is_active: true,
        email_verified: true,
        created_at: "2026-07-19T00:00:00Z",
      }),
    });
  });
  await page.route("**/api/v1/memberships/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ plan: "none", status: "inactive", is_entitled: false }),
    });
  });
  await page.route("**/api/v1/auth/oauth/link/pending", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ pending: true, provider: "apple", ready: true }),
    });
  });
  await page.route("**/api/v1/auth/oauth/link/confirm", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "OAuth link could not be completed" }),
    });
  });

  await page.goto("/membership");
  await page.getByRole("button", { name: "Connect Apple" }).click();

  const alert = page.getByRole("alert").filter({ hasText: "Apple could not be connected" });
  await expect(alert).toContainText("Start Apple sign-in again before retrying.");
  await expect(page.getByText(/Google could not be connected|Start Google sign-in again/)).toHaveCount(0);
});


test("password reauthentication resumes pending Google linking before return navigation", async ({ page }) => {
  const user = {
    id: "50000000-0000-4000-8000-000000000001",
    email: "member@example.com",
    role: "member",
    is_active: true,
    email_verified: true,
    created_at: "2026-07-19T00:00:00Z",
  };
  let ready = false;
  await page.route("**/api/v1/auth/oauth/link/pending", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ pending: true, provider: "google", ready }),
    });
  });
  await page.route("**/api/v1/auth/login", async (route) => {
    ready = true;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        access_token: "e2e-token",
        token_type: "bearer",
        expires_at: "2026-07-28T12:00:00Z",
        user,
      }),
    });
  });
  await page.route("**/api/v1/memberships/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ plan: "none", status: "inactive", is_entitled: false }),
    });
  });

  await page.goto(
    "/membership?returnTo=%2Flibrary&oauth=error&oauth_provider=google&oauth_error=account_conflict",
  );
  await page.getByLabel("Email address", { exact: true }).fill(user.email);
  await page.getByLabel("Password", { exact: true }).fill("correct horse battery staple");
  await page.locator("form").getByRole("button", { name: "Continue" }).click();

  await expect(page.getByRole("region", { name: "Connect Google" })).toBeVisible();
  await expect(page).toHaveURL(/returnTo=%2Flibrary/);
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
        email_verified: true,
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

  await expect(page.getByRole("heading", { name: "Your account", exact: true })).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "Signed in with Google" })).toBeVisible();
  await expect(page).toHaveURL(/\/membership$/);
});

test("mobile account header uses a Profile link and a three-line menu icon", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/v1/users/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "50000000-0000-4000-8000-000000000001",
        email: "member@example.com",
        role: "member",
        is_active: true,
        email_verified: true,
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

  await page.goto("/membership");
  await expect(page.getByText("early_access", { exact: true })).toBeVisible();
  const navigation = page.getByRole("navigation", { name: "Primary navigation" });
  const menu = navigation.locator("summary[aria-label='Menu']");

  await expect(navigation.getByRole("link", { name: "Profile", exact: true })).not.toBeVisible();
  await expect(navigation.getByText("Menu", { exact: true })).toHaveCount(0);
  await expect(menu.locator(".site-menu-icon > span")).toHaveCount(3);

  await menu.click();
  await expect(navigation.getByRole("link", { name: "Profile", exact: true })).toBeVisible();
});

test("open account menu does not move or overlap the heading across the mobile breakpoint", async ({ page }) => {
  await page.route("**/api/v1/users/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "50000000-0000-4000-8000-000000000001",
        email: "member@example.com",
        role: "member",
        is_active: true,
        email_verified: true,
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

  for (const width of [390, 700]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/membership");
    const heading = page.getByRole("heading", { level: 1, name: "Your account" });
    const eyebrow = page.locator(".account-hero .eyebrow");
    await expect(heading).toBeVisible();
    await expect(eyebrow).toBeVisible();
    await expect(page.getByText("early_access", { exact: true })).toBeVisible();
    const navigation = page.getByRole("navigation", { name: "Primary navigation" });
    const menuDetails = navigation.locator(".site-menu-mobile");
    const menuLinks = menuDetails.locator(".site-menu-links");
    await expect(menuDetails).not.toHaveAttribute("open", "");
    const closedHeadingBox = await heading.boundingBox();
    await menuDetails.locator("summary[aria-label='Menu']").click();
    await expect(menuDetails).toHaveAttribute("open", "");
    await expect(menuLinks).toBeVisible();

    const [menuBox, openEyebrowBox, openHeadingBox] = await Promise.all([
      menuLinks.boundingBox(),
      eyebrow.boundingBox(),
      heading.boundingBox(),
    ]);
    expect(menuBox).not.toBeNull();
    expect(openEyebrowBox).not.toBeNull();
    expect(closedHeadingBox).not.toBeNull();
    expect(openHeadingBox).not.toBeNull();
    expect(openHeadingBox!.y).toBeCloseTo(closedHeadingBox!.y, 1);
    expect(menuBox!.y + menuBox!.height).toBeLessThanOrEqual(openEyebrowBox!.y);
  }
});


test("magic-link signup and login outcomes are announced after account confirmation", async ({ page }) => {
  await page.route("**/api/v1/users/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "50000000-0000-4000-8000-000000000001",
        email: "member@example.com",
        role: "member",
        is_active: true,
        email_verified: true,
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

  for (const outcome of ["signup", "login"]) {
    await page.goto(`/membership?magic=${outcome}`);
    await expect(page.getByRole("heading", { name: "Your account", exact: true })).toBeVisible();
    await expect(page.getByRole("status").filter({ hasText: "Signed in with your email link" })).toBeVisible();
    await expect(page).toHaveURL(/\/membership$/);
    await page.goto("/about");
  }
});


test("social sign-in preserves a sanitized internal return path", async ({ page }) => {
  await page.goto("/membership?returnTo=%2Fsessions%2Ffirst-session");

  const social = page.getByRole("group", { name: "Continue with a social account" });
  for (const provider of ["Google", "Apple", "Facebook"]) {
    await expect(social.getByRole("link", { name: `Continue with ${provider}` })).toHaveAttribute(
      "href",
      /return_to=%2Fsessions%2Ffirst-session/,
    );
  }

  await page.goto("/membership?returnTo=%2F%2Fevil.example%2Fsteal");
  await expect(page.getByRole("link", { name: "Continue with Google" })).toHaveAttribute(
    "href",
    /return_to=%2Fmembership/,
  );
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
        email_verified: true,
        created_at: "2026-07-19T00:00:00Z",
      }),
    });
  });
  await page.route("**/api/v1/memberships/me", async (route) => {
    await route.fulfill({ status: 503, contentType: "application/json", body: "{}" });
  });
  await page.goto("/membership?oauth=success&oauth_provider=google");

  await expect(page.getByRole("heading", { name: "Your account", exact: true })).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "Signed in with Google" })).toBeVisible();
  await expect(page.locator("main .auth-notice").filter({ hasText: "temporarily unavailable" })).toBeVisible();
  await expect(page.getByText("Plan", { exact: true }).locator("..")).toContainText("Unavailable");
  await expect(page.getByText("Status", { exact: true }).locator("..")).toContainText("Unavailable");
  await expect(page.getByText("Playback", { exact: true }).locator("..")).toContainText("Unavailable");
  await expect(page.getByText("Plan", { exact: true }).locator("..")).not.toContainText("none");
  const accessCard = page.getByRole("complementary", { name: "Listening access is unavailable." });
  await expect(accessCard.getByText("Unavailable", { exact: true })).toBeVisible();
  await expect(accessCard).toContainText("We could not confirm your membership access right now.");
  await expect(page.getByRole("heading", { name: "The public atlas is open." })).toHaveCount(0);
  await expect(page.getByText(/no membership interest has been recorded/i)).toHaveCount(0);
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

  await expect(page.getByRole("heading", { name: "Your account", exact: true })).toBeVisible();
  await expect(page.getByText("Plan", { exact: true }).locator("..")).toContainText("Loading…");
  await expect(page.getByText("Status", { exact: true }).locator("..")).toContainText("Loading…");
  await expect(page.getByRole("heading", { name: "Checking your listening access…" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "The public atlas is open." })).toHaveCount(0);
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
        email_verified: true,
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
          email_verified: true,
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
  await expect(page.getByRole("heading", { name: "Your account", exact: true })).toBeVisible();
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


test("email verification clears the fragment before requests and survives account reload outage", async ({ page }) => {
  const token = "v".repeat(43);
  let confirmationBody: unknown;
  let currentUserRequests = 0;
  await page.route("**/api/v1/auth/email-verification/confirm", async (route) => {
    expect(new URL(page.url()).hash).toBe("");
    confirmationBody = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "verified" }),
    });
  });
  await page.route("**/api/v1/users/me", async (route) => {
    currentUserRequests += 1;
    expect(new URL(page.url()).hash).toBe("");
    await route.fulfill({ status: 503, contentType: "application/json", body: "{}" });
  });

  await page.goto(`/membership#verify_email_token=${token}`);

  await expect(page).toHaveURL(/\/membership$/);
  await expect.poll(() => currentUserRequests).toBeGreaterThanOrEqual(2);
  await expect(page.getByRole("status").filter({ hasText: "Your email address is verified." })).toBeVisible();
  expect(confirmationBody).toEqual({ token });
});


test("password recovery request uses a neutral accepted state", async ({ page }) => {
  let requestBody: unknown;
  await page.route("**/api/v1/auth/password-reset/request", async (route) => {
    requestBody = route.request().postDataJSON();
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ accepted: true }),
    });
  });

  await page.goto("/membership?mode=login");
  await page.getByRole("link", { name: "Forgot your password?" }).click();
  await expect(page.getByRole("heading", { name: "Recover your password" })).toBeVisible();
  await page.getByLabel("Account email").fill("missing@example.com");
  await page.getByRole("button", { name: "Send reset link" }).click();

  await expect(page.getByRole("status")).toContainText(
    "If a password account exists for that email, a reset link has been sent.",
  );
  expect(requestBody).toEqual({ email: "missing@example.com" });
});


test("leaving recovery ignores a stale password-reset request failure", async ({ page }) => {
  let releaseRequest!: () => void;
  const blocked = new Promise<void>((resolve) => { releaseRequest = resolve; });
  await page.route("**/api/v1/auth/password-reset/request", async (route) => {
    await blocked;
    await route.fulfill({ status: 503, contentType: "application/json", body: "{}" });
  });

  await page.goto("/membership?mode=forgot");
  await page.getByLabel("Account email").fill("listener@example.com");
  await page.getByRole("button", { name: "Send reset link" }).click();
  await page.getByRole("link", { name: "Return to sign in" }).click();
  releaseRequest();

  await expect(page.getByRole("heading", { name: "Sign in to ORNA Atlas" })).toBeVisible();
  await expect(page.getByText("Password recovery is temporarily unavailable.")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Continue" })).toBeEnabled();
});


test("browser Back releases recovery busy state and ignores its stale failure", async ({ page }) => {
  let releaseRequest!: () => void;
  const blocked = new Promise<void>((resolve) => { releaseRequest = resolve; });
  await page.route("**/api/v1/auth/password-reset/request", async (route) => {
    await blocked;
    await route.fulfill({ status: 503, contentType: "application/json", body: "{}" });
  });

  await page.goto("/membership?mode=login");
  await page.getByRole("link", { name: "Forgot your password?" }).click();
  await page.getByLabel("Account email").fill("listener@example.com");
  await page.getByRole("button", { name: "Send reset link" }).click();
  await page.goBack();

  await expect(page.getByRole("heading", { name: "Sign in to ORNA Atlas" })).toBeVisible();
  const magicLinkForm = page.locator("form").filter({ has: page.getByLabel("Email address") });
  const passwordForm = page.locator("form").filter({
    has: page.getByLabel("Password account email", { exact: true }),
  });
  await expect(magicLinkForm.getByRole("button")).toBeEnabled();
  await expect(passwordForm.getByRole("button")).toBeEnabled();
  releaseRequest();
  await expect(page.getByText("Password recovery is temporarily unavailable.")).toHaveCount(0);
});


test("password reset removes the fragment before requests and returns to an empty sign-in", async ({ page }) => {
  const token = "r".repeat(43);
  let confirmationBody: unknown;
  await page.route("**/api/v1/auth/password-reset/confirm", async (route) => {
    expect(new URL(page.url()).hash).toBe("");
    confirmationBody = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "password_reset" }),
    });
  });

  await page.goto(`/membership#reset_password_token=${token}`);
  await expect(page).toHaveURL(/\/membership$/);
  await expect(page.getByRole("heading", { name: "Choose a new password" })).toBeVisible();
  await page.getByLabel("New password", { exact: true }).fill("a secure new password");
  await page.getByLabel("Confirm new password").fill("a secure new password");
  await page.getByRole("button", { name: "Reset password" }).click();

  await expect(page).toHaveURL(/\/membership\?mode=login$/);
  await expect(page.getByRole("status")).toContainText(
    "Your password was reset. Sign in with your new password.",
  );
  await expect(page.getByLabel("Password", { exact: true })).toHaveValue("");
  expect(confirmationBody).toEqual({ token, password: "a secure new password" });
});


test("password reset discards a token after an ambiguous transport outcome", async ({ page }) => {
  const token = "r".repeat(43);
  let attempts = 0;
  await page.route("**/api/v1/auth/password-reset/confirm", async (route) => {
    attempts += 1;
    await route.fulfill({ status: 503, contentType: "application/json", body: "{}" });
  });

  await page.goto(`/membership#reset_password_token=${token}`);
  await page.getByLabel("New password", { exact: true }).fill("a secure new password");
  await page.getByLabel("Confirm new password").fill("a secure new password");
  await page.getByRole("button", { name: "Reset password" }).click();

  await expect(page).toHaveURL(/\/membership\?mode=login$/);
  await expect(page.getByRole("heading", { name: "Sign in to ORNA Atlas" })).toBeVisible();
  await expect(page.getByText(
    "We could not confirm whether your password changed.",
    { exact: false },
  )).toBeVisible();
  await expect(page.getByRole("heading", { name: "Choose a new password" })).toHaveCount(0);
  expect(attempts).toBe(1);
});


test("ambiguous password reset fails closed for an authenticated account", async ({ page }) => {
  const token = "r".repeat(43);
  let currentUserRequests = 0;
  await page.route("**/api/v1/users/me", async (route) => {
    currentUserRequests += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "50000000-0000-4000-8000-000000000001",
        email: "member@example.com",
        role: "member",
        is_active: true,
        email_verified: true,
        created_at: "2026-01-01T00:00:00Z",
      }),
    });
  });
  await page.route("**/api/v1/memberships/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ plan: "free", status: "active", is_entitled: false }),
    });
  });
  await page.route("**/api/v1/auth/password-reset/confirm", async (route) => {
    await route.fulfill({ status: 503, contentType: "application/json", body: "{}" });
  });

  await page.goto(`/membership#reset_password_token=${token}`);
  await expect.poll(() => currentUserRequests).toBeGreaterThan(0);
  await expect(page.getByRole("heading", { name: "Choose a new password" })).toBeVisible();
  await page.getByLabel("New password", { exact: true }).fill("a secure new password");
  await page.getByLabel("Confirm new password").fill("a secure new password");
  await page.getByRole("button", { name: "Reset password" }).click();

  await expect(page).toHaveURL(/\/membership\?mode=login$/);
  await expect(page.getByRole("heading", { name: "Sign in to ORNA Atlas" })).toBeVisible();
  await expect(page.getByText("member@example.com")).toHaveCount(0);
});


test("leaving a pending ambiguous reset cannot restore an authenticated dashboard", async ({ page }) => {
  const token = "r".repeat(43);
  let releaseConfirmation!: () => void;
  const confirmationBlocked = new Promise<void>((resolve) => { releaseConfirmation = resolve; });
  await page.route("**/api/v1/users/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "50000000-0000-4000-8000-000000000001",
        email: "member@example.com",
        role: "member",
        is_active: true,
        email_verified: true,
        created_at: "2026-01-01T00:00:00Z",
      }),
    });
  });
  await page.route("**/api/v1/memberships/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ plan: "free", status: "active", is_entitled: false }),
    });
  });
  await page.route("**/api/v1/auth/password-reset/confirm", async (route) => {
    await confirmationBlocked;
    await route.fulfill({ status: 503, contentType: "application/json", body: "{}" });
  });

  await page.goto(`/membership#reset_password_token=${token}`);
  await expect(page.getByRole("heading", { name: "Choose a new password" })).toBeVisible();
  await page.getByLabel("New password", { exact: true }).fill("a secure new password");
  await page.getByLabel("Confirm new password").fill("a secure new password");
  await page.getByRole("button", { name: "Reset password" }).click();
  await page.getByRole("link", { name: "Return to sign in" }).click();
  releaseConfirmation();

  await expect(page.getByRole("heading", { name: "Sign in to ORNA Atlas" })).toBeVisible();
  await expect(page.getByText("member@example.com")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Your account", exact: true })).not.toBeVisible();
});


test("same-route membership navigation follows query changes and browser history", async ({ page }) => {
  await page.goto("/membership?mode=login");
  await expect(page.getByRole("heading", { name: "Sign in to ORNA Atlas" })).toBeVisible();

  await page.getByRole("link", { name: "Create a free account" }).click();
  await expect(page).toHaveURL(/\/membership\?mode=register$/);
  await expect(page.getByRole("heading", { name: "Create your free ORNA account" })).toBeVisible();

  await page.goBack();
  await expect(page).toHaveURL(/\/membership\?mode=login$/);
  await expect(page.getByRole("heading", { name: "Sign in to ORNA Atlas" })).toBeVisible();

  await page.getByRole("link", { name: "Forgot your password?" }).click();
  await expect(page.getByRole("heading", { name: "Recover your password" })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Sign in to ORNA Atlas" })).toBeVisible();
});


test("same-route recovery handles post-mount fragments and reset exit", async ({ page }) => {
  const verificationToken = "v".repeat(43);
  let releaseConfirmation!: () => void;
  const confirmationBlocked = new Promise<void>((resolve) => { releaseConfirmation = resolve; });
  await page.route("**/api/v1/auth/email-verification/confirm", async (route) => {
    expect(new URL(page.url()).hash).toBe("");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "verified" }),
    });
  });
  await page.route("**/api/v1/auth/password-reset/confirm", async (route) => {
    await confirmationBlocked;
    await route.fulfill({ status: 503, contentType: "application/json", body: "{}" });
  });

  await page.goto("/membership?mode=login");
  await expect(page.getByRole("heading", { name: "Sign in to ORNA Atlas" })).toBeVisible();
  await page.evaluate((token) => {
    window.location.hash = `verify_email_token=${token}`;
  }, verificationToken);
  await expect(page).toHaveURL(/\/membership\?mode=login$/);
  await expect(page.getByText("Your email address is verified.")).toBeVisible();

  await page.evaluate((token) => {
    window.location.hash = `reset_password_token=${token}`;
  }, "r".repeat(43));
  await expect(page.getByRole("heading", { name: "Choose a new password" })).toBeVisible();
  await page.getByLabel("New password", { exact: true }).fill("a secure new password");
  await page.getByLabel("Confirm new password").fill("a secure new password");
  await page.getByRole("button", { name: "Reset password" }).click();
  await page.goBack();
  releaseConfirmation();
  await expect(page.getByRole("heading", { name: "Sign in to ORNA Atlas" })).toBeVisible();
  await expect(page.getByText("We could not confirm whether the password changed.")).toHaveCount(0);
});


test("a new verification fragment discards an ambiguous pending reset owner", async ({ page }) => {
  let releaseReset!: () => void;
  let releaseVerification!: () => void;
  let verificationRequests = 0;
  let currentUserRequests = 0;
  const resetBlocked = new Promise<void>((resolve) => { releaseReset = resolve; });
  const verificationBlocked = new Promise<void>((resolve) => { releaseVerification = resolve; });
  await page.route("**/api/v1/users/me", async (route) => {
    currentUserRequests += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "50000000-0000-4000-8000-000000000001",
        email: "member@example.com",
        role: "member",
        is_active: true,
        email_verified: true,
        created_at: "2026-01-01T00:00:00Z",
      }),
    });
  });
  await page.route("**/api/v1/memberships/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ plan: "free", status: "active", is_entitled: false }),
    });
  });
  await page.route("**/api/v1/auth/password-reset/confirm", async (route) => {
    await resetBlocked;
    await route.fulfill({ status: 503, contentType: "application/json", body: "{}" });
  });
  await page.route("**/api/v1/auth/email-verification/confirm", async (route) => {
    verificationRequests += 1;
    await verificationBlocked;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "verified" }),
    });
  });

  await page.goto(`/membership#reset_password_token=${"r".repeat(43)}`);
  await expect.poll(() => currentUserRequests).toBeGreaterThan(0);
  await page.getByLabel("New password", { exact: true }).fill("a secure new password");
  await page.getByLabel("Confirm new password").fill("a secure new password");
  await page.getByRole("button", { name: "Reset password" }).click();
  await page.evaluate((token) => {
    window.location.hash = `verify_email_token=${token}`;
  }, "v".repeat(43));

  await expect.poll(() => verificationRequests).toBe(1);
  await expect(page.getByRole("heading", { name: "Choose a new password" })).toHaveCount(0);
  releaseVerification();
  await expect(page.getByText("Your email address is verified.")).toBeVisible();
  await expect(page.getByText("member@example.com")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Your account", exact: true })).not.toBeVisible();
  releaseReset();
  await expect(page.getByText("We could not confirm whether the password changed.")).toHaveCount(0);
  await expect(page.getByText("member@example.com")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Choose a new password" })).toHaveCount(0);
});


test("a dual-key callback fragment is rejected without choosing two owners", async ({ page }) => {
  let verificationRequests = 0;
  let resetRequests = 0;
  await page.route("**/api/v1/auth/email-verification/confirm", async (route) => {
    verificationRequests += 1;
    await route.fulfill({ status: 500, contentType: "application/json", body: "{}" });
  });
  await page.route("**/api/v1/auth/password-reset/confirm", async (route) => {
    resetRequests += 1;
    await route.fulfill({ status: 500, contentType: "application/json", body: "{}" });
  });

  await page.goto(
    `/membership#verify_email_token=${"v".repeat(43)}&reset_password_token=${"r".repeat(43)}`,
  );

  await expect(page.getByRole("heading", { name: "Sign in or create your account" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Choose a new password" })).toHaveCount(0);
  await page.waitForTimeout(250);
  expect(verificationRequests).toBe(0);
  expect(resetRequests).toBe(0);
});


test("browser history restores a bare membership URL to its default mode", async ({ page }) => {
  await page.goto("/membership");
  await page.getByRole("link", { name: "Profile" }).click();
  await expect(page).toHaveURL(/\/membership\?mode=register$/);
  await expect(page.getByRole("heading", { name: "Create your free ORNA account" })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/\/membership$/);
  await expect(page.getByRole("heading", { name: "Sign in or create your account" })).toBeVisible();
});


test("entering reset invalidates a pending password login", async ({ page }) => {
  let releaseLogin!: () => void;
  const loginBlocked = new Promise<void>((resolve) => { releaseLogin = resolve; });
  await page.route("**/api/v1/auth/login", async (route) => {
    await loginBlocked;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        access_token: "stale-login-token",
        token_type: "bearer",
        expires_at: "2026-07-19T19:00:00Z",
        user: {
          id: "50000000-0000-4000-8000-000000000003",
          email: "stale-login@example.com",
          role: "member",
          is_active: true,
          email_verified: true,
          created_at: "2026-07-19T00:00:00Z",
        },
      }),
    });
  });

  await page.goto("/membership?mode=login");
  await page.getByLabel("Password account email", { exact: true }).fill("stale-login@example.com");
  await page.getByLabel("Password", { exact: true }).fill("valid-password");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.evaluate(() => { window.location.hash = `reset_password_token=${"r".repeat(43)}`; });
  await expect(page.getByRole("button", { name: "Reset password" })).toBeEnabled();
  releaseLogin();
  await expect(page.getByRole("heading", { name: "Choose a new password" })).toBeVisible();
  await expect(page.getByText("stale-login@example.com")).toHaveCount(0);
});


test("entering reset invalidates a pending magic-link request", async ({ page }) => {
  let releaseMagicLink!: () => void;
  const magicLinkBlocked = new Promise<void>((resolve) => { releaseMagicLink = resolve; });
  await page.route("**/api/v1/auth/magic-link/request", async (route) => {
    await magicLinkBlocked;
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ accepted: true }),
    });
  });

  await page.goto("/membership?mode=login");
  await page.getByLabel("Email address", { exact: true }).fill("magic@example.com");
  await page.getByRole("button", { name: "Email me a sign-in link" }).click();
  await page.evaluate(() => { window.location.hash = `reset_password_token=${"r".repeat(43)}`; });
  await expect(page.getByRole("button", { name: "Reset password" })).toBeEnabled();
  releaseMagicLink();
  await expect(page.getByRole("heading", { name: "Choose a new password" })).toBeVisible();
  await expect(page.getByText("Check your email. The one-time sign-in link expires in 15 minutes.")).toHaveCount(0);
});


test("unknown same-route membership mode resets stale auth UI", async ({ page }) => {
  await page.goto("/membership?mode=register");
  await expect(page.getByRole("heading", { name: "Create your free ORNA account" })).toBeVisible();
  await page.evaluate(() => {
    window.history.pushState(null, "", "/membership?mode=bogus");
    window.dispatchEvent(new PopStateEvent("popstate"));
  });
  await expect(page.getByRole("heading", { name: "Sign in or create your account" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Create your free ORNA account" })).toHaveCount(0);
});


test("verification delivery does not relabel the sign-out action", async ({ page }) => {
  let releaseVerification!: () => void;
  const verificationBlocked = new Promise<void>((resolve) => { releaseVerification = resolve; });
  await page.route("**/api/v1/users/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "50000000-0000-4000-8000-000000000001",
        email: "member@example.com",
        role: "member",
        is_active: true,
        email_verified: false,
        created_at: "2026-01-01T00:00:00Z",
      }),
    });
  });
  await page.route("**/api/v1/membership/me", async (route) => {
    await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });
  await page.route("**/api/v1/auth/email-verification/request", async (route) => {
    await verificationBlocked;
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ accepted: true }),
    });
  });
  await page.route("**/api/v1/auth/email-verification/confirm", async (route) => {
    await route.fulfill({ status: 503, contentType: "application/json", body: "{}" });
  });

  await page.goto("/membership");
  await page.getByRole("button", { name: /Verify email/ }).click();
  await expect(page.getByRole("button", { name: /Sending/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
  await page.evaluate(() => { window.location.hash = `verify_email_token=${"v".repeat(43)}`; });
  await expect(page.getByText("Email verification is temporarily unavailable.")).toBeVisible();
  releaseVerification();
  await expect(page.getByRole("button", { name: /Verify email/ })).toBeEnabled();
  await expect(page.getByText("Check your email. The verification link expires in 24 hours.")).toHaveCount(0);
});


test("verification rejects a wrong success literal", async ({ page }) => {
  const token = "v".repeat(43);
  await page.route("**/api/v1/auth/email-verification/confirm", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "password_reset" }),
    });
  });

  await page.goto(`/membership#verify_email_token=${token}`);
  await expect(page.getByText("Email verification is temporarily unavailable. Please try again.")).toBeVisible();
  await expect(page.getByText("Your email address is verified.")).toHaveCount(0);
});


test("verification cannot be overwritten by a stale initial account load", async ({ page }) => {
  const token = "v".repeat(43);
  let userRequests = 0;
  let releaseInitial!: () => void;
  let staleResponseCompleted = false;
  const initialBlocked = new Promise<void>((resolve) => { releaseInitial = resolve; });
  const user = (verified: boolean) => ({
    id: "50000000-0000-4000-8000-000000000001",
    email: "member@example.com",
    role: "member",
    is_active: true,
    email_verified: verified,
    created_at: "2026-01-01T00:00:00Z",
  });

  await page.route("**/api/v1/auth/email-verification/confirm", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "verified" }),
    });
  });
  await page.route("**/api/v1/users/me", async (route) => {
    const requestNumber = ++userRequests;
    if (requestNumber === 1) await initialBlocked;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(user(requestNumber !== 1)),
    });
    if (requestNumber === 1) staleResponseCompleted = true;
  });
  await page.route("**/api/v1/membership/me", async (route) => {
    await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });

  await page.goto(`/membership#verify_email_token=${token}`);
  await expect.poll(() => userRequests).toBe(2);
  await expect(page.getByText("Your email address is verified.")).toBeVisible();
  releaseInitial();
  await expect.poll(() => staleResponseCompleted).toBe(true);
  await expect(page.getByText("Verified", { exact: true })).toBeVisible();
  await expect(page.getByText("Not verified", { exact: true })).toHaveCount(0);
});


test("recovery links expose 44px touch targets on a narrow phone", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 700 });
  await page.goto("/membership?mode=login");
  const forgot = page.getByRole("link", { name: "Forgot your password?" });
  await expect(forgot).toBeVisible();
  expect((await forgot.boundingBox())?.height).toBeGreaterThanOrEqual(44);

  await forgot.click();
  const back = page.getByRole("link", { name: "Return to sign in" });
  await expect(back).toBeVisible();
  expect((await back.boundingBox())?.height).toBeGreaterThanOrEqual(44);
});
